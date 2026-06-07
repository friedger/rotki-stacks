"""Tests for Stacks blockchain types and validation - Phase 1."""
from rotkehlchen.chain.stacks.validation import (
    ALL_PREFIXES,
    C32_ALPHABET,
    MAINNET_PREFIX,
    MAINNET_PREFIXES,
    TESTNET_PREFIX,
    TESTNET_PREFIXES,
    is_valid_stacks_address,
)
from rotkehlchen.constants.assets import A_STX
from rotkehlchen.types import (
    BLOCKCHAIN_LOCATIONS,
    CHAINS_WITH_CHAIN_MANAGER,
    STACKS_TOKEN_KINDS,
    AddressbookEntry,
    ChainType,
    Location,
    StacksAddress,
    SupportedBlockchain,
    TokenKind,
)


class TestStacksAddressValidation:
    """Tests for Stacks address validation."""

    def test_valid_mainnet_addresses(self) -> None:
        """Test that valid mainnet addresses are accepted."""
        valid_addresses = [
            'SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7',
            'SP000000000000000000002Q6VF78',  # PoX contract address (shorter)
            'SP3K8BC0PPEVCV7NZ6QSRWPQ2JE9E5B6N3PA0KBR9',  # sBTC registry
            'SM3KNVZS30WM7F89SXKVVFY4SN9RMPZZ9FX929N0V',  # LISA contract (SM prefix)
        ]
        for address in valid_addresses:
            assert is_valid_stacks_address(address), f'Expected {address} to be valid'

    def test_valid_testnet_addresses(self) -> None:
        """Test that valid testnet addresses are accepted."""
        valid_addresses = [
            'ST2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRVF5T9',
            'ST000000000000000000002AMW42H',  # Testnet PoX
        ]
        for address in valid_addresses:
            assert is_valid_stacks_address(address), f'Expected {address} to be valid'

    def test_invalid_prefix(self) -> None:
        """Test that addresses with invalid prefixes are rejected."""
        invalid_addresses = [
            'SX2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7',  # SX prefix
            'AB2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7',  # AB prefix
            '0x2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7',  # EVM-style prefix
        ]
        for address in invalid_addresses:
            assert not is_valid_stacks_address(address), f'Expected {address} to be invalid'

    def test_invalid_length(self) -> None:
        """Test that addresses with invalid length are rejected."""
        invalid_addresses = [
            'SP123',  # Too short
            'SP12',  # Way too short
            '',  # Empty
            'SP' + 'A' * 50,  # Too long
        ]
        for address in invalid_addresses:
            assert not is_valid_stacks_address(address), f'Expected {address} to be invalid'

    def test_invalid_c32_characters(self) -> None:
        """Test that addresses with invalid c32 characters are rejected.

        c32 alphabet excludes: I, L, O, U (to avoid visual confusion)
        """
        # Replace valid characters with excluded ones
        base_address = 'SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7'
        for invalid_char in ['I', 'L', 'O', 'U']:
            # Replace a character with an invalid one
            invalid_address = base_address[:5] + invalid_char + base_address[6:]
            assert not is_valid_stacks_address(invalid_address), \
                f'Expected address with {invalid_char} to be invalid'

    def test_non_string_input(self) -> None:
        """Test that non-string inputs are rejected."""
        assert not is_valid_stacks_address(None)
        assert not is_valid_stacks_address(12345)
        assert not is_valid_stacks_address(['SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7'])

    def test_c32_alphabet_completeness(self) -> None:
        """Test that the c32 alphabet is correct."""
        expected = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
        assert expected == C32_ALPHABET
        assert 'I' not in C32_ALPHABET
        assert 'L' not in C32_ALPHABET
        assert 'O' not in C32_ALPHABET
        assert 'U' not in C32_ALPHABET

    def test_prefix_constants(self) -> None:
        """Test that prefix constants are correct."""
        assert MAINNET_PREFIX == 'SP'
        assert TESTNET_PREFIX == 'ST'
        assert MAINNET_PREFIXES == ('SP', 'SM')
        assert TESTNET_PREFIXES == ('ST', 'SN')
        assert ALL_PREFIXES == ('SP', 'SM', 'ST', 'SN')


