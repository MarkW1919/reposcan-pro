#!/usr/bin/env bash
# deploy/scripts/install.sh — Field installer for RepoScan Pro on Linux edge devices.
#
# Installs system dependencies, copies the repo, sets up the Python venv,
# builds the UI, installs systemd units, and enables services for auto-start.
#
# Tested on: Ubuntu 22.04 LTS, JetPack 6.x (Jetson Orin Nano Super target)
#
# Usage (as root or with sudo):
#   sudo ./deploy/scripts/install.sh [--profile jetson-orin-nano-super]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/reposcan-pro}"
SERVICE_USER="${SERVICE_USER:-reposcan}"
DEPLOY_PROFILE="jetson-orin-nano-super"

# Parse --profile flag
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) DEPLOY_PROFILE="$2"; shift 2;;
        *) shift;;
    esac
done

log() { echo "[$(date -u +%H:%M:%SZ)] install: $*"; }
die() { log "ERROR: $*"; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "This script must be run as root (sudo)."

# ── 1. System dependencies ────────────────────────────────────────────────────
log "Installing system packages…"
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev \
    build-essential git curl ca-certificates rsync \
    libpq-dev \
    libopencv-dev python3-opencv \
    supervisor \
    2>/dev/null || log "Some packages may already be installed."

if ! command -v node >/dev/null 2>&1 || [[ "$(node --version 2>/dev/null || true)" != v24.* ]]; then
    log "Installing Node.js 24.x runtime..."
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
    apt-get install -y --no-install-recommends nodejs
fi

NODE_VERSION="$(node --version)"
NPM_MAJOR="$(npm --version | cut -d. -f1)"
[[ "${NODE_VERSION}" == v24.* ]] || die "Node 24.x is required; found ${NODE_VERSION}."
[[ "${NPM_MAJOR}" == "11" ]] || die "npm 11.x is required; found $(npm --version)."

# ── 2. Service user ───────────────────────────────────────────────────────────
if ! id "${SERVICE_USER}" &>/dev/null; then
    log "Creating service user: ${SERVICE_USER}"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

# Add to video group for camera device access
usermod -aG video "${SERVICE_USER}" 2>/dev/null || true

# ── 3. Copy repo ─────────────────────────────────────────────────────────────
log "Installing repo to ${INSTALL_DIR}…"
mkdir -p "${INSTALL_DIR}"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    "${REPO_ROOT}/" "${INSTALL_DIR}/"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

# ── 4. Python venv ────────────────────────────────────────────────────────────
log "Creating Python virtual environment…"
python3.11 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip --quiet
"${INSTALL_DIR}/.venv/bin/pip" install -e "${INSTALL_DIR}[dev]" --quiet
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/.venv"

# ── 5. UI build ───────────────────────────────────────────────────────────────
log "Building UI…"
cd "${INSTALL_DIR}"
npm ci --silent
npm run ui:build
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/apps/ui/dist"

# ── 6. Runtime directories ────────────────────────────────────────────────────
log "Creating runtime directories…"
for dir in data artifacts media logs runtime; do
    mkdir -p "${INSTALL_DIR}/${dir}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/${dir}"
done

# ── 7. Environment file ───────────────────────────────────────────────────────
mkdir -p /etc/reposcan
if [[ ! -f /etc/reposcan/env ]]; then
    log "Installing environment file template to /etc/reposcan/env…"
    cp "${REPO_ROOT}/deploy/env.example" /etc/reposcan/env
    chmod 640 /etc/reposcan/env
    chown "root:${SERVICE_USER}" /etc/reposcan/env
    log "IMPORTANT: Edit /etc/reposcan/env and set real values before starting services."
else
    log "/etc/reposcan/env already exists — not overwriting."
fi

# ── 8. Deploy profile ─────────────────────────────────────────────────────────
log "Setting deploy profile to: ${DEPLOY_PROFILE}"
sed -i "s|^REPOSCAN_DEPLOY_PROFILE=.*|REPOSCAN_DEPLOY_PROFILE=${DEPLOY_PROFILE}|" /etc/reposcan/env

# ── 9. systemd units ──────────────────────────────────────────────────────────
log "Installing systemd units…"
for unit in reposcan-api reposcan-ingest reposcan-ui reposcan-watchdog; do
    cp "${REPO_ROOT}/deploy/systemd/${unit}.service" /etc/systemd/system/
done
systemctl daemon-reload
systemctl enable reposcan-api reposcan-ingest reposcan-ui reposcan-watchdog
log "systemd units installed and enabled."

# ── 10. Make scripts executable ───────────────────────────────────────────────
chmod +x "${INSTALL_DIR}/deploy/scripts/"*.sh

log "Installation complete."
log "Next steps:"
log "  1. Edit /etc/reposcan/env — set API keys, postgres URL, etc."
log "  2. Start services:  ${INSTALL_DIR}/deploy/scripts/start.sh"
log "  3. Verify health:   curl http://127.0.0.1:8000/api/v1/health"
