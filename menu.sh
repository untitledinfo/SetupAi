#!/usr/bin/env bash
# Setup AI / FIREWING — interactive management menu.
#
# Usage:
#   git clone https://github.com/untitledinfo/SetupAi.git
#   cd SetupAi/setup-ai        # (or wherever install.sh lives in your clone)
#   sudo bash menu.sh
#
# This wraps install.sh / uninstall.sh / the setup-ai CLI / nginx / certbot /
# Cloudflare's API behind one numbered menu. Every option shells out to a
# real, auditable command rather than hiding anything — read the functions
# below before running them on a production box.

set -uo pipefail

FIREWING_USER="firewing"
FIREWING_HOME="/opt/firewing"
DATA_DIR="/var/lib/firewing"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer the installed app dir if install.sh has already run; otherwise
# operate on this checkout directly (useful for local/dev before install).
if [[ -d "${FIREWING_HOME}/app" ]]; then
    APP_DIR="${FIREWING_HOME}/app"
    VENV_DIR="${FIREWING_HOME}/venv"
else
    APP_DIR="${SCRIPT_DIR}"
    VENV_DIR="${SCRIPT_DIR}/venv"
fi
CONFIG_FILE="${APP_DIR}/configs/firewing.yaml"
ENV_FILE="${APP_DIR}/.env"

log()  { echo -e "\033[1;32m[setup-ai]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
err()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; }
pause() { read -r -p "Press Enter to return to the menu..." _; }

need_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This action needs root — rerun with: sudo bash menu.sh"
        return 1
    fi
}

venv_python() {
    if [[ -x "${VENV_DIR}/bin/python" ]]; then
        echo "${VENV_DIR}/bin/python"
    else
        command -v python3
    fi
}

# ---------------------------------------------------------------------------
# 0. Install
# ---------------------------------------------------------------------------
action_install() {
    need_root || return
    bash "${SCRIPT_DIR}/install.sh"
}

# ---------------------------------------------------------------------------
# 1. Models install / switch / upgrade — makes the served model "yours":
#    point at a Hugging Face repo, a local checkpoint, or your own LoRA
#    adapter trained via docs/training.md.
# ---------------------------------------------------------------------------
action_models() {
    echo
    echo "  1) Use a Hugging Face model (e.g. Qwen/Qwen3-Omni-30B-A3B-Instruct or your own HF repo)"
    echo "  2) Use a local checkpoint path"
    echo "  3) Attach/replace a LoRA adapter (your own fine-tune) on top of the current base model"
    echo "  4) Show current model config"
    echo "  5) Browse popular models on Hugging Face (no API key needed)"
    echo "  6) Search Hugging Face by keyword (no API key needed)"
    read -r -p "Choose [1-6]: " choice

    local py
    py="$(venv_python)"

    case "$choice" in
        1)
            read -r -p "Hugging Face repo id: " repo
            [[ -z "$repo" ]] && { err "No repo id given."; return; }
            log "Setting model_path=${repo} in ${CONFIG_FILE}"
            (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main --config "${CONFIG_FILE}" model set --path "$repo")
            log "First load will download the weights via huggingface_hub — this can take a while and needs disk space."
            ;;
        2)
            read -r -p "Local model path: " path
            [[ -d "$path" ]] || warn "Path does not exist yet — that's fine if you're about to populate it."
            (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main --config "${CONFIG_FILE}" model set --path "$path")
            ;;
        3)
            read -r -p "Path to your trained LoRA adapter (see docs/training.md): " adapter
            [[ -z "$adapter" ]] && { err "No adapter path given."; return; }
            (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main --config "${CONFIG_FILE}" model set --adapter "$adapter")
            log "Adapter set. FIREWING is still built on the upstream base model + your adapter on top —"
            log "that combination is the closest thing to 'your own model' this project supports honestly."
            ;;
        4)
            (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main --config "${CONFIG_FILE}" model info)
            ;;
        5)
            read -r -p "How many to show [20]: " n
            (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main model list --limit "${n:-20}")
            ;;
        6)
            read -r -p "Search keyword (e.g. qwen, llama, omni): " kw
            [[ -z "$kw" ]] && { err "No keyword given."; return; }
            (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main model search "$kw")
            ;;
        *) err "Invalid choice." ;;
    esac
    if [[ -d /etc/systemd/system ]] && systemctl list-unit-files 2>/dev/null | grep -q '^firewing.service'; then
        echo
        read -r -p "Restart the firewing service now to apply? [y/N] " r
        [[ "$r" =~ ^[Yy]$ ]] && { need_root && systemctl restart firewing && log "Restarted."; }
    fi
}