class TestStacksTypeRegistration:
    """Tests for Stacks type registration in rotkehlchen.types."""

    def test_supported_blockchain_enum(self) -> None:
        """Test that STACKS is properly registered in SupportedBlockchain."""
        assert hasattr(SupportedBlockchain, 'STACKS')
        assert SupportedBlockchain.STACKS.value == 'STX'
        assert str(SupportedBlockchain.STACKS) == 'Stacks'
        assert SupportedBlockchain.STACKS.serialize() == 'stx'

    def test_location_enum(self) -> None:
        """Test that STACKS is properly registered in Location."""
        assert hasattr(Location, 'STACKS')
        assert Location.STACKS.value == 60  # After GATE = 59 (HYPERLIQUID/MONAD/GATE = 57/58/59)
        assert Location.STACKS in BLOCKCHAIN_LOCATIONS

    def test_chain_type_enum(self) -> None:
        """Test that STACKS is properly registered in ChainType."""
        assert hasattr(ChainType, 'STACKS')
        assert SupportedBlockchain.STACKS.get_chain_type() == ChainType.STACKS

    def test_token_kinds(self) -> None:
        """Test that SIP10 token kinds are properly registered."""
        assert hasattr(TokenKind, 'SIP010_FUNGIBLE')
        assert hasattr(TokenKind, 'SIP009_NFT')
        assert TokenKind.SIP010_FUNGIBLE in STACKS_TOKEN_KINDS
        assert TokenKind.SIP009_NFT in STACKS_TOKEN_KINDS

    def test_chains_with_chain_manager(self) -> None:
        """Test that STACKS is in CHAINS_WITH_CHAIN_MANAGER."""
        # CHAINS_WITH_CHAIN_MANAGER is a union of Literal types
        # We need to recursively extract all enum values
        from typing import Union, get_args, get_origin

        def extract_literal_values(type_hint: object) -> set[SupportedBlockchain]:
            """Recursively extract all values from nested Literal/Union types."""
            values: set[SupportedBlockchain] = set()
            origin = get_origin(type_hint)
            args = get_args(type_hint)

            if origin is Union:
                for arg in args:
                    values.update(extract_literal_values(arg))
            elif args:  # It's a Literal type
                for arg in args:
                    if isinstance(arg, SupportedBlockchain):
                        values.add(arg)
                    else:
                        values.update(extract_literal_values(arg))
            return values

        chains = extract_literal_values(CHAINS_WITH_CHAIN_MANAGER)
        assert SupportedBlockchain.STACKS in chains

    def test_native_token_id(self) -> None:
        """Test that the native token ID is correct."""
        assert SupportedBlockchain.STACKS.get_native_token_id() == 'STX'

    def test_image_name(self) -> None:
        """Test that the image name is correct."""
        assert SupportedBlockchain.STACKS.get_image_name() == 'stacks.svg'

    def test_address_chain_group(self) -> None:
        """Test that the address chain group is correct."""
        assert SupportedBlockchain.STACKS.get_address_chain_group() == ChainType.STACKS

    def test_location_from_chain(self) -> None:
        """Test that Location.from_chain works for STACKS."""
        # We need to update OTHER_CHAINS_WITH_TRANSACTIONS first, but let's test the mapping
        assert Location.from_chain(SupportedBlockchain.STACKS) == Location.STACKS


class TestStacksAddressbookEcosystem:
    """Tests for Stacks address ecosystem detection."""

    def test_check_chain_ecosystem_stacks(self) -> None:
        """Test that Stacks addresses are detected as STACKS ecosystem."""
        stacks_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')
        ecosystem = AddressbookEntry.check_chain_ecosystem(stacks_address)
        assert ecosystem == ChainType.STACKS

    def test_ecosystem_isolation(self) -> None:
        """Test that Stacks addresses don't match other ecosystems."""
        stacks_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')
        ecosystem = AddressbookEntry.check_chain_ecosystem(stacks_address)

        # Should not be any other ecosystem
        assert ecosystem != ChainType.BITCOIN
        assert ecosystem != ChainType.EVMLIKE
        assert ecosystem != ChainType.SUBSTRATE
        assert ecosystem != ChainType.SOLANA


class TestStacksAssetConstant:
    """Tests for the A_STX asset constant."""

    def test_a_stx_exists(self) -> None:
        """Test that A_STX asset constant exists and is correct."""
        assert A_STX is not None
        assert A_STX.identifier == 'STX'


