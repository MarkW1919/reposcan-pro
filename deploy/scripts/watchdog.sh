#!/usr/bin/env bash
# deploy/scripts/watchdog.sh — Health watchdog for deployed RepoScan Pro services.
#
# Polls the API health endpoint every 30 s.  If the API is unreachable or
# unhealthy, restarts the ingest and API services via systemctl.
#
# Designed to run as a long-lived process under the reposcan-watchdog.service
# systemd unit.  Works with supervisord too.

set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/reposcan/env}"
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a; source "${ENV_FILE}"; set +a
fi

REPOSCAN_API_HOST="${REPOSCAN_API_HOST:-127.0.0.1}"
REPOSCAN_API_PORT="${REPOSCAN_API_PORT:-8000}"
HEALTH_URL="http://${REPOSCAN_API_HOST}:${REPOSCAN_API_PORT}/api/v1/health"
POLL_INTERVAL="${WATCHDOG_POLL_INTERVAL:-30}"
MAX_FAILURES="${WATCHDOG_MAX_FAILURES:-3}"

log() { echo "[$(date -u +%H:%M:%SZ)] watchdog: $*"; }

consecutive_failures=0

while true; do
    sleep "${POLL_INTERVAL}"

    status_code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 5 "${HEALTH_URL}" 2>/dev/null || echo '000')"

    if [[ "${status_code}" == "200" ]]; then
        consecutive_failures=0
        log "API healthy (HTTP 200)."
    else
        consecutive_failures=$(( consecutive_failures + 1 ))
        log "WARNING: API returned HTTP ${status_code} (failure ${consecutive_failures}/${MAX_FAILURES})."

        if [[ "${consecutive_failures}" -ge "${MAX_FAILURES}" ]]; then
            log "Threshold reached — restarting services."
            systemctl restart reposcan-ingest 2>/dev/null && log "reposcan-ingest restarted." || log "could not restart reposcan-ingest."
            sleep 5
            systemctl restart reposcan-api 2>/dev/null && log "reposcan-api restarted." || log "could not restart reposcan-api."
            consecutive_failures=0
        fi
    fi
done
