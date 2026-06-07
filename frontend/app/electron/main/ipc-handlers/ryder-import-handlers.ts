import type { LogService } from '@electron/main/log-service';
import type { RyderChainAddress, RyderImport } from '@shared/ipc';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { app } from 'electron';

// The device tap + secure-channel read can take a while; give the user time to present the device.
const RYDER_TIMEOUT_MS = 120_000;

// The single JSON line the ryder-sidecar prints on stdout.
type SidecarOutput =
  | { ok: true; data: { accounts: RyderChainAddress[] } }
  | { ok: false; error: string };

/**
 * Bridges rotki to a Ryder One hardware wallet via the `ryder-sidecar` Rust binary.
 *
 * The sidecar uses the Ryder tool SDK (minimal build) with a PC/SC transport to pair with the
 * device over NFC, open a secure channel, read the chain public keys and derive addresses. It
 * prints a single JSON line: {"ok":true,"data":{version,accounts}} | {"ok":false,"error":...}.
 */
export class RyderImportHandlers {
  constructor(private readonly logger: LogService) {}

  /** Resolve the ryder-sidecar binary: env override -> packaged resources -> dev target dir. */
  private resolveBinary(): string | undefined {
    const exe = process.platform === 'win32' ? 'ryder-sidecar.exe' : 'ryder-sidecar';
    const candidates = [
      process.env.RYDER_SIDECAR_PATH,
      process.resourcesPath ? path.join(process.resourcesPath, 'ryder-sidecar', exe) : undefined,
      // dev: repo root is two levels above the electron app dir (frontend/app)
      path.resolve(process.cwd(), '..', '..', 'ryder-sidecar', 'target', 'release', exe),
      path.resolve(process.cwd(), '..', '..', 'ryder-sidecar', 'target', 'debug', exe),
    ].filter((p): p is string => typeof p === 'string' && p.length > 0);

    return candidates.find(candidate => fs.existsSync(candidate));
  }

  importFromRyder = async (): Promise<RyderImport> => {
    const binary = this.resolveBinary();
    if (!binary) {
      return {
        error: 'Ryder sidecar binary not found. Build it with `cargo build --release` in '
          + '`ryder-sidecar/`, or set RYDER_SIDECAR_PATH.',
      };
    }

    const dataDir = path.join(app.getPath('userData'), 'ryder');
    this.logger.info(`Running Ryder sidecar: ${binary} (data dir ${dataDir})`);

    return new Promise<RyderImport>((resolve) => {
      const child = spawn(binary, [dataDir], { windowsHide: true });
      let stdout = '';
      let stderr = '';
      let settled = false;
      let timer: NodeJS.Timeout;

      const finish = (result: RyderImport): void => {
        if (settled)
          return;
        settled = true;
        clearTimeout(timer);
        resolve(result);
      };

      timer = setTimeout(() => {
        child.kill();
        finish({ error: 'Timed out waiting for the Ryder One. Place it on the reader and retry.' });
      }, RYDER_TIMEOUT_MS);

      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString();
      });
      child.stderr.on('data', (chunk) => {
        stderr += chunk.toString();
      });
      child.on('error', (error) => {
        finish({ error: `Failed to launch Ryder sidecar: ${error.message}` });
      });
      child.on('close', () => {
        try {
          const line = stdout.split('\n').map(part => part.trim()).findLast(Boolean) ?? '';
          const parsed: SidecarOutput = JSON.parse(line);
          if (parsed.ok)
            finish({ accounts: parsed.data.accounts });
          else
            finish({ error: parsed.error });
        }
        catch {
          this.logger.error(`Ryder sidecar produced no parseable output. stderr: ${stderr}`);
          finish({ error: stderr.trim() || 'Ryder sidecar produced no output.' });
        }
      });
    });
  };
}