class TestStacksAddressType:
    """Tests for StacksAddress type."""

    def test_stacks_address_type_creation(self) -> None:
        """Test that StacksAddress type can be used."""
        address: StacksAddress = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')
        assert isinstance(address, str)
        assert address == 'SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7'


# Phase 2 Tests - API Client, Node Inquirer, Manager


class TestStacksConstants:
    """Tests for Stacks constants module."""

    def test_constants_exist(self) -> None:
        """Test that all constants are properly defined."""
        from rotkehlchen.chain.stacks.constants import (
            BACKOFF_MULTIPLIER,
            HIRO_API_BASE_URL,
            INITIAL_BACKOFF,
            MAX_RETRIES,
            STX_DECIMALS,
        )
        assert HIRO_API_BASE_URL == 'https://api.mainnet.hiro.so'
        assert INITIAL_BACKOFF == 4
        assert BACKOFF_MULTIPLIER == 2
        assert MAX_RETRIES == 3
        assert STX_DECIMALS == 6

    def test_micro_stx_to_stx_conversion(self) -> None:
        """Test microSTX to STX conversion."""
        from rotkehlchen.chain.stacks.constants import micro_stx_to_stx
        from rotkehlchen.fval import FVal

        # 1 STX = 1,000,000 microSTX
        assert micro_stx_to_stx(1_000_000) == FVal(1)
        assert micro_stx_to_stx(500_000) == FVal('0.5')
        assert micro_stx_to_stx(0) == FVal(0)
        assert micro_stx_to_stx(1) == FVal('0.000001')
        assert micro_stx_to_stx(123_456_789) == FVal('123.456789')


class TestStacksApiClient:
    """Tests for StacksApiClient."""

    def test_api_client_initialization(self) -> None:
        """Test API client can be initialized."""
        from rotkehlchen.chain.stacks.api_client import StacksApiClient

        # We can't create a real client without a DB, but we can import it
        assert StacksApiClient is not None

    def test_api_client_with_api_key(self) -> None:
        """Test API client retrieves API key from database."""
        from unittest.mock import MagicMock

        from rotkehlchen.chain.stacks.api_client import StacksApiClient
        from rotkehlchen.types import ApiKey, ExternalServiceApiCredentials

        mock_db = MagicMock()
        # Mock the database to return API credentials
        mock_db.get_external_service_credentials.return_value = ExternalServiceApiCredentials(
            service=MagicMock(),
            api_key=ApiKey('test-api-key'),
        )

        client = StacksApiClient(database=mock_db)
        # The API key is fetched dynamically from the database
        api_key = client._get_api_key()
        assert api_key == 'test-api-key'

    def test_api_client_without_api_key(self) -> None:
        """Test API client works without API key in database."""
        from unittest.mock import MagicMock

        from rotkehlchen.chain.stacks.api_client import StacksApiClient

        mock_db = MagicMock()
        # Mock the database to return no credentials
        mock_db.get_external_service_credentials.return_value = None

        client = StacksApiClient(database=mock_db)
        # No API key should be returned
        api_key = client._get_api_key()
        assert api_key is None
        assert 'x-api-key' not in client.session.headers


class TestStacksNodeInquirer:
    """Tests for StacksInquirer."""

    def test_inquirer_initialization(self) -> None:
        """Test node inquirer can be initialized."""
        from unittest.mock import MagicMock

        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(
            greenlet_manager=mock_gm,
            database=mock_db,
        )
        assert inquirer.blockchain == SupportedBlockchain.STACKS
        assert inquirer.api_client is not None

    def test_inquirer_with_empty_response(self) -> None:
        """Test inquirer handles empty API response."""
        from unittest.mock import MagicMock, patch

        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
        from rotkehlchen.fval import FVal

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)

        # Mock the API client to return empty response
        with patch.object(inquirer.api_client, 'get_account_balances', return_value={}):
            balance = inquirer.get_stx_balance(
                StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7'),
            )
            assert balance == FVal(0)

    def test_inquirer_with_balance_response(self) -> None:
        """Test inquirer parses STX balance from API response."""
        from unittest.mock import MagicMock, patch

        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
        from rotkehlchen.fval import FVal

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)

        # Mock response with 10 STX (10,000,000 microSTX)
        mock_response = {
            'stx': {
                'balance': '10000000',
                'total_sent': '0',
                'total_received': '10000000',
            },
            'fungible_tokens': {},
            'non_fungible_tokens': {},
        }

        with patch.object(inquirer.api_client, 'get_account_balances', return_value=mock_response):
            balance = inquirer.get_stx_balance(
                StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7'),
            )
            assert balance == FVal(10)


