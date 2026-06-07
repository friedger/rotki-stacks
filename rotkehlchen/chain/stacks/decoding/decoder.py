"""Stacks transaction decoder."""
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rotkehlchen.assets.utils import get_or_create_stacks_token
from rotkehlchen.chain.decoding.constants import CPT_GAS
from rotkehlchen.chain.decoding.decoder import TransactionDecoder
from rotkehlchen.chain.decoding.types import DecodingRulesBase
from rotkehlchen.chain.stacks.constants import (
    OUTGOING_EVENT_TYPES,
    get_all_stacks_counterparties,
    micro_stx_to_stx,
)
from rotkehlchen.chain.stacks.types import StacksTransaction, StacksTxType
from rotkehlchen.constants.assets import A_STX
from rotkehlchen.constants.misc import ZERO
from rotkehlchen.db.filtering import (
    StacksEventFilterQuery,
    StacksTransactionsNotDecodedFilterQuery,
)
from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.db.stackstx import DBStacksTx
from rotkehlchen.errors.asset import UnknownAsset, WrongAssetType
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.fval import FVal
from rotkehlchen.history.events.structures.stacks_event import StacksEvent
from rotkehlchen.history.events.structures.types import HistoryEventSubType, HistoryEventType
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import Location, StacksAddress, SupportedBlockchain

from ..modules.alex.decoder import decode_alex_events, is_alex_transaction
from ..modules.allbridge.decoder import decode_allbridge_events, is_allbridge_transaction
from ..modules.arkadiko.decoder import decode_arkadiko_events, is_arkadiko_transaction
from ..modules.bitflow.decoder import decode_bitflow_events, is_bitflow_transaction
from ..modules.dual_stacking.decoder import (
    decode_dual_stacking_events,
    is_dual_stacking_transaction,
)
from ..modules.hermetica.decoder import decode_hermetica_events, is_hermetica_transaction
from ..modules.pox.decoder import decode_pox_events, is_pox_transaction
from ..modules.sbtc.decoder import decode_sbtc_events, is_sbtc_transaction
from ..modules.sendmany.decoder import decode_sendmany_events, is_sendmany_transaction
from ..modules.stacking_pools.decoder import (
    decode_stacking_pool_events,
    is_stacking_pool_transaction,
)
from ..modules.stackingdao.decoder import (
    decode_stackingdao_events,
    is_stackingdao_transaction,
)
from ..modules.usdcx.decoder import decode_usdcx_events, is_usdcx_transaction
from ..modules.velar.decoder import decode_velar_events, is_velar_transaction
from ..modules.zest.decoder import decode_zest_events, is_zest_transaction
from .tools import StacksDecoderTools

if TYPE_CHECKING:
    from rotkehlchen.chain.decoding.types import CounterpartyDetails
    from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
    from rotkehlchen.chain.stacks.transactions import StacksTransactions
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.db.drivers.gevent import DBCursor
    from rotkehlchen.premium.premium import Premium

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


@dataclass(init=True, repr=True, eq=True, order=False, unsafe_hash=False, frozen=True)
class StacksDecodingRules(DecodingRulesBase):
    """Decoding rules for Stacks transactions."""
    all_counterparties: set['CounterpartyDetails']

    def __add__(self, other: 'StacksDecodingRules') -> 'StacksDecodingRules':
        if not isinstance(other, StacksDecodingRules):
            raise TypeError(
                f'Can only add StacksDecodingRules to StacksDecodingRules. Got {type(other)}',
            )
        return StacksDecodingRules(
            all_counterparties=self.all_counterparties | other.all_counterparties,
        )


