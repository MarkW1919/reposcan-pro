#!/usr/bin/env bash
# deploy/scripts/rollback.sh — Roll back to the previous git commit and restart.
#
# Rolls back code only — does NOT roll back the database schema or stored media.
# If the database schema changed in the rolled-back commit, restore the database
# separately before running this script.
#
# Usage:
#   ./deploy/scripts/rollback.sh              # revert to HEAD~1
#   ./deploy/scripts/rollback.sh <git-ref>    # revert to specific commit

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TARGET_REF="${1:-HEAD~1}"

log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }
die() { log "ERROR: $*"; exit 1; }

cd "${REPO_ROOT}"

CURRENT_REF="$(git rev-parse --short HEAD)"
log "Current ref: ${CURRENT_REF}"
log "Rolling back to: ${TARGET_REF}"

# Resolve the target ref to a full hash for clarity
RESOLVED_REF="$(git rev-parse --short "${TARGET_REF}")" || die "Cannot resolve ref: ${TARGET_REF}"
log "Resolved rollback target: ${RESOLVED_REF}"

# Safety: verify the target ref exists in the history
git merge-base --is-ancestor "${RESOLVED_REF}" HEAD || die "${RESOLVED_REF} is not in the current branch history."

# ── Stop services ────────────────────────────────────────────────────────────
log "Stopping services before rollback…"
"${SCRIPT_DIR}/stop.sh"

# ── Checkout ─────────────────────────────────────────────────────────────────
log "Checking out ${RESOLVED_REF}…"
git checkout "${RESOLVED_REF}" -- .

# ── Reinstall dependencies at the rolled-back version ───────────────────────
log "Reinstalling Python dependencies…"
.venv/bin/pip install -e ".[dev]" --quiet

# ── Rebuild UI at rolled-back version ────────────────────────────────────────
log "Rebuilding UI at rolled-back version…"
npm run ui:build || die "UI build failed at ${RESOLVED_REF}."

# ── Restart services ─────────────────────────────────────────────────────────
log "Starting services…"
"${SCRIPT_DIR}/start.sh"

log "Rollback complete. Running at: ${RESOLVED_REF}"
log "To finalize: git reset --hard ${RESOLVED_REF} && git push --force-with-lease origin HEAD"
