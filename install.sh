#!/usr/bin/env bash
# Setup AI / FIREWING 1.0 BETA installer for Ubuntu 22.04 / 24.04 LTS.
#
# Usage:
#   git clone <repository>       # replace with your actual repo URL
#   cd setup-ai
#   bash install.sh
#
# There is currently no hosted curl-pipe installer — no
# `curl -fsSL https://.../install.sh | bash` — because no public
# download URL exists yet for this project. Use git clone above, or
# publish install.sh at a URL you control and update this comment.

set -euo pipefail

FIREWING_USER="firewing"
FIREWING_HOME="/opt/firewing"
VENV_DIR="${FIREWING_HOME}/venv"

log()  { echo -e "\033[1;32m[install]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        die "This installer needs root (sudo bash install.sh) to create a system user, install packages, and set up the systemd service."
    fi
}

detect_os() {
    if [[ ! -f /etc/os-release ]]; then
        die "Cannot detect OS (missing /etc/os-release). This installer supports Ubuntu 22.04/24.04 LTS only."
    fi
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]]; then
        warn "Detected ${PRETTY_NAME:-unknown OS}. This installer is tested on Ubuntu 22.04/24.04 only — continuing, but expect rough edges."
    fi
    log "Detected: ${PRETTY_NAME:-unknown}"
}

detect_gpu() {
    if command -v nvidia-smi &>/dev/null; then
        log "NVIDIA GPU detected:"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
        HAS_GPU=1
    else
        warn "No NVIDIA GPU detected (nvidia-smi not found). Installing CPU-only path."
        HAS_GPU=0
    fi
}

install_system_deps() {
    log "Installing system packages..."
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip git curl ufw
}

create_service_user() {
    if id "${FIREWING_USER}" &>/dev/null; then
        log "User ${FIREWING_USER} already exists."
    else
        log "Creating dedicated non-root user '${FIREWING_USER}'..."
        useradd --system --create-home --shell /usr/sbin/nologin "${FIREWING_USER}"
    fi
}

setup_python_env() {
    log "Setting up Python virtual environment at ${VENV_DIR}..."
    mkdir -p "${FIREWING_HOME}"
    cp -r . "${FIREWING_HOME}/app"
    python3 -m venv "${VENV_DIR}"
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install -r "${FIREWING_HOME}/app/requirements.txt"
    if [[ "${HAS_GPU:-0}" -eq 1 ]]; then
        log "GPU detected — ensure your requirements.txt/torch install matches your CUDA version."
        log "See docs/gpu.md for CUDA-specific install instructions."
    fi
    chown -R "${FIREWING_USER}:${FIREWING_USER}" "${FIREWING_HOME}"
}

setup_config() {
    local cfg_dir="${FIREWING_HOME}/app/configs"
    if [[ ! -f "${cfg_dir}/firewing.yaml" ]]; then
        cp "${cfg_dir}/firewing.example.yaml" "${cfg_dir}/firewing.yaml"
        log "Created configs/firewing.yaml from the example — review it before starting the service."
    fi
    if [[ ! -f "${FIREWING_HOME}/app/.env" ]]; then
        cp "${FIREWING_HOME}/app/.env.example" "${FIREWING_HOME}/app/.env"
        warn "Created .env from .env.example — set FIREWING_API_KEYS before exposing this service to the network."
    fi
}

setup_systemd() {
    log "Installing systemd service..."
    cp "${FIREWING_HOME}/app/firewing.service" /etc/systemd/system/firewing.service
    systemctl daemon-reload
    systemctl enable firewing
    log "Service installed. Start it with: sudo systemctl start firewing"
}

setup_firewall() {
    if command -v ufw &>/dev/null; then
        log "Configuring firewall: allowing SSH only by default. The FIREWING API port"
        log "should stay internal and be reached via a reverse proxy (see docs/vps.md)."
        ufw allow OpenSSH || true
    fi
}

main() {
    require_root
    detect_os
    detect_gpu
    install_system_deps
    create_service_user
    setup_python_env
    setup_config
    setup_systemd
    setup_firewall

    log "Installation complete."
    log "Next steps:"
    log "  1. Review ${FIREWING_HOME}/app/configs/firewing.yaml"
    log "  2. Set FIREWING_API_KEYS in ${FIREWING_HOME}/app/.env"
    log "  3. sudo systemctl start firewing"
    log "  4. sudo systemctl status firewing"
    log "  5. curl http://localhost:8000/health"
}

main "$@"
