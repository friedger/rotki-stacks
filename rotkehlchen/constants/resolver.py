from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.serialization.deserialize import deserialize_evm_address
from rotkehlchen.types import (
    EVM_TOKEN_KINDS_TYPE,
    SOLANA_TOKEN_KINDS_TYPE,
    STACKS_TOKEN_KINDS_TYPE,
    ChainID,
    ChecksumEvmAddress,
    SolanaAddress,
    StacksAddress,
    TokenKind,
)

ETHEREUM_DIRECTIVE = '_ceth_'
ETHEREUM_DIRECTIVE_LENGTH = len(ETHEREUM_DIRECTIVE)
EVM_CHAIN_DIRECTIVE = 'eip155'
SOLANA_CHAIN_DIRECTIVE = 'solana'
STACKS_CHAIN_DIRECTIVE = 'stacks'
STACKS_MAINNET_CHAIN_ID = 1  # CAIP-2 chain reference for Stacks mainnet
STACKS_TESTNET_CHAIN_ID = 2147483648  # CAIP-2 chain reference for Stacks testnet


def evm_address_to_identifier(
        address: str,
        chain_id: ChainID,
        token_type: EVM_TOKEN_KINDS_TYPE = TokenKind.ERC20,
        collectible_id: str | None = None,
) -> str:
    """Format EVM token information into the CAIPs identifier format"""
    ident = f'{EVM_CHAIN_DIRECTIVE}:{chain_id.value}/{token_type!s}:{address}'
    if collectible_id is not None:
        return ident + f'/{collectible_id}'
    return ident


def _split_evm_identifier(identifier: str) -> tuple[str, str, str] | None:
    """Split a CAIPs identifier on `:` and return its three substrings or None if it is invalid."""
    if len(parts := identifier.split(':')) != 3 or parts[0] != EVM_CHAIN_DIRECTIVE:
        return None

    return tuple(parts)  # type: ignore[return-value]  # Checked the len above, will be 3 items.


def identifier_to_evm_address(identifier: str) -> ChecksumEvmAddress | None:
    """Parse CAIPs identifier format and return the EVM address or None on error."""
    if (parts := _split_evm_identifier(identifier)) is None:
        return None

    try:
        return deserialize_evm_address(parts[2].split('/')[0])  # Don't include the token id for erc721  # noqa: E501
    except DeserializationError:
        return None


def identifier_to_evm_chain(identifier: str) -> ChainID | None:
    """Parse CAIPs identifier format and return the EVM chain or None on error."""
    if (parts := _split_evm_identifier(identifier)) is None:
        return None

    try:
        return ChainID.deserialize(int(parts[1].split('/')[0]))
    except (DeserializationError, TypeError, ValueError):
        return None


def tokenid_to_collectible_id(identifier: str) -> str | None:
    """Get erc721 collectible id from the asset identifier."""
    if 'erc721' not in identifier or len(id_parts := identifier.split('/')) != 3:
        return None

    return id_parts[-1]


def tokenid_belongs_to_collection(token_identifier: str, collection_identifier: str) -> bool:
    """Determine if an ERC721 token belongs to the specified collection.
    An ERC721 token's identifier is its token id appended to its collection identifier.
    Returns true if the token identifier starts with the collection identifier otherwise false.
    """
    return token_identifier.startswith(collection_identifier)


def ethaddress_to_identifier(address: ChecksumEvmAddress) -> str:
    return evm_address_to_identifier(
        address=str(address),
        chain_id=ChainID.ETHEREUM,
        token_type=TokenKind.ERC20,
    )


def strethaddress_to_identifier(address: str) -> str:
    return evm_address_to_identifier(
        address=str(address),
        chain_id=ChainID.ETHEREUM,
        token_type=TokenKind.ERC20,
    )


def solana_address_to_identifier(
        address: SolanaAddress,
        token_type: SOLANA_TOKEN_KINDS_TYPE = TokenKind.SPL_TOKEN,
) -> str:
    """Converts a Solana address and token type into a CAIP-19 identifier.

    Uses 'solana' prefix instead of full CAIP-2 chain reference to save database space.

    Example: SPL_TOKEN becomes 'solana/token:<address>'.
    See: https://namespaces.chainagnostic.org/solana/caip19
    """
    return f'{SOLANA_CHAIN_DIRECTIVE}/{str(token_type)[4:]}:{address}'


_STACKS_TOKEN_NAMESPACES: dict[STACKS_TOKEN_KINDS_TYPE, str] = {
    TokenKind.SIP010_FUNGIBLE: 'sip010',
    TokenKind.SIP009_NFT: 'sip009',
}


def stacks_contract_to_identifier(
        contract_id: StacksAddress,
        asset_name: str,
        token_type: STACKS_TOKEN_KINDS_TYPE = TokenKind.SIP010_FUNGIBLE,
        chain_id: int = STACKS_MAINNET_CHAIN_ID,
) -> str:
    """Format Stacks token information into the CAIP-19 identifier format.

    Follows https://github.com/ChainAgnostic/namespaces/blob/main/stacks/caip19.md
    e.g. stacks:1/sip010:SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token.sbtc-token

    Args:
        contract_id: The contract principal, i.e. {address}.{contract-name}
            (e.g. SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token)
        asset_name: The SIP-010/SIP-009 asset name defined in the contract (e.g. sbtc-token).
            This is the part after '::' in the asset id Hiro returns.
        token_type: The token kind (SIP010_FUNGIBLE or SIP009_NFT)
        chain_id: CAIP-2 chain reference (1 = mainnet, 2147483648 = testnet)

    Returns:
        CAIP-19 identifier 'stacks:{chain_id}/{namespace}:{contract_id}.{asset_name}'
    """
    namespace = _STACKS_TOKEN_NAMESPACES[token_type]
    return f'{STACKS_CHAIN_DIRECTIVE}:{chain_id}/{namespace}:{contract_id}.{asset_name}'


def _stacks_asset_reference(identifier: str) -> str | None:
    """Return the '{address}.{contract}.{asset_name}' reference of a CAIP-19 Stacks
    identifier (NFT token id stripped), or None if the identifier is not a Stacks one."""
    if not identifier.startswith(f'{STACKS_CHAIN_DIRECTIVE}:'):
        return None
    try:
        # stacks:{chain}/{namespace}:{address}.{contract}.{asset_name}[/{nft_id}]
        return identifier.split('/', 1)[1].split(':', 1)[1].split('/', 1)[0]
    except IndexError:
        return None


def identifier_to_stacks_contract(identifier: str) -> StacksAddress | None:
    """Parse a CAIP-19 Stacks identifier and return the contract ID ({address}.{contract})
    or None on error. The trailing '.{asset_name}' (and optional '/{nft_id}') are stripped."""
    if (asset_reference := _stacks_asset_reference(identifier)) is None:
        return None
    try:
        return StacksAddress(asset_reference.rsplit('.', 1)[0])  # drop trailing .asset_name
    except (ValueError, IndexError):
        return None


def identifier_to_stacks_asset_name(identifier: str) -> str | None:
    """Return the SIP-010/SIP-009 asset name component of a CAIP-19 Stacks identifier,
    or None on error."""
    if (asset_reference := _stacks_asset_reference(identifier)) is None:
        return None
    try:
        return asset_reference.rsplit('.', 1)[1]
    except IndexError:
        return None