# ---------------------------------------------------------------------------
# 2. Uninstall
# ---------------------------------------------------------------------------
action_uninstall() {
    need_root || return
    read -r -p "Also purge model cache / conversations.db / API keys / logs? [y/N] " r
    if [[ "$r" =~ ^[Yy]$ ]]; then
        bash "${SCRIPT_DIR}/uninstall.sh" --purge
    else
        bash "${SCRIPT_DIR}/uninstall.sh"
    fi
}

# ---------------------------------------------------------------------------
# 3. Domain link — Cloudflare DNS pointed at this server's IP, then an
#    nginx reverse-proxy vhost for that domain.
# ---------------------------------------------------------------------------
action_domain() {
    need_root || return
    read -r -p "Domain (e.g. ai.example.com): " domain
    [[ -z "$domain" ]] && { err "No domain given."; return; }

    read -r -p "Public IPv4 of this server (leave blank to auto-detect): " ip
    if [[ -z "$ip" ]]; then
        ip="$(curl -fsSL https://api.ipify.org || true)"
        [[ -z "$ip" ]] && { err "Could not auto-detect IP. Re-run and enter it manually."; return; }
        log "Detected public IP: ${ip}"
    fi

    read -r -p "Configure DNS via Cloudflare API now? [y/N] " use_cf
    if [[ "$use_cf" =~ ^[Yy]$ ]]; then
        read -r -p "Cloudflare Zone ID: " cf_zone
        read -r -s -p "Cloudflare API token (Zone.DNS edit permission): " cf_token
        echo
        read -r -p "Proxy through Cloudflare (orange cloud)? [y/N] " cf_proxied
        local proxied="false"
        [[ "$cf_proxied" =~ ^[Yy]$ ]] && proxied="true"

        local existing_id
        existing_id="$(curl -fsSL -X GET \
            "https://api.cloudflare.com/client/v4/zones/${cf_zone}/dns_records?type=A&name=${domain}" \
            -H "Authorization: Bearer ${cf_token}" -H "Content-Type: application/json" \
            | python3 -c 'import sys,json; d=json.load(sys.stdin); r=d.get("result") or []; print(r[0]["id"] if r else "")' 2>/dev/null)"

        local payload
        payload=$(python3 -c "import json; print(json.dumps({'type':'A','name':'${domain}','content':'${ip}','ttl':1,'proxied':${proxied}}))")

        if [[ -n "$existing_id" ]]; then
            log "Updating existing A record (${existing_id}) for ${domain}..."
            curl -fsSL -X PUT "https://api.cloudflare.com/client/v4/zones/${cf_zone}/dns_records/${existing_id}" \
                -H "Authorization: Bearer ${cf_token}" -H "Content-Type: application/json" \
                --data "$payload" | python3 -m json.tool
        else
            log "Creating A record for ${domain} -> ${ip}..."
            curl -fsSL -X POST "https://api.cloudflare.com/client/v4/zones/${cf_zone}/dns_records" \
                -H "Authorization: Bearer ${cf_token}" -H "Content-Type: application/json" \
                --data "$payload" | python3 -m json.tool
        fi
        log "If DNS was just created, allow a few minutes to propagate before requesting SSL (menu option 5)."
    else
        log "Skipping Cloudflare — create the A record for ${domain} -> ${ip} manually with your DNS provider."
    fi

    if command -v nginx &>/dev/null; then
        log "Writing nginx vhost for ${domain}..."
        sed "s/ai\.example\.com/${domain}/" "${SCRIPT_DIR}/scripts/deploy/nginx.conf.example" \
            > "/etc/nginx/sites-available/firewing"
        ln -sf /etc/nginx/sites-available/firewing /etc/nginx/sites-enabled/firewing
        if nginx -t; then
            systemctl reload nginx
            log "nginx configured for ${domain} -> 127.0.0.1:8000. Now run option 5 to get HTTPS."
        else
            err "nginx config test failed — check /etc/nginx/sites-available/firewing"
        fi
    else
        warn "nginx not installed. Install it first: sudo apt-get install -y nginx"
    fi
}