class TestStacksManager:
    """Tests for StacksManager."""

    def test_manager_initialization(self) -> None:
        """Test manager can be initialized."""
        from unittest.mock import MagicMock

        from rotkehlchen.chain.stacks.manager import StacksManager
        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)
        manager = StacksManager(node_inquirer=inquirer)

        assert manager.node_inquirer is inquirer
        assert manager.database is mock_db

    def test_manager_query_balances_empty(self) -> None:
        """Test manager handles empty address list."""
        from unittest.mock import MagicMock

        from rotkehlchen.chain.stacks.manager import StacksManager
        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)
        manager = StacksManager(node_inquirer=inquirer)

        balances = manager.query_balances([])
        assert balances == {}

    def test_manager_query_balances_with_address(self) -> None:
        """Test manager queries balances for addresses."""
        from unittest.mock import MagicMock, patch

        from rotkehlchen.chain.stacks.manager import StacksManager
        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
        from rotkehlchen.constants import DEFAULT_BALANCE_LABEL
        from rotkehlchen.fval import FVal

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)
        manager = StacksManager(node_inquirer=inquirer)

        # Mock response with 100 STX (100,000,000 microSTX)
        mock_response = {
            'stx': {'balance': '100000000'},
        }

        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')

        with (
            patch.object(inquirer, 'get_balances', return_value=mock_response),
            patch('rotkehlchen.inquirer.Inquirer.find_main_currency_price', return_value=FVal(1)),
        ):
            balances = manager.query_balances([test_address])

            assert test_address in balances
            assert A_STX in balances[test_address].assets
            stx_balance = balances[test_address].assets[A_STX][DEFAULT_BALANCE_LABEL]
            assert stx_balance.amount == FVal(100)
            assert stx_balance.value == FVal(100)

    def test_manager_query_transactions_stub(self) -> None:
        """Test that query_transactions is a no-op (Phase 4 feature)."""
        from unittest.mock import MagicMock

        from rotkehlchen.chain.stacks.manager import StacksManager
        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
        from rotkehlchen.types import Timestamp

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)
        manager = StacksManager(node_inquirer=inquirer)

        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')

        # Should not raise, just log and return
        manager.query_transactions(
            addresses=[test_address],
            from_timestamp=Timestamp(0),
            to_timestamp=Timestamp(1000),
        )


class TestStacksBlockchainAccountsIntegration:
    """Tests for BlockchainAccounts integration with Stacks."""

    def test_blockchain_accounts_has_stx_field(self) -> None:
        """Test that BlockchainAccounts has stx field."""
        from rotkehlchen.chain.accounts import BlockchainAccounts

        accounts = BlockchainAccounts()
        assert hasattr(accounts, 'stx')
        assert accounts.stx == ()

    def test_blockchain_accounts_get_stacks(self) -> None:
        """Test that BlockchainAccounts.get works for Stacks."""
        from rotkehlchen.chain.accounts import BlockchainAccounts

        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')
        accounts = BlockchainAccounts(stx=(test_address,))

        result = accounts.get(SupportedBlockchain.STACKS)
        assert result == (test_address,)

    def test_blockchain_accounts_add_stacks(self) -> None:
        """Test that BlockchainAccounts.add works for Stacks."""
        from rotkehlchen.chain.accounts import BlockchainAccounts

        accounts = BlockchainAccounts()
        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')

        accounts.add(SupportedBlockchain.STACKS, test_address)
        assert accounts.stx == (test_address,)

    def test_blockchain_accounts_remove_stacks(self) -> None:
        """Test that BlockchainAccounts.remove works for Stacks."""
        from rotkehlchen.chain.accounts import BlockchainAccounts

        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')
        accounts = BlockchainAccounts(stx=(test_address,))

        accounts.remove(SupportedBlockchain.STACKS, test_address)
        assert accounts.stx == ()


