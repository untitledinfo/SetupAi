#!/usr/bin/env bash
# Setup AI / FIREWING 1.0 BETA installer for Ubuntu 22.04 / 24.04 LTS.
#
# Usage:
#   git clone https://github.com/untitledinfo/SetupAi.git
#   cd SetupAi/setup-ai
#   sudo bash install.sh
#
# There is intentionally no curl-pipe installer — this script needs
# root and touches system state (users, systemd, firewall), so review
# it from a clone rather than piping it blind from a URL.
#
# Related scripts in this same directory:
#   sudo bash menu.sh       interactive menu covering install, models,
#                           uninstall, domain/SSL, chat, API keys, DB
#   sudo bash uninstall.sh  reverses everything this script does

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

fix_eol_debian_repos() {
    # Debian codenames go EOL and their security repo (security.debian.org)
    # gets pulled with no replacement — apt-get update/install then fails
    # with 404s on every *-security package. Detect this and route around
    # it instead of failing the whole install over an OS-level repo issue.
    #
    # As of this writing, bullseye (Debian 11) LTS closed end of August
    # 2026 and its security repo returns 404 with no archive available yet.
    # This list may need updating as more codenames go EOL after you're
    # reading this — check https://www.debian.org/releases/ if a future
    # codename hits the same issue.
    local eol_codenames=("bullseye" "buster" "stretch" "jessie")

    [[ -f /etc/os-release ]] || return 0
    . /etc/os-release
    [[ "${ID:-}" == "debian" ]] || return 0

    local codename="${VERSION_CODENAME:-}"
    local is_eol=0
    for c in "${eol_codenames[@]}"; do
        [[ "$codename" == "$c" ]] && is_eol=1 && break
    done
    [[ $is_eol -eq 1 ]] || return 0

    warn "Debian '${codename}' is EOL — its security repo (security.debian.org) is gone."
    warn "Disabling the dead security repo so 'apt-get update' can succeed. This base"
    warn "image will NOT receive further security patches — consider upgrading it."

    local sources_files=(/etc/apt/sources.list /etc/apt/sources.list.d/*.list)
    for f in "${sources_files[@]}"; do
        [[ -f "$f" ]] || continue
        # Comment out any line referencing the dead security suite rather
        # than deleting it, so it's easy to see/restore what was disabled.
        sed -i.bak "/security\.debian\.org/ s/^deb/#deb/" "$f" 2>/dev/null || true
        sed -i "/${codename}-security/ s/^deb/#deb/" "$f" 2>/dev/null || true
    done
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

# Containers (Docker, most CI, some cloud shells) don't run systemd as PID 1.
# install.sh used to assume a full VPS and fail confusingly in that case
# ("System has not been booted with systemd..."). Detect it up front and
# switch to LOCAL_MODE: a plain venv in this directory, no dedicated system
# user, no systemd service, no firewall changes — just get `setup-ai chat`
# and the API runnable by hand.
detect_init_system() {
    if [[ -d /run/systemd/system ]] && command -v systemctl &>/dev/null; then
        LOCAL_MODE=0
        log "systemd detected — installing in PRODUCTION MODE (system user, /opt/firewing, systemd service)."
    else
        LOCAL_MODE=1
        warn "No systemd (this looks like a container or minimal environment)."
        log "Installing in LOCAL MODE instead: a venv right here in $(pwd), no system service, no dedicated user."
        log "(Deploying to a real VPS with systemd later? Just run install.sh there for the full production install.)"
    fi
}

# "Smart verify": check which of the packages this project actually needs
# are importable in the target Python, and only pip-install the ones that
# are missing — instead of blindly re-running the full requirements.txt
# every time, or (the bug you hit) silently doing nothing and leaving you
# with a bare venv.
REQUIRED_MODULES=(yaml torch transformers fastapi uvicorn pydantic accelerate)
module_to_pip_spec() {
    case "$1" in
        yaml) echo "pyyaml>=6.0" ;;
        *) echo "$1" ;;
    esac
}

verify_python_deps() {
    local pybin="$1"   # path to python executable to check/fix
    local missing=()
    log "Verifying required Python packages for ${pybin}..."
    for mod in "${REQUIRED_MODULES[@]}"; do
        if "${pybin}" -c "import ${mod}" &>/dev/null; then
            echo "  [ok]      ${mod}"
        else
            echo "  [missing] ${mod}"
            missing+=("${mod}")
        fi
    done

    if [[ ${#missing[@]} -eq 0 ]]; then
        log "All required packages already present — nothing to install."
        return 0
    fi

    warn "Missing packages: ${missing[*]}"
    log "Installing the full requirements.txt (safer than partial installs, since"
    log "torch/transformers/accelerate versions need to stay in sync)..."
    "${pybin}" -m pip install --upgrade pip
    "${pybin}" -m pip install -r requirements.txt

    local still_missing=()
    for mod in "${missing[@]}"; do
        "${pybin}" -c "import ${mod}" &>/dev/null || still_missing+=("${mod}")
    done
    if [[ ${#still_missing[@]} -gt 0 ]]; then
        die "Still missing after install: ${still_missing[*]}. Check the pip output above for build errors (torch/bitsandbytes are the usual culprits on unusual platforms — see docs/troubleshooting.md)."
    fi
    log "All required packages now present."
}

# "Smart verify files": create the config/.env files a fresh clone is
# missing, without ever clobbering ones you already customized.
verify_config_files() {
    local app_dir="$1"
    local made_any=0
    if [[ ! -f "${app_dir}/configs/firewing.yaml" ]]; then
        if [[ -f "${app_dir}/configs/firewing.example.yaml" ]]; then
            cp "${app_dir}/configs/firewing.example.yaml" "${app_dir}/configs/firewing.yaml"
            log "Created configs/firewing.yaml from the example."
            made_any=1
        else
            die "configs/firewing.example.yaml is missing from this checkout — re-clone the repo, it looks incomplete."
        fi
    else
        log "configs/firewing.yaml already exists — leaving it alone."
    fi
    if [[ ! -f "${app_dir}/.env" ]]; then
        if [[ -f "${app_dir}/.env.example" ]]; then
            cp "${app_dir}/.env.example" "${app_dir}/.env"
            warn "Created .env from .env.example — set FIREWING_API_KEYS/FIREWING_ADMIN_KEY before exposing the API to a network."
            made_any=1
        else
            die ".env.example is missing from this checkout — re-clone the repo, it looks incomplete."
        fi
    else
        log ".env already exists — leaving it alone."
    fi
    [[ $made_any -eq 1 ]] || log "Config files already in place — nothing to create."
}

install_system_deps() {
    log "Installing system packages..."
    fix_eol_debian_repos
    if ! apt-get update -y; then
        die "'apt-get update' failed. If this is an EOL Debian/Ubuntu base image, check its sources.list — see docs/troubleshooting.md ('apt-get 404 on security.debian.org / EOL base image')."
    fi
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
    (cd "${FIREWING_HOME}/app" && verify_python_deps "${VENV_DIR}/bin/python")
    if [[ "${HAS_GPU:-0}" -eq 1 ]]; then
        log "GPU detected — ensure your requirements.txt/torch install matches your CUDA version."
        log "See docs/gpu.md for CUDA-specific install instructions."
    fi
    chown -R "${FIREWING_USER}:${FIREWING_USER}" "${FIREWING_HOME}"
}

setup_config() {
    verify_config_files "${FIREWING_HOME}/app"
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

# ---------------------------------------------------------------------------
# LOCAL MODE — containers / no systemd. No root required beyond what apt
# needs; if apt isn't usable (no root, no network to the package mirror)
# this still proceeds with just the venv + pip steps, which is all `chat`
# actually needs.
# ---------------------------------------------------------------------------
install_local() {
    detect_os
    detect_gpu

    if [[ $EUID -eq 0 ]] && command -v apt-get &>/dev/null; then
        log "Ensuring python3-venv/pip/git are installed..."
        fix_eol_debian_repos
        apt-get update -y || warn "'apt-get update' failed — continuing, this only matters if python3-venv/pip aren't already present."
        apt-get install -y python3 python3-venv python3-pip git curl || warn "Some system packages failed to install — continuing if python3 already works."
    else
        warn "Not root or no apt-get available — skipping system package install. If 'python3 -m venv' fails below, install python3-venv yourself first."
    fi

    if [[ ! -d venv ]]; then
        log "Creating virtual environment at ./venv..."
        python3 -m venv venv
    else
        log "./venv already exists — reusing it."
    fi

    verify_python_deps "$(pwd)/venv/bin/python"
    verify_config_files "$(pwd)"

    log "Local install complete. Running 'doctor' so you know what hardware you actually have:"
    echo
    ./venv/bin/python -m setup_ai.cli.main doctor || true
    echo
    log "Next steps:"
    log "  source venv/bin/activate"
    log "  setup-ai chat                 # or: python -m setup_ai.cli.main chat"
    log "  setup-ai chat --offline       # skip the Hugging Face 'check for updates' network call once weights are cached"
    log "Want the full API server instead of the REPL? uvicorn firewing.api.server:app --host 0.0.0.0 --port 8000"
}

main() {
    detect_init_system
    if [[ $LOCAL_MODE -eq 1 ]]; then
        install_local
        return 0
    fi

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