# ---------------------------------------------------------------------------
# 4. Chat locally
# ---------------------------------------------------------------------------
action_chat() {
    local py
    py="$(venv_python)"
    if [[ ! -x "$py" ]]; then
        err "No Python found. Run option 0 (install) or create a venv first."
        return
    fi
    (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main --config "${CONFIG_FILE}" chat)
}

# ---------------------------------------------------------------------------
# 5. SSL / HTTPS via certbot
# ---------------------------------------------------------------------------
action_ssl() {
    need_root || return
    read -r -p "Domain to issue a certificate for (must already resolve here): " domain
    [[ -z "$domain" ]] && { err "No domain given."; return; }

    if ! command -v certbot &>/dev/null; then
        log "Installing certbot..."
        apt-get update -y && apt-get install -y certbot python3-certbot-nginx
    fi
    read -r -p "Email for renewal notices (blank to register --register-unsafely-without-email): " email
    if [[ -n "$email" ]]; then
        certbot --nginx -d "$domain" -m "$email" --agree-tos --non-interactive || \
            certbot --nginx -d "$domain" -m "$email"
    else
        certbot --nginx -d "$domain" --register-unsafely-without-email --agree-tos --non-interactive || \
            certbot --nginx -d "$domain"
    fi
    log "certbot installs a systemd timer for auto-renewal — verify with: systemctl list-timers | grep certbot"
}

# ---------------------------------------------------------------------------
# 6. API — manage keys via the admin API (needs the service running and
#    FIREWING_ADMIN_KEY set in .env)
# ---------------------------------------------------------------------------
action_api() {
    if [[ ! -f "$ENV_FILE" ]]; then
        err "No .env found at ${ENV_FILE}. Run option 0 (install) first."
        return
    fi
    local admin_key host port
    admin_key="$(grep -E '^FIREWING_ADMIN_KEY=' "$ENV_FILE" | cut -d= -f2- || true)"
    host="127.0.0.1"
    port="$(grep -E '^FIREWING_API_PORT=' "$ENV_FILE" | cut -d= -f2- || echo 8000)"
    if [[ -z "$admin_key" ]]; then
        err "FIREWING_ADMIN_KEY is not set in ${ENV_FILE}. Set it, restart the service, and try again."
        return
    fi
    local base="http://${host}:${port}/v1/admin"

    echo
    echo "  1) List API keys"
    echo "  2) Create a new API key"
    echo "  3) Revoke an API key"
    echo "  4) Show request stats"
    read -r -p "Choose [1-4]: " choice
    case "$choice" in
        1) curl -fsSL "${base}/keys" -H "Authorization: Bearer ${admin_key}" | python3 -m json.tool ;;
        2)
            read -r -p "Label for the new key: " label
            curl -fsSL -X POST "${base}/keys" -H "Authorization: Bearer ${admin_key}" \
                -H "Content-Type: application/json" --data "$(python3 -c "import json;print(json.dumps({'label':'${label}'}))")" \
                | python3 -m json.tool
            warn "The api_key field above is shown once only — copy it now."
            ;;
        3)
            read -r -p "key_id to revoke: " key_id
            curl -fsSL -X DELETE "${base}/keys/${key_id}" -H "Authorization: Bearer ${admin_key}" | python3 -m json.tool
            ;;
        4) curl -fsSL "${base}/stats" -H "Authorization: Bearer ${admin_key}" | python3 -m json.tool ;;
        *) err "Invalid choice." ;;
    esac
}

