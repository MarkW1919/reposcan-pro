#!/usr/bin/env bash
# deploy/scripts/start.sh — Ordered startup for all RepoScan Pro services.
#
# Waits for each dependency to be healthy before proceeding to the next layer.
# Safe to run after a power-loss restart — services are already idempotent.
#
# Usage:
#   ./deploy/scripts/start.sh                   # uses REPOSCAN_DEPLOY_PROFILE env var
#   REPOSCAN_DEPLOY_PROFILE=jetson-orin-edge ./deploy/scripts/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Load environment variables if the env file exists
ENV_FILE="${ENV_FILE:-/etc/reposcan/env}"
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a; source "${ENV_FILE}"; set +a
fi

REPOSCAN_DEPLOY_PROFILE="${REPOSCAN_DEPLOY_PROFILE:-local-dev}"
REPOSCAN_API_HOST="${REPOSCAN_API_HOST:-127.0.0.1}"
REPOSCAN_API_PORT="${REPOSCAN_API_PORT:-8000}"

log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }

# ── 1. Infrastructure (postgres) ────────────────────────────────────────────
log "Checking infrastructure services…"
if command -v docker &>/dev/null; then
    if docker compose -f "${REPO_ROOT}/docker-compose.yml" ps postgres 2>/dev/null | grep -q "healthy\|running"; then
        log "postgres already running."
    else
        log "Starting postgres via docker-compose…"
        docker compose -f "${REPO_ROOT}/docker-compose.yml" up -d postgres
        log "Waiting for postgres to be healthy…"
        for i in $(seq 1 30); do
            if docker compose -f "${REPO_ROOT}/docker-compose.yml" ps postgres | grep -q "healthy"; then
                log "postgres healthy."
                break
            fi
            [[ $i -eq 30 ]] && { log "ERROR: postgres did not become healthy in 30 s."; exit 1; }
            sleep 1
        done
    fi
else
    log "Docker not available — assuming postgres is managed externally."
fi

# ── 2. API server ────────────────────────────────────────────────────────────
log "Starting API server (profile: ${REPOSCAN_DEPLOY_PROFILE})…"
if systemctl is-active --quiet reposcan-api 2>/dev/null; then
    log "reposcan-api already active."
else
    systemctl start reposcan-api 2>/dev/null || {
        # Fallback for non-systemd environments
        log "systemd not available — using direct uvicorn start."
        cd "${REPO_ROOT}"
        REPOSCAN_DEPLOY_PROFILE="${REPOSCAN_DEPLOY_PROFILE}" \
            .venv/bin/uvicorn reposcan_api.main:app \
            --host "${REPOSCAN_API_HOST}" \
            --port "${REPOSCAN_API_PORT}" \
            --log-level warning \
            --no-access-log &
        echo $! > runtime/api.pid
    }
fi

# Wait for API to be reachable
log "Waiting for API health endpoint…"
for i in $(seq 1 20); do
    if curl -sf "http://${REPOSCAN_API_HOST}:${REPOSCAN_API_PORT}/api/v1/health" >/dev/null 2>&1; then
        log "API is healthy."
        break
    fi
    [[ $i -eq 20 ]] && { log "ERROR: API did not become healthy in 20 s."; exit 1; }
    sleep 1
done

# ── 3. Ingest runtime ────────────────────────────────────────────────────────
log "Starting ingest runtime…"
if systemctl is-active --quiet reposcan-ingest 2>/dev/null; then
    log "reposcan-ingest already active."
else
    systemctl start reposcan-ingest 2>/dev/null || log "systemd not available — start ingest manually."
fi

# ── 4. UI server ─────────────────────────────────────────────────────────────
log "Starting UI server…"
if systemctl is-active --quiet reposcan-ui 2>/dev/null; then
    log "reposcan-ui already active."
else
    systemctl start reposcan-ui 2>/dev/null || log "systemd not available — start UI manually."
fi

log "All services started. Status:"
systemctl status reposcan-api reposcan-ingest reposcan-ui --no-pager 2>/dev/null || true
