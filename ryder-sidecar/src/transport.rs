//! The one platform-specific piece: a synchronous transceiver (send one APDU, get the response).
//! Desktop uses PC/SC. Everything above this — pairing, secure channel, commands — is shared
//! (see `flow.rs`). Ported from the `ryder-tauri-getversion` desktop transport.

use anyhow::{anyhow, Result};
use pcsc::{Card, Context, Protocols, Scope, ShareMode};
use ryder_nfc_tool::utils::ApduResponse;

pub struct PlatformTransport {
    _ctx: Context,
    card: Card,
}

impl PlatformTransport {
    pub fn transceive(&mut self, apdu: &[u8]) -> Result<ApduResponse> {
        let mut buf = vec![0u8; pcsc::MAX_BUFFER_SIZE];
        let resp = self
            .card
            .transmit(apdu, &mut buf)
            .map_err(|e| anyhow!("transmit failed: {e}"))?;
        Ok(ApduResponse::from(resp))
    }
}

/// Opens the first PC/SC reader that has a card present.
pub fn open_transport() -> Result<PlatformTransport, String> {
    let ctx = Context::establish(Scope::User)
        .map_err(|e| format!("PC/SC service unavailable: {e}"))?;
    let readers = ctx
        .list_readers_owned()
        .map_err(|e| format!("failed to list readers: {e}"))?;
    if readers.is_empty() {
        return Err(
            "No NFC reader found — plug in a PC/SC reader and place your Ryder One on it."
                .to_string(),
        );
    }
    let mut last_err = None;
    for reader in &readers {
        match ctx.connect(reader, ShareMode::Exclusive, Protocols::ANY) {
            Ok(card) => return Ok(PlatformTransport { _ctx: ctx, card }),
            Err(e) => last_err = Some(e),
        }
    }
    Err(format!(
        "No device on the reader ({})",
        last_err.map(|e| e.to_string()).unwrap_or_default()
    ))
}
