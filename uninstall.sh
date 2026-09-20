#!/usr/bin/env bash
# Setup AI / FIREWING uninstaller — reverses what install.sh did.
#
# Usage:
#   sudo bash uninstall.sh            # interactive, asks before deleting data
#   sudo bash uninstall.sh --purge    # also deletes model weights, DB, API keys, logs
#   sudo bash uninstall.sh --yes      # skip confirmation prompts (still respects --purge)

set -uo pipefail

FIREWING_USER="firewing"
FIREWING_HOME="/opt/firewing"
DATA_DIR="/var/lib/firewing"
LOG_DIR="/var/log/firewing"

PURGE=0
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        --yes|-y) ASSUME_YES=1 ;;
        *) echo "Unknown flag: $arg" >&2; exit 1 ;;
    esac
done

log()  { echo -e "\033[1;32m[uninstall]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "This needs root (sudo bash uninstall.sh)." >&2
        exit 1
    fi
}

confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    read -r -p "$1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

stop_service() {
    if systemctl list-unit-files 2>/dev/null | grep -q '^firewing.service'; then
        log "Stopping and disabling the firewing service..."
        systemctl stop firewing 2>/dev/null || true
        systemctl disable firewing 2>/dev/null || true
        rm -f /etc/systemd/system/firewing.service
        systemctl daemon-reload
    else
        log "No firewing systemd service found — skipping."
    fi
}

remove_nginx() {
    if [[ -e /etc/nginx/sites-enabled/firewing ]]; then
        if confirm "Remove the nginx site config for FIREWING (/etc/nginx/sites-*/firewing)?"; then
            rm -f /etc/nginx/sites-enabled/firewing /etc/nginx/sites-available/firewing
            command -v nginx &>/dev/null && systemctl reload nginx 2>/dev/null || true
            log "Removed nginx site config."
        fi
    fi
}

remove_app() {
    if [[ -d "${FIREWING_HOME}" ]]; then
        if [[ $PURGE -eq 1 ]] || confirm "Remove the application directory ${FIREWING_HOME} (venv + code)?"; then
            rm -rf "${FIREWING_HOME}"
            log "Removed ${FIREWING_HOME}."
        fi
    fi
}

remove_data() {
    for dir in "${DATA_DIR}" "${LOG_DIR}"; do
        [[ -d "$dir" ]] || continue
        if [[ $PURGE -eq 1 ]]; then
            rm -rf "$dir"
            log "Purged $dir."
        elif confirm "Delete $dir? (This holds model weights cache, conversations.db, api_keys.json, logs — say no to keep for a reinstall)"; then
            rm -rf "$dir"
            log "Removed $dir."
        else
            log "Kept $dir."
        fi
    done
}

remove_user() {
    if id "${FIREWING_USER}" &>/dev/null; then
        if confirm "Remove the system user '${FIREWING_USER}'?"; then
            userdel "${FIREWING_USER}" 2>/dev/null || warn "Could not remove user ${FIREWING_USER} (may still own files)."
            log "Removed user ${FIREWING_USER}."
        fi
    fi
}

main() {
    require_root
    log "Uninstalling Setup AI / FIREWING..."
    stop_service
    remove_nginx
    remove_app
    remove_data
    remove_user
    log "Uninstall complete."
    if [[ $PURGE -eq 0 ]]; then
        log "Some directories may have been kept — rerun with --purge to remove everything."
    fi
}

main
