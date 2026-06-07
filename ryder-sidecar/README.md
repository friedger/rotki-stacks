# ryder-sidecar

A small Rust binary that lets rotki's **Electron** desktop app read addresses from a
[Ryder One](https://ryder.id) hardware wallet over NFC. It demonstrates how to use the Ryder
**tool SDK** (`ryder_nfc_tool`, the minimal/transport-agnostic build) from Electron via a
sidecar process — the same way the reference `ryder-tauri-getversion` app uses it from Tauri,
just with a different host.

```
Electron main (Node)                         this crate (Rust)
┌───────────────────────────┐  spawn        ┌──────────────────────────────┐
│ ryder-import-handlers.ts   │ ───────────▶ │ ryder-sidecar                 │
│  (IPC: INVOKE_RYDER_IMPORT)│  stdout JSON  │  PC/SC transport (transport.rs)│
└───────────▲───────────────┘ ◀──────────── │  Ryder flow (flow.rs):         │
            │ preload interop.importFromRyder│   pair → secure channel →      │
   renderer │                                │   read pubkeys → derive addrs  │
"Import from Ryder One" button               │  ryder_nfc_tool (minimal SDK)  │
                                             └──────────────────────────────┘
```

## What it does

Runs the shared Ryder flow (ported from `ryder-tauri-getversion`):
pairs with the device, opens the secure channel, reads the BTC / ETH / SOL / STX public keys
and derives their addresses. It prints a single JSON line on stdout:

```json
{"ok":true,"data":{"version":{...},"accounts":[{"chain":"Stacks","symbol":"STX","path":"m/44'/5757'/0'/0/0","address":"SP..."}, ...]}}
{"ok":false,"error":"No NFC reader found — plug in a PC/SC reader and place your Ryder One on it."}
```

The transport is **PC/SC** (`pcsc` crate) — the default desktop NFC path, matching the Ryder
CLI tool. The protocol stack (Session / pairing / secure channel / commands / address
derivation) all comes from `ryder_nfc_tool` with `default-features = false`; we only supply the
transceiver closure (`src/transport.rs`).

## Prerequisites

- Rust (stable; `ryder_nfc_tool` uses edition 2024)
- `libpcsclite` dev headers (Linux: `apt install libpcsclite-dev`) and the `pcscd` daemon running
- A PC/SC NFC reader (e.g. ACR122U) with the Ryder One placed on it
- The sibling **`light-labs/ryder-nfc-tool`** checkout next to this repo — the `Cargo.toml`
  path dependency is `../../../light-labs/ryder-nfc-tool` (relative to this crate). Adjust if your
  layout differs. (This is why CI/other machines won't build it without that checkout.)

## Build & run

```sh
cargo build --release        # produces target/release/ryder-sidecar
./target/release/ryder-sidecar /path/to/datadir   # datadir holds the pairing key
```

## How rotki uses it (Electron)

- The Electron main process spawns this binary on demand from
  `frontend/app/electron/main/ipc-handlers/ryder-import-handlers.ts`.
- Binary resolution order: `$RYDER_SIDECAR_PATH` → `<resources>/ryder-sidecar/` (packaged) →
  `<repo>/ryder-sidecar/target/{release,debug}/ryder-sidecar` (dev).
- The renderer calls `interop.importFromRyder()` (preload bridge → IPC `RYDER_IMPORT`).
- UI: the **"Import from Ryder One"** button next to the existing "Import from browser wallet"
  button in the blockchain account add form (`WalletAddressesImport.vue`). It appears in the
  packaged (Electron) app for BTC / ETH (and EVM) / SOL / STX accounts and fills the address
  field with the device's address for the form's chain.

To try it in dev: `cargo build --release` here, then run the rotki Electron app
(`cd frontend && pnpm dev`), open Accounts → add a blockchain account, and click the Ryder
button. Without a reader/device the sidecar returns a friendly error that rotki surfaces.

## Alternatives (not used here)

- **WASM**: `ryder_nfc_tool`'s minimal build also targets WASM. That could run the protocol in
  the renderer, but WASM has no PC/SC access, so a JS-side transport would still be needed —
  the sidecar keeps the native NFC transport out of the renderer.
- **TS secure-channel SDK** (`ryder-secure-channel-ts-internal`): a separate, lower-level TS
  implementation. This integration deliberately uses the Rust tool SDK instead, per the
  reference Tauri app.

## Packaging note

For a shipping build, bundle the release binary as an Electron resource (alongside the backend
and colibri binaries) so it lands at `<resources>/ryder-sidecar/`. The handler already looks
there first (after `$RYDER_SIDECAR_PATH`).