# ---------------------------------------------------------------------------
# 7. Database — the SQLite conversation store + JSON key store under
#    data_dir (default /var/lib/firewing)
# ---------------------------------------------------------------------------
action_database() {
    local db="${DATA_DIR}/conversations.db"
    local keys="${DATA_DIR}/api_keys.json"

    echo
    echo "  1) Show info (paths, sizes, conversation/message counts)"
    echo "  2) Backup now (copy to a timestamped file)"
    echo "  3) Vacuum (compact) the conversations DB"
    echo "  4) Reset — delete conversations DB (destructive)"
    read -r -p "Choose [1-4]: " choice
    case "$choice" in
        1)
            echo "Data dir:      ${DATA_DIR}"
            [[ -f "$db" ]] && echo "Conversations: $db ($(du -h "$db" | cut -f1))" || echo "Conversations: not created yet"
            [[ -f "$keys" ]] && echo "API keys file: $keys ($(python3 -c "import json;print(len(json.load(open('${keys}'))))" 2>/dev/null || echo '?') keys)" || echo "API keys file: not created yet"
            if [[ -f "$db" ]] && command -v sqlite3 &>/dev/null; then
                echo "Conversations: $(sqlite3 "$db" 'select count(*) from conversations;' 2>/dev/null || echo '?')"
            fi
            ;;
        2)
            [[ -f "$db" ]] || { err "No DB found at $db yet."; return; }
            need_root || return
            local backup="${DATA_DIR}/conversations.db.$(date +%Y%m%d%H%M%S).bak"
            cp "$db" "$backup"
            log "Backed up to $backup"
            ;;
        3)
            [[ -f "$db" ]] || { err "No DB found at $db yet."; return; }
            command -v sqlite3 &>/dev/null || { err "sqlite3 CLI not installed (sudo apt-get install sqlite3)."; return; }
            sqlite3 "$db" 'VACUUM;'
            log "Vacuumed $db"
            ;;
        4)
            need_root || return
            read -r -p "This deletes all stored conversations permanently. Type 'yes' to confirm: " confirm
            [[ "$confirm" == "yes" ]] || { log "Cancelled."; return; }
            local backup="${DATA_DIR}/conversations.db.$(date +%Y%m%d%H%M%S).bak"
            [[ -f "$db" ]] && cp "$db" "$backup" && log "Safety backup written to $backup"
            rm -f "$db"
            log "Deleted $db — a fresh one is created on next service start."
            ;;
        *) err "Invalid choice." ;;
    esac
}

# ---------------------------------------------------------------------------
# 8. Chat with Terminal AI — proves the pipeline is actually working
#    (sends "hi", shows a thinking indicator, shows the real streamed
#    reply) then drops you straight into the normal interactive REPL.
# ---------------------------------------------------------------------------
action_chat_test() {
    local py
    py="$(venv_python)"
    if [[ ! -x "$py" ]]; then
        err "No Python found. Run option 0 (install) first — it creates the venv and installs torch/transformers."
        return
    fi
    if ! "$py" -c "import torch, transformers" &>/dev/null; then
        warn "torch/transformers aren't installed yet in this venv."
        read -r -p "Install requirements.txt now? [y/N] " r
        if [[ "$r" =~ ^[Yy]$ ]]; then
            (cd "${APP_DIR}" && "$py" -m pip install -r requirements.txt)
        else
            err "Can't chat without torch/transformers. Run option 0 or 'pip install -r requirements.txt'."
            return
        fi
    fi
    log "Sending a test message ('hi') to confirm FIREWING loads and replies, then handing off to interactive chat..."
    (cd "${APP_DIR}" && "$py" -m setup_ai.cli.main --config "${CONFIG_FILE}" chat --self-test)
}

# ---------------------------------------------------------------------------
main_menu() {
    while true; do
        cat <<'EOF'

========================================
        SETUP AI — FIREWING
========================================
  0) Install Setup AI
  1) Models Install
  2) Uninstall
  3) Domain Link (Cloudflare / IP / DNS)
  4) Chat Locally
  5) SSL / HTTPS Install
  6) API
  7) Database
  8) Chat with Terminal AI (hi -> thinking -> reply, fully working test)
  9) Exit
EOF
        read -r -p "Choose an option [0-9]: " opt
        case "$opt" in
            0) action_install ;;
            1) action_models ;;
            2) action_uninstall ;;
            3) action_domain ;;
            4) action_chat ;;
            5) action_ssl ;;
            6) action_api ;;
            7) action_database ;;
            8) action_chat_test ;;
            9) exit 0 ;;
            *) err "Invalid option." ;;
        esac
        pause
    done
}

main_menu
