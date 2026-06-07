"""Stacks blockchain manager."""
import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING

from rotkehlchen.accounting.structures.balance import Balance, BalanceSheet
from rotkehlchen.assets.asset import Asset
from rotkehlchen.assets.utils import get_or_create_stacks_token, token_normalized_value_decimals
from rotkehlchen.chain.manager import ChainManagerWithTransactions
from rotkehlchen.chain.stacks.constants import micro_stx_to_stx
from rotkehlchen.chain.stacks.decoding.decoder import StacksTransactionDecoder
from rotkehlchen.chain.stacks.decoding.tools import StacksDecoderTools
from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
from rotkehlchen.chain.stacks.transactions import StacksTransactions
from rotkehlchen.constants import DEFAULT_BALANCE_LABEL
from rotkehlchen.constants.assets import A_STX
from rotkehlchen.constants.misc import ZERO
from rotkehlchen.errors.asset import UnknownAsset, WrongAssetType
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.fval import FVal
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import StacksAddress, Timestamp

if TYPE_CHECKING:
    from rotkehlchen.premium.premium import Premium

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class StacksManager(ChainManagerWithTransactions[StacksAddress]):
    """Manager for Stacks blockchain operations.

    Handles balance queries and transaction fetching for Stacks addresses.
    Uses the Hiro REST API through StacksInquirer.
    """

    def __init__(
            self,
            node_inquirer: StacksInquirer,
            premium: 'Premium | None' = None,
    ) -> None:
        """Initialize the Stacks manager.

        Args:
            node_inquirer: The Stacks node inquirer for API queries
            premium: Optional premium subscription for extended features
        """
        self.node_inquirer = node_inquirer
        self.database = node_inquirer.database
        self.premium = premium
        self.transactions = StacksTransactions(
            node_inquirer=node_inquirer,
            database=node_inquirer.database,
        )
        base_tools = StacksDecoderTools(
            database=node_inquirer.database,
            node_inquirer=node_inquirer,
        )
        self.transactions_decoder = StacksTransactionDecoder(
            database=node_inquirer.database,
            node_inquirer=node_inquirer,
            transactions=self.transactions,
            base_tools=base_tools,
            premium=premium,
        )

    def query_balances(
            self,
            addresses: Sequence[StacksAddress],
    ) -> dict[StacksAddress, BalanceSheet]:
        """Query the balances of the given addresses.

        Args:
            addresses: List of Stacks addresses to query

        Returns:
            Dictionary mapping addresses to their balance sheets

        May raise RemoteError if there is a problem with querying the API.
        """
        chain_balances: defaultdict[StacksAddress, BalanceSheet] = defaultdict(BalanceSheet)
        tokens_to_price: list[Asset] = []
        address_token_balances: dict[StacksAddress, dict[Asset, FVal]] = {}

        if not addresses:
            return dict(chain_balances)

        stx_price = Inquirer.find_main_currency_price(A_STX)

        for address in addresses:
            try:
                response = self.node_inquirer.get_balances(address)
            except RemoteError as e:
                log.error(f'Failed to query Stacks balances for {address}: {e}')
                continue

            if response is None:
                continue

            # Get STX balance
            stx_data = response.get('stx', {})
            balance_str = stx_data.get('balance', '0')

            try:
                balance_micro = int(balance_str)
            except (ValueError, TypeError):
                log.error(f'Invalid STX balance for {address}: {balance_str}')
                continue

            if balance_micro > 0:
                balance = micro_stx_to_stx(balance_micro)
                chain_balances[address].assets[A_STX][DEFAULT_BALANCE_LABEL] = Balance(
                    amount=balance,
                    value=balance * stx_price,
                )

            # Parse SIP-10 fungible token balances
            token_balances = self._parse_fungible_tokens(response, address)
            if token_balances:
                tokens_to_price.extend(token_balances.keys())
                address_token_balances[address] = token_balances

        # Bulk fetch token prices for all addresses
        if tokens_to_price:
            token_prices = Inquirer.find_main_currency_prices(list(tokens_to_price))
            for address, token_balances in address_token_balances.items():
                for token, balance in token_balances.items():
                    chain_balances[address].assets[token][DEFAULT_BALANCE_LABEL] = Balance(
                        amount=balance,
                        value=balance * token_prices.get(token, ZERO),
                    )

        return dict(chain_balances)

    def _parse_fungible_tokens(
            self,
            response: dict,
            address: StacksAddress,
    ) -> dict[Asset, FVal]:
        """Parse SIP-10 fungible token balances from the API response.

        Args:
            response: The full API response from get_balances
            address: The address being queried (for logging)

        Returns:
            Dictionary mapping token assets to their balances
        """
        token_balances: dict[Asset, FVal] = {}
        fungible_tokens = response.get('fungible_tokens', {})

        for token_id, token_data in fungible_tokens.items():
            # Token ID format: CONTRACT_ID::asset-name. Both parts are needed: the
            # CONTRACT_ID for metadata/contract calls and the asset-name for the CAIP-19 id.
            if '::' not in token_id:
                log.warning(f'Invalid token ID format for {address}: {token_id}')
                continue

            contract_id, asset_name = token_id.split('::', 1)  # contract_id is a str principal

            try:
                balance_raw = int(token_data.get('balance', '0'))
            except (ValueError, TypeError):
                log.error(f'Invalid token balance for {token_id} at {address}')
                continue

            if balance_raw == 0:
                continue

            # Fetch token metadata from Hiro API for proper name/symbol
            metadata = self.node_inquirer.api_client.get_token_metadata(contract_id)
            log.debug(
                f'Fetched metadata for {contract_id}: '
                f'name={metadata.name if metadata else None}, '
                f'symbol={metadata.symbol if metadata else None}',
            )

            try:
                token = get_or_create_stacks_token(
                    userdb=self.database,
                    contract_id=contract_id,
                    asset_name=asset_name,
                    name=metadata.name if metadata else None,
                    symbol=metadata.symbol if metadata else None,
                    decimals=metadata.decimals if metadata else None,
                )
            except (RemoteError, DeserializationError, UnknownAsset, WrongAssetType) as e:
                log.error(f'Failed to get/create token {contract_id} for {address}: {e}')
                continue

            # SIP-10 tokens typically use 6 decimals like STX, but use token's decimals if known
            balance = token_normalized_value_decimals(balance_raw, token.decimals)
            token_balances[token] = balance
            log.debug(f'Found {token} balance for {address}: {balance}')

        return token_balances

    def query_transactions(
            self,
            addresses: list[StacksAddress],
            from_timestamp: Timestamp,
            to_timestamp: Timestamp,
    ) -> None:
        """Query and save transactions for the given addresses.

        Args:
            addresses: List of Stacks addresses to query
            from_timestamp: Start of time range
            to_timestamp: End of time range

        May raise RemoteError if there is a problem with querying the API.
        """
        for address in addresses:
            self.transactions.query_transactions_for_address(
                address=address,
                from_ts=from_timestamp,
                to_ts=to_timestamp,
            )

    def decode_undecoded_transactions(
            self,
            limit: int | None = None,
            send_ws_notifications: bool = False,
    ) -> list[str]:
        """Decode any undecoded transactions in the database.

        Args:
            limit: Optional limit on number of transactions to decode
            send_ws_notifications: Whether to send WebSocket progress notifications

        Returns:
            List of transaction IDs that were decoded
        """
        return self.transactions_decoder.get_and_decode_undecoded_transactions(
            limit=limit,
            send_ws_notifications=send_ws_notifications,
        )
