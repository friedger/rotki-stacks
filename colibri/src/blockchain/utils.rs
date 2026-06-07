use alloy_primitives::Address;

#[derive(Debug, Clone, PartialEq)]
pub enum AssetAddress {
    Evm(Address),
    Solana(String),
    Stacks(String),
}

impl AssetAddress {
    /// Returns the address as a string, lowercased for EVM addresses
    pub fn as_str(&self) -> String {
        match self {
            AssetAddress::Evm(address) => address.to_string().to_ascii_lowercase(),
            AssetAddress::Solana(address) => address.clone(),
            AssetAddress::Stacks(address) => address.clone(),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct AssetIdentifier {
    pub chain_id: u64,
    pub contract_address: AssetAddress,
    pub token_id: Option<String>,
}

// Solana mainnet chain ID as used by smoldapp
const SOLANA_CHAIN_ID: u64 = 1151111081099710;
const SOLANA_ADDRESS_MIN_LENGTH: usize = 32;
const SOLANA_ADDRESS_MAX_LENGTH: usize = 44;

/// Parses an asset identifier supporting EVM, Solana, and Stacks formats:
/// - EVM: "eip155:{chain_id}/{asset_type}:{contract_address}[/{token_id}]"
/// - Solana: "solana/{asset_type}:{contract_address}"
/// - Stacks (CAIP-19): "stacks:{chain_id}/{sip010|sip009}:{address}.{contract}.{asset_name}"
///
/// Examples:
///   - "eip155:1/erc20:0x6B175474E89094C44Da98b954EedeAC495271d0F" (ERC-20 token)
///   - "eip155:1/erc721:0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D/1" (ERC-721 NFT with token ID)
///   - "solana/token:So11111111111111111111111111111111111111112" (Solana SPL token)
///   - "solana/nft:7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU" (Solana NFT)
///   - "stacks:1/sip010:SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token.sbtc-token" (SIP-010)
///
/// Returns None if the format is invalid or any required component is missing.
pub fn parse_asset_identifier(identifier: &str) -> Option<AssetIdentifier> {
    let parts: Vec<&str> = identifier.split('/').collect();
    if parts.len() < 2 {
        return None;
    }

    let blockchain_part = parts[0];
    if blockchain_part.starts_with("eip155:") {
        parse_evm_identifier(&parts)
    } else if blockchain_part == "solana" {
        parse_solana_identifier(&parts)
    } else if blockchain_part.starts_with("stacks:") {
        parse_stacks_identifier(&parts)
    } else {
        None
    }
}

/// Parse EVM (EIP-155) asset identifier
fn parse_evm_identifier(parts: &[&str]) -> Option<AssetIdentifier> {
    // Extract chain ID from "eip155:1" format
    let chain_parts: Vec<&str> = parts[0].splitn(2, ':').collect();
    debug_assert_eq!(chain_parts.len(), 2);
    debug_assert_eq!(chain_parts[0], "eip155");

    let chain_id = chain_parts[1].parse::<u64>().ok()?;

    // Parse asset type and contract address from "erc20:0x..." format
    let asset_parts: Vec<&str> = parts[1].splitn(2, ':').collect();
    if asset_parts.len() != 2 {
        return None;
    }

    let contract_address_str = asset_parts[1];
    if contract_address_str.is_empty() {
        return None;
    }

    let contract_address = Address::parse_checksummed(contract_address_str, None).ok()?;
    let token_id = parts.get(2).map(|s| s.to_string());

    Some(AssetIdentifier {
        chain_id,
        contract_address: AssetAddress::Evm(contract_address),
        token_id,
    })
}

/// Parse Solana asset identifier
fn parse_solana_identifier(parts: &[&str]) -> Option<AssetIdentifier> {
    // Parse asset type and contract address from "token:So11..." format
    let asset_parts: Vec<&str> = parts[1].splitn(2, ':').collect();
    if asset_parts.len() != 2 {
        return None;
    }
    if !matches!(asset_parts[0], "token" | "nft") {
        return None;
    }

    // Validate Solana address format - base58 encoded, 32-44 characters
    let contract_address = asset_parts[1];
    if contract_address.is_empty()
        || contract_address.len() < SOLANA_ADDRESS_MIN_LENGTH
        || contract_address.len() > SOLANA_ADDRESS_MAX_LENGTH
    {
        return None;
    }

    Some(AssetIdentifier {
        chain_id: SOLANA_CHAIN_ID,
        contract_address: AssetAddress::Solana(contract_address.to_string()),
        token_id: None, // we don't need it for solana
    })
}

// Stacks contract principal minimum length (e.g., SP + 38 chars)
const STACKS_ADDRESS_MIN_LENGTH: usize = 39;
// Stacks contract principal maximum length (address.contract-name)
const STACKS_ADDRESS_MAX_LENGTH: usize = 128;

/// Parse a Stacks CAIP-19 asset identifier
/// Format: "stacks:{chain_id}/{sip010|sip009}:{address}.{contract}.{asset_name}[/{nft_id}]"
/// (https://github.com/ChainAgnostic/namespaces/blob/main/stacks/caip19.md)
/// Examples:
///   - "stacks:1/sip010:SP3K8BC0PPEVCV7NZ6QSRWPQ2JE9E5B6N3PA0KBR9.token-abtc.bridged-btc"
///   - "stacks:1/sip010:SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token.sbtc-token"
fn parse_stacks_identifier(parts: &[&str]) -> Option<AssetIdentifier> {
    // parts[0] = "stacks:{chain_id}"
    let chain_parts: Vec<&str> = parts[0].splitn(2, ':').collect();
    if chain_parts.len() != 2 {
        return None;
    }
    let chain_id = chain_parts[1].parse::<u64>().ok()?;

    // parts[1] = "{sip010|sip009}:{address}.{contract}.{asset_name}"
    let asset_parts: Vec<&str> = parts[1].splitn(2, ':').collect();
    if asset_parts.len() != 2 {
        return None;
    }
    // Valid Stacks asset namespaces (SIP-010 fungible, SIP-009 NFT)
    if !matches!(asset_parts[0], "sip010" | "sip009") {
        return None;
    }

    // The asset reference is "{address}.{contract}.{asset_name}". Strip the trailing
    // asset name to get the contract principal "{address}.{contract}" that Hiro expects.
    let (contract_principal, _asset_name) = asset_parts[1].rsplit_once('.')?;

    // Validate Stacks contract principal format
    if contract_principal.is_empty()
        || contract_principal.len() < STACKS_ADDRESS_MIN_LENGTH
        || contract_principal.len() > STACKS_ADDRESS_MAX_LENGTH
    {
        return None;
    }

    // Validate that it starts with a valid Stacks address prefix (SP or SM for mainnet)
    if !contract_principal.starts_with("SP") && !contract_principal.starts_with("SM") {
        return None;
    }

    Some(AssetIdentifier {
        chain_id,
        contract_address: AssetAddress::Stacks(contract_principal.to_string()),
        token_id: parts.get(2).map(|s| s.to_string()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use alloy_primitives::address;

    #[test]
    fn test_parse_asset_identifier_valid() {
        // Test ERC-20 format
        let erc20 = "eip155:1/erc20:0x6B175474E89094C44Da98b954EedeAC495271d0F";
        let expected_erc20 = AssetIdentifier {
            chain_id: 1,
            contract_address: AssetAddress::Evm(address!(
                "0x6B175474E89094C44Da98b954EedeAC495271d0F"
            )),
            token_id: None,
        };
        assert_eq!(parse_asset_identifier(erc20), Some(expected_erc20));

        // Test ERC-721 format
        let erc721 = "eip155:1/erc721:0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D/1";
        let expected_erc721 = AssetIdentifier {
            chain_id: 1,
            contract_address: AssetAddress::Evm(address!(
                "0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D"
            )),
            token_id: Some("1".to_string()),
        };
        assert_eq!(parse_asset_identifier(erc721), Some(expected_erc721));

        // Test Solana token format
        let solana_token = "solana/token:So11111111111111111111111111111111111111112";
        let expected_solana_token = AssetIdentifier {
            chain_id: SOLANA_CHAIN_ID,
            contract_address: AssetAddress::Solana(
                "So11111111111111111111111111111111111111112".to_string(),
            ),
            token_id: None,
        };
        assert_eq!(
            parse_asset_identifier(solana_token),
            Some(expected_solana_token)
        );

        // Test Solana NFT format
        let solana_nft = "solana/nft:7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU";
        let expected_solana_nft = AssetIdentifier {
            chain_id: SOLANA_CHAIN_ID,
            contract_address: AssetAddress::Solana(
                "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU".to_string(),
            ),
            token_id: None,
        };
        assert_eq!(
            parse_asset_identifier(solana_nft),
            Some(expected_solana_nft)
        );

        // Test Stacks SIP-010 fungible token format (CAIP-19)
        let stacks_sip10 =
            "stacks:1/sip010:SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token.sbtc-token";
        let expected_stacks_sip10 = AssetIdentifier {
            chain_id: 1,
            contract_address: AssetAddress::Stacks(
                "SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token".to_string(),
            ),
            token_id: None,
        };
        assert_eq!(
            parse_asset_identifier(stacks_sip10),
            Some(expected_stacks_sip10)
        );

        // Test Stacks SIP-010 fungible token format with SP prefix (CAIP-19)
        let stacks_sp =
            "stacks:1/sip010:SP4SZE494VC2YC5JYG7AYFQ44F5Q4PYV7DVMDPBG.ststx-token.ststx";
        let expected_stacks_sp = AssetIdentifier {
            chain_id: 1,
            contract_address: AssetAddress::Stacks(
                "SP4SZE494VC2YC5JYG7AYFQ44F5Q4PYV7DVMDPBG.ststx-token".to_string(),
            ),
            token_id: None,
        };
        assert_eq!(parse_asset_identifier(stacks_sp), Some(expected_stacks_sp));
    }

    #[test]
    fn test_parse_asset_identifier_invalid() {
        // Missing prefix
        assert_eq!(
            parse_asset_identifier("1/erc20:0x6B175474E89094C44Da98b954EedeAC495271d0F"),
            None
        );

        // Invalid prefix
        assert_eq!(
            parse_asset_identifier("eip123:1/erc20:0x6B175474E89094C44Da98b954EedeAC495271d0F"),
            None
        );

        // Invalid chain ID
        assert_eq!(
            parse_asset_identifier("eip155:abc/erc20:0x6B175474E89094C44Da98b954EedeAC495271d0F"),
            None
        );

        // Missing asset type
        assert_eq!(
            parse_asset_identifier("eip155:1:0x6B175474E89094C44Da98b954EedeAC495271d0F"),
            None
        );

        // Missing contract address
        assert_eq!(parse_asset_identifier("eip155:1/erc20:"), None);

        // Empty string
        assert_eq!(parse_asset_identifier(""), None);

        // Too few parts
        assert_eq!(parse_asset_identifier("eip155:1"), None);

        // Invalid hex address
        assert_eq!(
            parse_asset_identifier("eip155:1/erc20:0xInvalidAddress"),
            None
        );

        // Invalid Solana asset type
        assert_eq!(
            parse_asset_identifier("solana/invalid:So11111111111111111111111111111111111111112"),
            None
        );

        // Solana address too short
        assert_eq!(parse_asset_identifier("solana/token:short"), None);

        // Solana address too long
        assert_eq!(
            parse_asset_identifier(
                "solana/token:ThisAddressIsTooLongForSolanaValidation12345678901234567890"
            ),
            None
        );

        // Missing Solana address
        assert_eq!(parse_asset_identifier("solana/token:"), None);

        // Invalid Stacks asset type
        assert_eq!(
            parse_asset_identifier(
                "stacks/invalid:SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token"
            ),
            None
        );

        // Stacks contract principal too short
        assert_eq!(parse_asset_identifier("stacks:1/sip010:SP123.tok.tok"), None);

        // Stacks contract principal with wrong prefix
        assert_eq!(
            parse_asset_identifier(
                "stacks:1/sip010:XX3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token.sbtc-token"
            ),
            None
        );

        // Missing asset reference
        assert_eq!(parse_asset_identifier("stacks:1/sip010:"), None);

        // Unknown asset namespace (not sip010/sip009)
        assert_eq!(
            parse_asset_identifier(
                "stacks:1/sip999:SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token.sbtc-token"
            ),
            None
        );

        // Old (pre-CAIP-19) format is no longer accepted
        assert_eq!(
            parse_asset_identifier(
                "stacks/sip10_fungible:SM3VDXK3WZZSA84XXFKAFAF15NNZX32CTSG82JFQ4.sbtc-token"
            ),
            None
        );
    }
}
