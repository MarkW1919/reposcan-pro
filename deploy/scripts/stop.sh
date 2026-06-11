#!/usr/bin/env bash
# deploy/scripts/stop.sh — Graceful shutdown of all RepoScan Pro services.
#
# Stops in reverse startup order: ingest first (stops new detections), then
# API (drains in-flight requests), then UI.
#
# Usage:
#   ./deploy/scripts/stop.sh

set -euo pipefail

log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }

stop_service() {
    local name="$1"
    if systemctl is-active --quiet "${name}" 2>/dev/null; then
        log "Stopping ${name}…"
        systemctl stop "${name}"
        log "${name} stopped."
    elif [[ -f "runtime/${name##reposcan-}.pid" ]]; then
        local pid
        pid="$(cat "runtime/${name##reposcan-}.pid")"
        if kill -0 "${pid}" 2>/dev/null; then
            log "Stopping ${name} (pid ${pid})…"
            kill -TERM "${pid}"
            sleep 3
            kill -0 "${pid}" 2>/dev/null && kill -KILL "${pid}" || true
        fi
        rm -f "runtime/${name##reposcan-}.pid"
    else
        log "${name} is not running."
    fi
}

stop_service reposcan-ingest
stop_service reposcan-ui
stop_service reposcan-api

log "All services stopped."