class TestStacksCuratedTokenMetadata:
    """Tests for curated Stacks token metadata - Phase 3."""

    def test_csv_file_exists(self) -> None:
        """Test that the Stacks tokens CSV file exists."""
        from pathlib import Path
        csv_path = (
            Path(__file__).resolve().parent.parent.parent / 'data' / 'stacks_tokens_data.csv'
        )
        assert csv_path.exists(), f'CSV file not found at {csv_path}'

    def test_curated_tokens_loaded(self) -> None:
        """Test that curated token metadata is loaded from CSV."""
        from rotkehlchen.chain.stacks.constants import CURATED_STACKS_TOKENS

        assert len(CURATED_STACKS_TOKENS) > 0
        # Check that sBTC mainnet contract is in the curated tokens
        assert 'SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token' in CURATED_STACKS_TOKENS

    def test_curated_tokens_lazy_loading(self) -> None:
        """Test that _load_curated_tokens properly loads from CSV."""
        from rotkehlchen.chain.stacks.constants import _load_curated_tokens

        tokens = _load_curated_tokens()
        assert len(tokens) > 0
        # Verify sBTC is present with correct data
        sbtc = tokens.get('SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token')
        assert sbtc is not None
        assert sbtc.name == 'sBTC'
        assert sbtc.symbol == 'sBTC'
        assert sbtc.decimals == 8

    def test_get_curated_token_metadata_sbtc(self) -> None:
        """Test getting metadata for sBTC token (mainnet contract)."""
        from rotkehlchen.chain.stacks.constants import get_curated_token_metadata

        metadata = get_curated_token_metadata(
            'SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token',
        )
        assert metadata is not None
        assert metadata.name == 'sBTC'
        assert metadata.symbol == 'sBTC'
        assert metadata.decimals == 8
        assert metadata.coingecko == 'sbtc-2'
        assert metadata.protocol == 'sbtc'

    def test_get_curated_token_metadata_ststx(self) -> None:
        """Test getting metadata for stSTX token (mainnet contract)."""
        from rotkehlchen.chain.stacks.constants import get_curated_token_metadata

        metadata = get_curated_token_metadata(
            'SP4SZE494VC2YC5JYG7AYFQ44F5Q4PYV7DVMDPBG.ststx-token',
        )
        assert metadata is not None
        assert metadata.name == 'Stacked STX'
        assert metadata.symbol == 'stSTX'
        assert metadata.decimals == 6
        assert metadata.coingecko == 'stacking-dao'
        assert metadata.protocol == 'stackingdao'

    def test_get_curated_token_metadata_unknown(self) -> None:
        """Test getting metadata for an unknown token returns None."""
        from rotkehlchen.chain.stacks.constants import get_curated_token_metadata

        metadata = get_curated_token_metadata('SP_UNKNOWN.unknown-token')
        assert metadata is None

    def test_stacks_token_metadata_namedtuple(self) -> None:
        """Test StacksTokenMetadata is a proper NamedTuple."""
        from rotkehlchen.chain.stacks.constants import StacksTokenMetadata

        metadata = StacksTokenMetadata(
            name='Test Token',
            symbol='TEST',
            decimals=6,
            coingecko='test-coin',
        )
        assert metadata.name == 'Test Token'
        assert metadata.symbol == 'TEST'
        assert metadata.decimals == 6
        assert metadata.coingecko == 'test-coin'
        assert metadata.cryptocompare is None  # default
        assert metadata.protocol is None  # default


