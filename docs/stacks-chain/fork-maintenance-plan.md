# Fork Maintenance Guide: rotki-stacks

Maintaining alexlmiller/rotki-stacks as a long-lived fork of rotki/rotki.

---

## Quick Reference

### Sync with Upstream
```bash
git checkout upstream-sync && git fetch upstream && git reset --hard upstream/develop && git push origin upstream-sync --force
git checkout develop && git merge upstream-sync && git push origin develop
git checkout main && git merge develop --no-edit && git push origin main
git tag v1.41.3-stacks.N -m "Upstream sync: <summary>" && git push origin v1.41.3-stacks.N
```

### Check Fork Health
```bash
git fetch upstream
git log --oneline develop..upstream/develop | wc -l  # commits behind
git diff upstream-sync develop --shortstat            # lines changed
```

### Tag Release
```bash
# Increment suffix for same upstream version
git tag v1.41.3-stacks.2 -m "Upstream sync: bug fixes"
git push origin v1.41.3-stacks.2

# New upstream version
git tag v1.42.0-stacks.1 -m "Based on upstream v1.42.0"
git push origin v1.42.0-stacks.1
```

---

## Part 1: Common Tasks

### Upstream Sync Workflow

Use the normal merge workflow for small, frequent upstream syncs. If the fork is far behind
upstream or the merge would replay a large amount of stale fork history, prefer the
`Major Replay Sync Workflow` below.

**Full sync process:**
```bash
# 1. Update upstream-sync
git checkout upstream-sync
git fetch upstream
git reset --hard upstream/develop
git push origin upstream-sync --force

# 2. Merge to develop
git checkout develop
git merge upstream-sync

# 3. Resolve conflicts (see Conflict Resolution below)
# 4. Test (see Testing Checklist below)
# 5. Update main and tag
git push origin develop
git checkout main && git merge develop --no-edit && git push origin main
git tag v1.41.3-stacks.N -m "Upstream sync: <summary>"
git push origin v1.41.3-stacks.N
```

**Testing Checklist:**

Minimal:
- Backend: `uv run python -m rotkehlchen --api-port 4242`
- Colibri: Check logs for errors
- Frontend: `cd frontend && pnpm run build`
- Stacks: Add address, verify balance loads
- Linters: `uv run make lint` and `cd frontend && pnpm run lint`

Full:
- Backend tests: `uv run python pytestgeventwrapper.py -k stacks`
- Frontend tests: `cd frontend && pnpm run test:unit`
- Smoke test: New user, add accounts, verify history

**Reality check:** First sync (4 commits) had zero conflicts. Stacks is mostly additive.

### Major Replay Sync Workflow

Use this when the fork is hundreds of commits behind upstream and a normal merge would
produce a hard-to-review conflict set or preserve obsolete fork history. The goal is a branch
that equals current `upstream/develop` plus a small number of Stacks replay commits.

**Process:**
```bash
# 1. Create a fresh replay branch from upstream
git fetch upstream
git checkout -b sync/upstream-vX.Y.Z upstream/develop

# 2. Reapply Stacks changes as focused commits
# Prefer a small number of reviewed commits over a giant merge commit.

# 3. Open a PR to alexlmiller/rotki-stacks:develop
git push origin sync/upstream-vX.Y.Z
gh pr create --repo alexlmiller/rotki-stacks --base develop --head sync/upstream-vX.Y.Z
```

**Review checklist for replay PRs:**
- Confirm topology: `git log --oneline upstream/develop..PR_HEAD` should show only replay commits.
- Review the replay delta with `git diff upstream/develop..PR_HEAD --stat`.
- Check migration-number collisions against both upstream and old fork versions.
- Add fork-aware compatibility migrations for existing fork DBs before replacing `develop`.
- Validate old-fork user DB upgrades, Stacks tests, frontend typecheck, and Docker/release build.

**Integration:**

Do not use GitHub's normal merge button for replay PRs. A replay branch is intended to
replace `develop` after review:
```bash
git checkout develop
git reset --hard sync/upstream-vX.Y.Z
git push origin develop --force-with-lease
```

After replacement, update `upstream-sync`, promote to `main` only after validation, and tag
the release. Tell anyone with a local `develop` checkout to resync because this rewrites fork
history.

### Conflict Resolution

**Conflict Zones:**

| Risk Level | Files | Strategy |
|------------|-------|----------|
| **High** | `rotkehlchen/types.py`, `rotkehlchen.py`, `db/dbhandler.py`, `db/schema.py`, `globaldb/handler.py`, `frontend/common/src/blockchain/` | Review carefully, reapply additions |
| **Medium** | `api/v1/schemas.py`, `frontend/.../composables/`, `frontend/.../types/`, `locales/en.json` | Usually append/merge |
| **Low** | `rotkehlchen/chain/stacks/`, `frontend/.../stacks/`, `docs/stacks-chain/` | Should survive untouched |

**Resolution Process:**
```bash
# Preview changes
git log develop..upstream-sync --oneline
git diff develop..upstream-sync --stat

# Try merge to see conflicts
git merge upstream-sync --no-commit --no-ff
git merge --abort  # inspect first

# Do actual merge
git merge upstream-sync
# For each conflict: understand both changes, keep both if possible, prefer upstream approach
git add <files> && git commit

# Always test
uv run python pytestgeventwrapper.py -k stacks
cd frontend && pnpm run test:unit
```