class StacksTransactionDecoder(TransactionDecoder[StacksTransaction, StacksDecodingRules, Any, str, StacksEvent, StacksTransaction, StacksDecoderTools, DBStacksTx, StacksEventFilterQuery, StacksTransactionsNotDecodedFilterQuery]):  # noqa: E501
    """Decoder for Stacks blockchain transactions."""

    def __init__(
            self,
            database: 'DBHandler',
            node_inquirer: 'StacksInquirer',
            transactions: 'StacksTransactions',
            base_tools: 'StacksDecoderTools',
            premium: 'Premium | None' = None,
    ):
        self.node_inquirer = node_inquirer
        self.transactions = transactions
        self.dbevents = DBHistoryEvents(database)
        super().__init__(
            database=database,
            dbtx=DBStacksTx(database),
            tx_mappings_table='stacks_tx_mappings',
            chain_name=SupportedBlockchain.STACKS.name.lower(),
            value_asset=A_STX.resolve_to_asset_with_oracles(),
            rules=StacksDecodingRules(all_counterparties=get_all_stacks_counterparties()),
            premium=premium,
            base_tools=base_tools,
            misc_counterparties=[],
            possible_decoding_exceptions=(),
        )

    def _add_builtin_decoders(self, rules: StacksDecodingRules) -> None:
        """No-op for Stacks. All decoders are loaded dynamically."""

    def _add_single_decoder(
            self,
            class_name: str,
            decoder_class: type[Any],
            rules: StacksDecodingRules,
    ) -> None:
        """Initialize a single decoder, add it to the set of decoders to use
        and append its rules to the passed rules.
        For now, Stacks uses simplified decoding without protocol-specific decoders.
        """

    @staticmethod
    def _load_default_decoding_rules() -> StacksDecodingRules:
        return StacksDecodingRules(all_counterparties=set())

    def _get_tx_not_decoded_filter_query(
            self,
            limit: int | None,
    ) -> StacksTransactionsNotDecodedFilterQuery:
        return StacksTransactionsNotDecodedFilterQuery.make(limit=limit)

    def _load_transaction_context(
            self,
            cursor: 'DBCursor',
            tx_hash: str,
    ) -> StacksTransaction:
        """Load the transaction from DB or fetch from API."""
        tx = self.transactions.get_or_create_transaction(tx_id=tx_hash)
        if tx is None:
            raise RemoteError(f'Could not find Stacks transaction {tx_hash}')
        return tx

    def _decode_transaction_from_context(
            self,
            context: StacksTransaction,
            ignore_cache: bool,
            delete_customized: bool,
    ) -> tuple[list[StacksEvent], bool, set[str] | None]:
        if (events := self._maybe_load_or_purge_events_from_db(
            transaction=context,
            tx_ref=context.tx_id,
            location=Location.STACKS,
            ignore_cache=ignore_cache,
            delete_customized=delete_customized,
        )) is not None:
            return events, False, None

        # Decode the transaction
        return self._decode_transaction(transaction=context)

    def _make_event_filter_query(self, tx_ref: str) -> StacksEventFilterQuery:
        return StacksEventFilterQuery.make(tx_ids=[tx_ref])

    def _calculate_fees(self, tx: StacksTransaction) -> FVal:
        return micro_stx_to_stx(tx.fee_rate)

    def _maybe_decode_fee_event(self, transaction: StacksTransaction) -> StacksEvent | None:
        """Decode the fee event for the given transaction.
        Returns the fee event or None if the fee is zero or the sender is not tracked.
        """
        if transaction.fee_rate == ZERO:
            return None

        if not self.base.is_tracked(transaction.sender_address):
            return None

        amount = micro_stx_to_stx(transaction.fee_rate)
        return self.base.make_event_next_index(
            tx_ref=transaction.tx_id,
            timestamp=transaction.block_time,
            event_type=HistoryEventType.SPEND,
            event_subtype=HistoryEventSubType.FEE,
            asset=A_STX,
            amount=amount,
            location_label=transaction.sender_address,
            notes=f'Spend {amount} STX as transaction fee',
            counterparty=CPT_GAS,
        )

    def _maybe_decode_stx_transfer(
            self,
            transaction: StacksTransaction,
    ) -> StacksEvent | None:
        """Decode native STX transfers."""
        if transaction.tx_type != StacksTxType.TOKEN_TRANSFER:
            return None

        if transaction.amount is None or transaction.amount == 0:
            return None

        if transaction.recipient_address is None:
            return None

        amount = micro_stx_to_stx(transaction.amount)
        from_address = transaction.sender_address
        to_address = transaction.recipient_address

        if (direction_result := self.base.decode_direction(
                from_address=from_address,
                to_address=to_address,
        )) is None:
            return None

        event_type, event_subtype, location_label, address, counterparty, verb = direction_result
        counterparty_or_address = counterparty or address
        preposition = 'to' if event_type in OUTGOING_EVENT_TYPES else 'from'

        return self.base.make_event_next_index(
            tx_ref=transaction.tx_id,
            timestamp=transaction.block_time,
            event_type=event_type,
            event_subtype=event_subtype,
            asset=A_STX,
            amount=amount,
            location_label=location_label,
            notes=f'{verb} {amount} STX {preposition} {counterparty_or_address}',
            counterparty=counterparty,
            address=address,
        )

    def _maybe_decode_token_transfer(
            self,
            transaction: StacksTransaction,
            token_transfers: list[dict],
    ) -> list[StacksEvent]:
        """Decode SIP-10 token transfers from a transaction.

        The Hiro API returns events with structure:
        {
            "event_type": "fungible_token_asset",
            "asset": {
                "asset_event_type": "transfer" | "mint" | "burn",
                "asset_id": "SP...::token-name",
                "sender": "SP..." | "",
                "recipient": "SP..." | "",
                "amount": "12345"
            }
        }
        """
        events: list[StacksEvent] = []

        for event in token_transfers:
            try:
                asset_data = event.get('asset', {})
                asset_identifier = asset_data.get('asset_id', '')

                # asset_identifier is in format: contract_id::asset_name
                if '::' not in asset_identifier:
                    continue

                contract_id, asset_name = asset_identifier.split('::', 1)
                raw_amount = int(asset_data.get('amount', '0'))

                if raw_amount == 0:
                    continue

                sender = asset_data.get('sender', '')
                recipient = asset_data.get('recipient', '')

                # Handle mints (sender is empty) and burns (recipient is empty)
                if not sender and not recipient:
                    continue

                # Fetch token metadata from Hiro API for proper name/symbol
                metadata = self.node_inquirer.api_client.get_token_metadata(contract_id)

                # Get or create the token
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
                    log.error(
                        f'Failed to load SIP-10 token {contract_id} in transaction '
                        f'{transaction.tx_id} due to {e}',
                    )
                    continue

                # Calculate amount with proper decimals
                decimals = getattr(token.resolve_to_crypto_asset(), 'decimals', None) or 0
                amount = FVal(raw_amount) / (10 ** decimals)
                symbol = token.resolve_to_asset_with_symbol().symbol

                # Handle mints (receiving new tokens with no sender)
                if not sender and recipient:
                    if not self.base.is_tracked(recipient):
                        continue
                    events.append(self.base.make_event_next_index(
                        tx_ref=transaction.tx_id,
                        timestamp=transaction.block_time,
                        event_type=HistoryEventType.RECEIVE,
                        event_subtype=HistoryEventSubType.NONE,
                        asset=token,
                        amount=amount,
                        location_label=recipient,
                        notes=f'Receive {amount} {symbol} from mint',
                        counterparty=None,
                        address=contract_id,
                    ))
                    continue

                # Handle burns (sending tokens with no recipient)
                if sender and not recipient:
                    if not self.base.is_tracked(sender):
                        continue
                    events.append(self.base.make_event_next_index(
                        tx_ref=transaction.tx_id,
                        timestamp=transaction.block_time,
                        event_type=HistoryEventType.SPEND,
                        event_subtype=HistoryEventSubType.NONE,
                        asset=token,
                        amount=amount,
                        location_label=sender,
                        notes=f'Burn {amount} {symbol}',
                        counterparty=None,
                        address=contract_id,
                    ))
                    continue

                # Regular transfer
                from_address = StacksAddress(sender)
                to_address = StacksAddress(recipient)

                if (direction_result := self.base.decode_direction(
                        from_address=from_address,
                        to_address=to_address,
                )) is None:
                    continue

                (
                    event_type,
                    event_subtype,
                    location_label,
                    address,
                    counterparty,
                    verb,
                ) = direction_result
                counterparty_or_address = counterparty or address
                preposition = 'to' if event_type in OUTGOING_EVENT_TYPES else 'from'

                events.append(self.base.make_event_next_index(
                    tx_ref=transaction.tx_id,
                    timestamp=transaction.block_time,
                    event_type=event_type,
                    event_subtype=event_subtype,
                    asset=token,
                    amount=amount,
                    location_label=location_label,
                    notes=f'{verb} {amount} {symbol} {preposition} {counterparty_or_address}',
                    counterparty=counterparty,
                    address=address,
                ))

            except (KeyError, ValueError, TypeError) as e:
                log.error(f'Failed to decode token transfer in {transaction.tx_id}: {e}')
                continue

        return events

    def _maybe_decode_stx_events(
            self,
            transaction: StacksTransaction,
            stx_events: list[dict],
    ) -> list[StacksEvent]:
        """Decode STX transfers within contract calls.

        The Hiro API returns STX events with structure:
        {
            "event_type": "stx_asset",
            "asset": {
                "asset_event_type": "transfer" | "mint" | "burn",
                "sender": "SP..." | "",
                "recipient": "SP..." | "",
                "amount": "12345"  # in microSTX
            }
        }
        """
        events: list[StacksEvent] = []

        for event in stx_events:
            try:
                asset_data = event.get('asset', {})
                raw_amount = int(asset_data.get('amount', '0'))

                if raw_amount == 0:
                    continue

                sender = asset_data.get('sender', '')
                recipient = asset_data.get('recipient', '')

                if not sender and not recipient:
                    continue

                amount = micro_stx_to_stx(raw_amount)

                # Handle STX mints (receiving STX from contract with no sender)
                if not sender and recipient:
                    if not self.base.is_tracked(recipient):
                        continue
                    events.append(self.base.make_event_next_index(
                        tx_ref=transaction.tx_id,
                        timestamp=transaction.block_time,
                        event_type=HistoryEventType.RECEIVE,
                        event_subtype=HistoryEventSubType.NONE,
                        asset=A_STX,
                        amount=amount,
                        location_label=recipient,
                        notes=f'Receive {amount} STX',
                        counterparty=None,
                        address=None,
                    ))
                    continue

                # Handle STX burns (sending STX to contract with no recipient)
                if sender and not recipient:
                    if not self.base.is_tracked(sender):
                        continue
                    events.append(self.base.make_event_next_index(
                        tx_ref=transaction.tx_id,
                        timestamp=transaction.block_time,
                        event_type=HistoryEventType.SPEND,
                        event_subtype=HistoryEventSubType.NONE,
                        asset=A_STX,
                        amount=amount,
                        location_label=sender,
                        notes=f'Spend {amount} STX',
                        counterparty=None,
                        address=None,
                    ))
                    continue

                # Regular STX transfer
                from_address = StacksAddress(sender)
                to_address = StacksAddress(recipient)

                if (direction_result := self.base.decode_direction(
                        from_address=from_address,
                        to_address=to_address,
                )) is None:
                    continue

                (
                    event_type,
                    event_subtype,
                    location_label,
                    address,
                    counterparty,
                    verb,
                ) = direction_result
                counterparty_or_address = counterparty or address
                preposition = 'to' if event_type in OUTGOING_EVENT_TYPES else 'from'

                events.append(self.base.make_event_next_index(
                    tx_ref=transaction.tx_id,
                    timestamp=transaction.block_time,
                    event_type=event_type,
                    event_subtype=event_subtype,
                    asset=A_STX,
                    amount=amount,
                    location_label=location_label,
                    notes=f'{verb} {amount} STX {preposition} {counterparty_or_address}',
                    counterparty=counterparty,
                    address=address,
                ))

            except (KeyError, ValueError, TypeError) as e:
                log.error(f'Failed to decode STX event in {transaction.tx_id}: {e}')
                continue

        return events

    def _fetch_token_transfers(self, tx_id: str) -> tuple[list[dict], list[dict]]:
        """Fetch token transfer events for a transaction from the API.

        Returns:
            Tuple of (fungible_token_events, stx_events)
        """
        try:
            events = self.node_inquirer.api_client.get_transaction_events(tx_id)
        except RemoteError as e:
            log.error(f'Failed to fetch token transfers for {tx_id}: {e}')
            return [], []

        ft_events = []
        stx_events = []
        for event in events:
            event_type = event.get('event_type')
            if event_type == 'fungible_token_asset':
                ft_events.append(event)
            elif event_type == 'stx_asset':
                stx_events.append(event)
        return ft_events, stx_events

    def _apply_protocol_decoders(
            self,
            transaction: StacksTransaction,
            events: list[StacksEvent],
    ) -> None:
        """Apply protocol-specific decoders to enhance events.

        Checks if the transaction involves known protocols and applies
        the appropriate decoder to enrich the event information.
        """
        # sBTC bridge operations
        if is_sbtc_transaction(transaction):
            additional = decode_sbtc_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Allbridge bridge operations (aeUSDC, aeETH)
        elif is_allbridge_transaction(transaction):
            additional = decode_allbridge_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Circle USDCx bridge operations
        elif is_usdcx_transaction(transaction):
            additional = decode_usdcx_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # PoX stacking operations
        elif is_pox_transaction(transaction):
            additional = decode_pox_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # StackingDAO liquid staking operations
        elif is_stackingdao_transaction(transaction):
            additional = decode_stackingdao_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Third-party stacking pools (Fastpool, Xverse, etc.)
        elif is_stacking_pool_transaction(transaction):
            additional = decode_stacking_pool_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Send-many batched transfers
        elif is_sendmany_transaction(transaction):
            additional = decode_sendmany_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # ALEX DEX operations
        elif is_alex_transaction(transaction):
            additional = decode_alex_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Velar DEX operations
        elif is_velar_transaction(transaction):
            additional = decode_velar_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Bitflow DEX operations
        elif is_bitflow_transaction(transaction):
            additional = decode_bitflow_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Zest lending operations
        elif is_zest_transaction(transaction):
            additional = decode_zest_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Hermetica synthetic assets operations
        elif is_hermetica_transaction(transaction):
            additional = decode_hermetica_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Arkadiko CDP protocol operations
        elif is_arkadiko_transaction(transaction):
            additional = decode_arkadiko_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

        # Dual Stacking operations
        elif is_dual_stacking_transaction(transaction):
            additional = decode_dual_stacking_events(
                transaction=transaction,
                base_tools=self.base,
                existing_events=events,
            )
            events.extend(additional)

    def _decode_transaction(
            self,
            transaction: StacksTransaction,
    ) -> tuple[list[StacksEvent], bool, set[str] | None]:
        """Decode a Stacks transaction and save to DB."""
        log.debug(f'Starting decoding of Stacks transaction {transaction.tx_id}')

        with self.database.conn.write_ctx() as write_cursor:
            tx_id = transaction.get_or_query_db_id(write_cursor)

        self.base.reset_sequence_counter(tx_data=transaction)
        events: list[StacksEvent] = []

        # Decode fee event
        if (fee_event := self._maybe_decode_fee_event(transaction=transaction)) is not None:
            events.append(fee_event)

        # Decode STX transfer
        if (stx_transfer_event := self._maybe_decode_stx_transfer(
            transaction=transaction,
        )) is not None:
            events.append(stx_transfer_event)

        # For contract calls, fetch and decode token transfers and STX events
        if transaction.tx_type == StacksTxType.CONTRACT_CALL:
            token_transfers, stx_events = self._fetch_token_transfers(transaction.tx_id)

            # Decode SIP-10 token transfers
            if token_transfers:
                token_events = self._maybe_decode_token_transfer(
                    transaction=transaction,
                    token_transfers=token_transfers,
                )
                events.extend(token_events)

            # Decode STX transfers within contract calls
            if stx_events:
                stx_transfer_events = self._maybe_decode_stx_events(
                    transaction=transaction,
                    stx_events=stx_events,
                )
                events.extend(stx_transfer_events)

            # Apply protocol-specific decoders
            self._apply_protocol_decoders(transaction, events)

        # Sort events by sequence index
        events = sorted(events, key=lambda x: x.sequence_index, reverse=False)

        self._write_new_tx_events_to_the_db(
            events=events,
            action_id=transaction.tx_id,
            db_id=tx_id,
        )

        return events, False, None

    def _create_swap_event(
            self,
            trade_event: StacksEvent,
            spend_event: StacksEvent,
            sequence_index: int,
            event_type: HistoryEventType,
    ) -> StacksEvent:
        """Creates a StacksEvent from trade event data."""
        # For now, we return the trade_event as-is since Stacks doesn't have
        # a separate swap event type yet
        return StacksEvent(
            tx_ref=trade_event.tx_ref,
            sequence_index=sequence_index,
            timestamp=trade_event.timestamp,
            event_type=event_type,
            event_subtype=trade_event.event_subtype,
            asset=trade_event.asset,
            amount=trade_event.amount,
            notes=trade_event.notes,
            extra_data=trade_event.extra_data,
            location_label=(
                trade_event.location_label
                if trade_event.location_label is not None
                else spend_event.location_label
            ),
            counterparty=spend_event.counterparty,
            address=spend_event.address,
        )
