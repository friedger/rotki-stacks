# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Rotki is a privacy-focused crypto portfolio management and tax reporting application with:
- **Python backend** (Flask API, accounting engine, blockchain interactions)
- **Vue.js/TypeScript frontend** (Electron desktop app + web interface)
- **Rust service** (Colibri - performance-critical components)

### Fork Purpose: Stacks Integration

This fork adds first-class Stacks blockchain support. See `docs/stacks-chain/stacks-integration-prd.md` for full scope.

### CRITICAL: Fork-Only Development

**ALL work happens on this fork (alexlmiller/rotki-stacks), NOT upstream (rotki/rotki).**

- All commits, branches, issues, and PRs target this fork
- Never push to or create issues/PRs on upstream without explicit permission
- Use `origin` (the fork) for all git operations, not `upstream`

After cloning, configure: `gh repo set-default alexlmiller/rotki-stacks`

### Fork Maintenance

**When working on fork operations**, always consult `docs/stacks-chain/fork-maintenance-plan.md`:
- Syncing with upstream rotki/rotki
- Creating releases and version tags
- Resolving merge conflicts
- Branch cleanup and health monitoring

**Quick sync command** (see fork-maintenance-plan.md for full process):
```bash
git checkout upstream-sync && git fetch upstream && git reset --hard upstream/develop && git push origin upstream-sync --force
git checkout develop && git merge upstream-sync && git push origin develop
```

## Git Worktrees and Branch Policy

**Small changes (1-3 lines, context files):** Direct to `develop`
**Medium changes (bug fixes, multi-file):** `git worktree add .worktrees/fix -b bugfixes` → PR
**Substantial (features, major changes):** `git worktree add .worktrees/feat-name -b feat/name` → PR

If unsure, use a worktree + PR.

## Documentation Hierarchy

| Document | Purpose | When to Use |
|----------|---------|-------------|
| `CLAUDE.md` | Entry point, quick reference | Always loaded |
| `docs/stacks-chain/fork-maintenance-plan.md` | Upstream sync, releases, branch management | **Syncing upstream, tagging releases, fork health checks** |
| `docs/stacks-chain/release-process.md` | Creating releases, Docker publishing | **Cutting releases, troubleshooting CI, rollback** |
| `docs/stacks-chain/dev-environment.md` | Running dev environment correctly | **Dev setup issues, CORS errors, service startup** |
| `docs/stacks-chain/stacks-integration-prd.md` | WHAT to build (features, scope) | Planning new Stacks features |
| `docs/stacks-chain/architecture/quick-reference.md` | HOW patterns (common tasks) | During implementation |
| `docs/stacks-chain/architecture/*.md` | Detailed implementation guides | Phase-specific work |
| `.claude/rules/*.md` | Code conventions | When writing code |

**For fork maintenance**: Check `fork-maintenance-plan.md` first - it has Quick Reference section at top.
**For Stacks features**: Read PRD first, then load relevant architecture files.

## Development Commands

### Prerequisites
- Node.js 24, pnpm 11, Python 3.11+, Rust (stable), uv

### Quick Start

**IMPORTANT**: For Stacks development, use the documented setup in `docs/stacks-chain/dev-environment.md`.

**Correct way to run all services:**
```bash
cd frontend
export PATH="$HOME/.cargo/bin:$PATH"
source ../.venv/bin/activate
pnpm dev:web  # Starts backend + Colibri (with CORS) + frontend
```

**Alternative (traditional):**
```bash
pnpm install && uv sync    # Install dependencies
pnpm dev                   # Full dev environment (Electron)
```

**Common mistake**: Manually starting services individually leads to CORS issues. Use `pnpm dev:web` from frontend directory.

### Backend
```bash
uv run python -m rotkehlchen --api-port 4242 --websockets-port 4333  # Run server
uv run python pytestgeventwrapper.py                                  # All tests
uv run python pytestgeventwrapper.py -k test_name                     # Specific test
uv run make lint && uv run make format                                # Lint/format
```

### Frontend
**Run from `frontend/` directory, NOT `frontend/app/`**
```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev && pnpm run test:unit && pnpm run typecheck
```

## Code Architecture

### Backend Structure
- `rotkehlchen/chain/` - Blockchain integrations (Ethereum, Bitcoin, L2s)
- `rotkehlchen/exchanges/` - Exchange integrations
- `rotkehlchen/accounting/` - Tax calculation logic
- `rotkehlchen/history/events/` - Core event abstraction

### Frontend Structure
- `frontend/app/src/` - Vue.js application
- `frontend/app/src/store/` - Pinia state management
- `frontend/app/src/composables/` - Vue composition utilities

### Key Patterns
- REST API (port 4242) + WebSockets (port 4333)
- `HistoryBaseEntry` is the core abstraction for all activities
- Reference implementation for new chains: `rotkehlchen/chain/solana/`

## Conventions Summary

**Frontend** (details in `.claude/rules/frontend-conventions.md`):
- Use `get()`/`set()` from VueUse instead of `.value`
- Explicit types: `ref<boolean>(false)`, explicit return types
- `useI18n({ useScope: 'global' })` always
- Tailwind CSS only; `startPromise()` for floating promises

**Backend** (details in `.claude/rules/backend-conventions.md`):
- Always run tests through `pytestgeventwrapper.py`
- All EVM addresses MUST be checksummed
- Byte signatures as constant literals with `Final`
- Don't use asset objects as constants; use identifier strings

## Testing

- **Backend**: `uv run python pytestgeventwrapper.py` (never direct pytest)
- **Frontend**: `pnpm run test:unit` from `frontend/` directory
- EVM addresses must be checksummed (use `to_checksum_address()`)
- Do not add `@pytest.mark.vcr` to decoder tests

## Code Review Guidelines

### No Assumptions Policy
- Do NOT assume error handling is missing without tracing implementations
- ALWAYS trace function calls to actual implementations

### Known Safe Functions
`request_get()`, `globaldb_get_*()`, `get_or_create_evm_asset()` - handle errors internally

### Pre-validated Types
`ChainID`, `ChecksumEvmAddress`, `Asset`, `TimestampMS` - validated on construction

## Common Issues

- **Frontend build fails**: `pnpm run clean:modules` then `pnpm install --frozen-lockfile`
- **Backend gevent errors**: Use `pytestgeventwrapper.py`, never direct pytest
- **"Invalid XXX account in DB"**: Address not checksummed - use `to_checksum_address()`

## Commits and PRs

- Follow worktree/branch policy (see "Git Worktrees and Branch Policy" section above)
- Commit titles: max 50 characters, imperative mood
- Do not add Co-Authored-By entries for any AI tool
- Target `bugfixes` branch for medium changes, feature branches for substantial changes
- Only small changes (1-3 lines, context files) go direct to `develop`

## Memories

- EVM addresses MUST be checksummed: `'0x5A0b54D5dc17e0AadC383d2db43B0a0D3E029c4c'` (not lowercase)
- `string_to_evm_address()` is a no-op typing function - will NOT checksum

## Additional Resources

- Contribution Guide: https://docs.rotki.com/contribution-guides/contribute-as-developer.html
- Config files: `pyproject.toml`, `frontend/app/package.json`, `Makefile`