class TestStacksTokenBalanceParsing:
    """Tests for SIP-10 token balance parsing in manager - Phase 3."""

    def test_manager_parses_fungible_tokens(self) -> None:
        """Test manager parses fungible token balances from API response."""
        from unittest.mock import MagicMock, patch

        from rotkehlchen.chain.stacks.manager import StacksManager
        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
        from rotkehlchen.constants import DEFAULT_BALANCE_LABEL
        from rotkehlchen.fval import FVal

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)
        manager = StacksManager(node_inquirer=inquirer)

        # Mock response with STX and a fungible token (sBTC)
        mock_response = {
            'stx': {'balance': '1000000'},  # 1 STX
            'fungible_tokens': {
                'SP3K8BC0PPEVCV7NZ6QSRWPQ2JE9E5B6N3PA0KBR9.sbtc-token::sbtc': {
                    'balance': '100000000',  # 1 sBTC (8 decimals)
                },
            },
        }

        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')

        # Create a mock token to return from get_or_create_stacks_token
        mock_token = MagicMock()
        mock_token.decimals = 8

        with (
            patch.object(inquirer, 'get_balances', return_value=mock_response),
            patch(
                'rotkehlchen.inquirer.Inquirer.find_main_currency_price',
                return_value=FVal(1),
            ),
            patch(
                'rotkehlchen.inquirer.Inquirer.find_main_currency_prices',
                return_value={mock_token: FVal(50000)},
            ),
            patch(
                'rotkehlchen.chain.stacks.manager.get_or_create_stacks_token',
                return_value=mock_token,
            ),
        ):
            balances = manager.query_balances([test_address])

            # Should have STX balance
            assert test_address in balances
            assert A_STX in balances[test_address].assets
            stx_balance = balances[test_address].assets[A_STX][DEFAULT_BALANCE_LABEL]
            assert stx_balance.amount == FVal(1)

            # Should have token balance
            assert mock_token in balances[test_address].assets
            token_balance = balances[test_address].assets[mock_token][DEFAULT_BALANCE_LABEL]
            assert token_balance.amount == FVal(1)  # 100000000 / 10^8 = 1
            assert token_balance.value == FVal(50000)  # 1 * 50000

    def test_manager_skips_zero_balance_tokens(self) -> None:
        """Test manager skips tokens with zero balance."""
        from unittest.mock import MagicMock, patch

        from rotkehlchen.chain.stacks.manager import StacksManager
        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
        from rotkehlchen.fval import FVal

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)
        manager = StacksManager(node_inquirer=inquirer)

        # Mock response with zero balance token
        mock_response = {
            'stx': {'balance': '0'},
            'fungible_tokens': {
                'SP_SOME_TOKEN.token::token': {
                    'balance': '0',
                },
            },
        }

        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')

        with (
            patch.object(inquirer, 'get_balances', return_value=mock_response),
            patch(
                'rotkehlchen.inquirer.Inquirer.find_main_currency_price',
                return_value=FVal(1),
            ),
        ):
            balances = manager.query_balances([test_address])

            # Should have empty balance sheet (no non-zero balances)
            # The defaultdict will create an entry but it should be empty
            assert test_address not in balances or len(balances[test_address].assets) == 0

    def test_manager_strips_asset_name_suffix(self) -> None:
        """Test manager correctly strips ::asset-name suffix from contract ID."""
        from unittest.mock import MagicMock, patch

        from rotkehlchen.chain.stacks.manager import StacksManager
        from rotkehlchen.chain.stacks.node_inquirer import StacksInquirer
        from rotkehlchen.fval import FVal

        mock_gm = MagicMock()
        mock_db = MagicMock()
        inquirer = StacksInquirer(greenlet_manager=mock_gm, database=mock_db)
        manager = StacksManager(node_inquirer=inquirer)

        # Track what contract_id was passed to get_or_create_stacks_token
        captured_contract_id = None

        def capture_contract_id(userdb, contract_id, **kwargs):
            nonlocal captured_contract_id
            captured_contract_id = contract_id
            mock_token = MagicMock()
            mock_token.decimals = 6
            return mock_token

        mock_response = {
            'stx': {'balance': '0'},
            'fungible_tokens': {
                'SP_CONTRACT.token-name::asset-name': {
                    'balance': '1000000',
                },
            },
        }

        test_address = StacksAddress('SP2J6ZY48GV1EZ5V2V5RB9MP66SW86PYKKNRV9EJ7')

        with (
            patch.object(inquirer, 'get_balances', return_value=mock_response),
            patch(
                'rotkehlchen.inquirer.Inquirer.find_main_currency_price',
                return_value=FVal(1),
            ),
            patch(
                'rotkehlchen.inquirer.Inquirer.find_main_currency_prices',
                return_value={},
            ),
            patch(
                'rotkehlchen.chain.stacks.manager.get_or_create_stacks_token',
                side_effect=capture_contract_id,
            ),
        ):
            manager.query_balances([test_address])

            # Contract ID should have ::asset-name stripped
            assert captured_contract_id == 'SP_CONTRACT.token-name'
