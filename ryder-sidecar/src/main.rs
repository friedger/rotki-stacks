//! ryder-sidecar: a tiny stdout-JSON bridge that rotki's Electron main process spawns to read a
//! Ryder One over NFC (PC/SC). It runs the shared Ryder flow (pair + secure channel + read the
//! four chain public keys + derive addresses) and prints a single JSON line:
//!
//!   {"ok": true,  "data": { "version": {...}, "accounts": [ { "chain", "symbol", "path", "address" }, ... ] }}
//!   {"ok": false, "error": "human readable message"}
//!
//! Usage:  ryder-sidecar [DATA_DIR]
//!   DATA_DIR (or $RYDER_DATA_DIR) is where the app's pairing key is stored. Defaults to a temp dir.

mod flow;
mod transport;

use std::path::PathBuf;

fn data_dir() -> PathBuf {
    std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .or_else(|| std::env::var("RYDER_DATA_DIR").ok().map(PathBuf::from))
        .unwrap_or_else(|| std::env::temp_dir().join("rotki-ryder-sidecar"))
}

fn main() {
    let dir = data_dir();
    let result = (|| -> Result<flow::WalletData, String> {
        let mut transport = transport::open_transport()?;
        flow::run(move |apdu| transport.transceive(apdu), &dir)
    })();

    match result {
        Ok(data) => {
            let out = serde_json::json!({ "ok": true, "data": data });
            println!("{}", serde_json::to_string(&out).expect("serialize wallet data"));
        }
        Err(error) => {
            let out = serde_json::json!({ "ok": false, "error": error });
            println!("{}", serde_json::to_string(&out).expect("serialize error"));
            std::process::exit(1);
        }
    }
}