**Common Patterns:**

| Conflict | Resolution |
|----------|------------|
| Enum additions | Keep both, yours at end |
| Function signatures | Update Stacks code to match |
| Schema changes | Merge both, ensure consistency |
| Import reordering | Accept upstream, add yours |
| Type changes | Update Stacks types to match |

### Versioning

Format: `v{upstream}-stacks.{suffix}`

**When to increment:**
- `v1.41.3-stacks.1` → `v1.41.3-stacks.2`: Sync commits within same upstream version
- `v1.41.3-stacks.2` → `v1.42.0-stacks.1`: New upstream version

**Release workflow:**
1. Sync with upstream
2. Test thoroughly
3. Tag release
4. Create GitHub Release (document upstream version, Stacks features, known issues)

### Releasing

**Automated CI** creates releases when you push version tags.

**Quick release:**
```bash
# From main branch, after merging develop
git tag v1.41.3-stacks.2 -m "Release: upstream sync + bug fixes"
git push origin v1.41.3-stacks.2
```

CI automatically:
- Creates GitHub Release with template
- Builds Docker images (amd64 + arm64)
- Pushes to Docker Hub with version + `latest` tags

**After release:**
```bash
# Update release notes
gh release edit v1.41.3-stacks.2

# Verify images
docker pull alexlmiller/rotki-stacks:v1.41.3-stacks.2
docker manifest inspect alexlmiller/rotki-stacks:latest
```

**Full guide:** See `docs/stacks-chain/release-process.md` for:
- Prerequisites (Docker Hub secrets)
- Detailed steps
- Troubleshooting
- Rollback procedures

---

## Part 2: Operational Guidance

### Branch Cleanup

**After every merge:**
```bash
git branch -d feat/my-feature
git push origin --delete feat/my-feature
```

**Monthly review:**
```bash
git for-each-ref --sort=-committerdate refs/heads/ --format='%(refname:short) %(committerdate:relative)'
```

**Keep:** `main`, `develop`, `upstream-sync`, active features

### Git Worktrees

```bash
# Create
git worktree add .worktrees/fix-issue-42 -b fix/issue-42
cd .worktrees/fix-issue-42

# Cleanup after merge
cd ../..
git worktree remove .worktrees/fix-issue-42
git branch -d fix/issue-42

# List
git worktree list
```

### Fork Health Monitoring

**Commits behind:**
```bash
git fetch upstream
git log --oneline develop..upstream/develop | wc -l
```
- < 10: Sync when convenient
- 10-50: Sync soon
- \> 50: Priority sync

**Lines changed:**
```bash
git diff upstream-sync develop --numstat | awk '{added+=$1; removed+=$2} END {print "Added:", added, "Removed:", removed}'
```
- < 5K: Clean fork ✓
- 5K-20K: Manageable
- \> 20K: Consider refactoring

**Track over time:**
| Date | Commits | Conflicts | Time | Notes |
|------|---------|-----------|------|-------|
| 2026-01-26 | 4 | 0 | 10m | Clean |

If difficulty increases: sync more often, contribute upstream, or refactor.

---

## Part 3: Reference

### Repository Identity

Fork: `alexlmiller/rotki-stacks`

Update remotes:
```bash
git remote set-url origin https://github.com/alexlmiller/rotki-stacks.git
gh repo set-default alexlmiller/rotki-stacks
```

### Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable releases |
| `develop` | Active development + upstream merges or reviewed replay syncs |
| `upstream-sync` | Clean upstream mirror |

**Flow:**
```
upstream/develop → upstream-sync → develop → main
                                      ↓
                                 feature branches
```

**Why upstream-sync?**
- Clean reference of upstream
- Easy to see what changed: `git diff upstream-sync develop`
- Base for PRs back to upstream

### Commands Reference

```bash
# Divergence from upstream
git log --oneline upstream/develop..develop

# Your changes vs upstream
git diff upstream-sync develop --stat

# Preview conflicts
git merge upstream-sync --no-commit --no-ff
git merge --abort

# Sync with specific tag
git fetch upstream --tags
git checkout -b release/v1.42.0-stacks upstream/v1.42.0
git merge develop

# Commits in each direction
git rev-list --left-right --count upstream/develop...develop
# Output: X Y (X=upstream ahead, Y=you ahead)
```

---

## Appendix

### Contributing Back to Upstream

**PR from clean base:**
```bash
git checkout upstream-sync
git checkout -b upstream-pr/fix-xyz
git commit -m "Fix XYZ"
git push origin upstream-pr/fix-xyz
# PR: rotki/rotki ← alexlmiller/rotki-stacks:upstream-pr/fix-xyz
```

**What to PR:** Bug fixes, generic improvements, foundational changes
**What not to PR:** Full Stacks integration (too large), Stacks-specific changes

**Long-term:** If proposing Stacks integration upstream, open issue first, break into small PRs.

### Tracking Sync Work

Create issue for significant syncs:
```markdown
# Upstream Sync: v1.42.0
**Commits:** 23
**Changes:** Avalanche subnets, performance, bug fixes
**Conflicts:** TBD
**Testing:** Full suite + Stacks tests
**Release:** v1.42.0-stacks.1
```

Benefits: Track history, document decisions, link releases.
