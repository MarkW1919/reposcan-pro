#!/usr/bin/env bash
# deploy/scripts/update.sh — Pull latest code, rebuild, and restart services.
#
# Performs a rolling update:
#   1. Pull new code from the configured remote
#   2. Install/update Python dependencies
#   3. Run contract validation tests (abort if they fail)
#   4. Build the UI
#   5. Reload services in order (ingest → api → ui)
#
# Usage:
#   ./deploy/scripts/update.sh
#   ./deploy/scripts/update.sh --skip-tests    # not recommended for production

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SKIP_TESTS="${1:-}"

log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }
die() { log "ERROR: $*"; exit 1; }

cd "${REPO_ROOT}"

# ── 1. Pull latest code ──────────────────────────────────────────────────────
log "Pulling latest code…"
git fetch origin
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git pull --ff-only origin "${CURRENT_BRANCH}" || die "Fast-forward pull failed. Resolve conflicts manually."
log "Now at: $(git rev-parse --short HEAD)"

# ── 2. Python dependencies ───────────────────────────────────────────────────
log "Updating Python dependencies…"
.venv/bin/pip install -e ".[dev]" --quiet

# ── 3. Contract validation ───────────────────────────────────────────────────
if [[ "${SKIP_TESTS}" != "--skip-tests" ]]; then
    log "Running contract and integration tests…"
    .venv/bin/pytest tests/ -x -q --timeout=60 || die "Tests failed — aborting update."
    log "Tests passed."
else
    log "WARNING: Tests skipped by --skip-tests flag."
fi

# ── 4. UI build ──────────────────────────────────────────────────────────────
log "Building UI…"
npm run ui:build || die "UI build failed."
log "UI build complete."

# ── 5. Reload services ───────────────────────────────────────────────────────
log "Reloading services…"
systemctl restart reposcan-ingest 2>/dev/null && log "reposcan-ingest restarted." || log "reposcan-ingest not managed by systemd."
sleep 3
systemctl restart reposcan-api 2>/dev/null && log "reposcan-api restarted." || log "reposcan-api not managed by systemd."
sleep 2
systemctl restart reposcan-ui 2>/dev/null && log "reposcan-ui restarted." || log "reposcan-ui not managed by systemd."

log "Update complete. Git ref: $(git rev-parse --short HEAD)"
