//! The shared Ryder wallet flow (ported verbatim from the `ryder-tauri-getversion` reference).
//! Given a synchronous transceiver, it builds a `Session` (reusing the nfc-tool's protocol stack),
//! reads the device version, pairs, opens the secure channel, reads the four public keys, and
//! derives their addresses. The ONLY platform-specific piece is the transceiver closure (here:
//! PC/SC, see `transport.rs`).

use std::path::Path;

use serde::Serialize;

use ryder_nfc_tool::{
    addresses,
    connection::{NfcConnection, VersionedConnection},
    logger::{Logger, Verbosity},
    nfc_protocol::{commands, Settings},
    pairing::PairedDevice,
    session::Session,
    types::{
        DerivationPath, EllipticCurve, KeyExportSettings, KeyType, PairRequestStatus,
        PairRequestType,
    },
    utils::ApduResponse,
    version_summary::DeviceVersionSummary,
};

#[derive(Serialize, Clone)]
pub struct ChainAddress {
    pub chain: String,
    pub symbol: String,
    pub path: String,
    pub address: String,
}

#[derive(Serialize, Clone)]
pub struct WalletData {
    pub version: DeviceVersionSummary,
    pub accounts: Vec<ChainAddress>,
}

enum Kind {
    Eth,
    Btc,
    Stx,
    Sol,
}

struct Spec {
    chain: &'static str,
    symbol: &'static str,
    path: &'static str,
    curve: EllipticCurve,
    kind: Kind,
}

fn specs() -> Vec<Spec> {
    vec![
        Spec { chain: "Bitcoin", symbol: "BTC", path: "m/84'/0'/0'/0/0", curve: EllipticCurve::Secp256k1, kind: Kind::Btc },
        Spec { chain: "Ethereum", symbol: "ETH", path: "m/44'/60'/0'/0/0", curve: EllipticCurve::Secp256k1, kind: Kind::Eth },
        Spec { chain: "Solana", symbol: "SOL", path: "m/44'/501'/0'/0'", curve: EllipticCurve::Ed25519, kind: Kind::Sol },
        Spec { chain: "Stacks", symbol: "STX", path: "m/44'/5757'/0'/0/0", curve: EllipticCurve::Secp256k1, kind: Kind::Stx },
    ]
}

/// Runs the full flow over the given transceiver. `data_dir` holds the app's pairing key.
pub fn run<F>(transceive: F, data_dir: &Path) -> Result<WalletData, String>
where
    F: FnMut(&[u8]) -> anyhow::Result<ApduResponse> + 'static,
{
    let key_path = data_dir.join("paired_device.toml");
    let _ = std::fs::create_dir_all(data_dir);
    let paired = if key_path.exists() {
        PairedDevice::load(&key_path).map_err(|e| format!("failed to load app key: {e}"))?
    } else {
        PairedDevice::new(None)
    };

    // Build a Session over the supplied transport. (Logging off.)
    let logger = Logger::new(Verbosity::new(0, 0));
    let mut conn = NfcConnection::new_with_transceiver(transceive, logger, 255);
    conn.connect_as_card_reader().map_err(|e| e.to_string())?;
    let versioned = VersionedConnection::new(conn).map_err(|e| e.to_string())?;
    let mut session = Session::new(versioned, Settings::default());

    // Version.
    let info = commands::get_version(&mut session).map_err(|e| format!("get version: {e}"))?;
    let version = DeviceVersionSummary::from(&info);

    // Pair (plaintext).
    let resp = commands::pair(
        &mut session,
        false,
        PairRequestType::Pair,
        "Ryder".to_string(),
        &paired.app_public_key(),
    )
    .map_err(|e| format!("pairing failed: {e}"))?;
    let status = PairRequestStatus::from_repr(resp.response_data[0])
        .ok_or_else(|| "invalid pairing status from device".to_string())?;
    let _ = paired.save(&key_path);
    match status {
        PairRequestStatus::Paired | PairRequestStatus::AlreadyPaired => {}
        PairRequestStatus::RequiresConfirmation => {
            return Err("Confirm the pairing on your Ryder One, then read again.".to_string());
        }
        other => return Err(format!("pairing rejected by device: {other:?}")),
    }

    // Secure channel, then read each key over it.
    let mut session = session
        .create_secure_channel(paired)
        .map_err(|e| format!("failed to open secure channel: {e}"))?;

    let mut accounts = Vec::new();
    for spec in specs() {
        let path: DerivationPath = spec
            .path
            .parse()
            .map_err(|e| format!("bad path {}: {e}", spec.path))?;
        let key = KeyExportSettings { path, key_type: KeyType::Normal, curve: spec.curve };
        let r = commands::get_public_key(&mut session, key, false)
            .map_err(|e| format!("failed to read {} key: {e}", spec.symbol))?;
        let pubkey = r.response_data;
        let address = match spec.kind {
            Kind::Eth => addresses::eth_address(&pubkey),
            Kind::Btc => addresses::btc_p2wpkh_address(&pubkey),
            Kind::Stx => addresses::stx_address(&pubkey),
            Kind::Sol => addresses::sol_address(&pubkey),
        }
        .map_err(|e| format!("failed to derive {} address: {e}", spec.symbol))?;
        accounts.push(ChainAddress {
            chain: spec.chain.to_string(),
            symbol: spec.symbol.to_string(),
            path: spec.path.to_string(),
            address,
        });
    }

    Ok(WalletData { version, accounts })
}
