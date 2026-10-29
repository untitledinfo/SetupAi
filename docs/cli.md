# CLI Reference

```bash
setup-ai start      # systemctl start firewing (or check local server status)
setup-ai stop       # systemctl stop firewing
setup-ai restart    # systemctl restart firewing
setup-ai status     # checks systemctl service or queries local API /health
setup-ai logs       # journalctl -u firewing -f
setup-ai update     # git pull + reinstall dependencies + restart
setup-ai update --fix # update repository + 1-click auto-repair configs & hardware
setup-ai config     # print resolved configuration
setup-ai doctor     # hardware/environment check (OS, CPU, RAM, GPU, CUDA, disk, Docker)
setup-ai chat       # interactive REPL against the local model
setup-ai chat --self-test    # sends "hi" first, shows thinking + reply, then continues to the REPL
setup-ai chat --persona <name> # specify persona preset (default, coding, concise, creative)
setup-ai bench      # run performance and latency benchmarks directly
setup-ai serve      # launch local Uvicorn API server (--host, --port, --reload, --workers)
setup-ai --version
setup-ai --config <path>   # use a specific config file for any subcommand

# Hardware Matching & Device Inspection
setup-ai device                              # inspect AMD ROCm / NVIDIA CUDA / Apple MPS / Intel XPU / CPU
setup-ai device --apply                      # auto-tune and apply recommended settings to firewing.yaml
setup-ai device --json                       # output machine-readable hardware match JSON

# System Diagnostics & 1-Click Auto-Repair (STRICT DATA PRESERVATION)
setup-ai fix                                 # 1-click auto-fix configs, DB schema, API keys, hardware match
setup-ai fix --check-only                    # diagnose issues without modifying anything
setup-ai fix --no-match-device               # repair configs/DB without altering hardware settings
setup-ai fix --reinstall                     # reinstall core package dependencies (keeps all models & data)
setup-ai fix --json                          # output diagnostic or repair report as JSON

# Model Management
setup-ai model info                          # base model + license + configured path
setup-ai model set --path <hf-repo-or-path>  # point at a different base model
setup-ai model set --adapter <path>          # attach/replace a LoRA adapter
setup-ai model upgrade --path <hf-repo-or-path> [--adapter <path>]
setup-ai model list [--limit 20] [--task ...] # browse popular HF models
setup-ai model search <query> [--limit 20]   # search HF models

# API Key Management
setup-ai keys list                           # list all keys, labels, creation dates, usage
setup-ai keys create <label>                 # generate and display a new API key
setup-ai keys revoke <key_id>                # revoke an existing API key
setup-ai keys delete <key_id>                # permanently delete an API key

# Persistent Conversations Management
setup-ai conv list                           # list recent conversations
setup-ai conv show <conv_id>                 # display conversation messages
setup-ai conv export <conv_id> [--out file]  # export conversation to Markdown
setup-ai conv delete <conv_id>               # delete a conversation
```

`start`/`stop`/`restart`/`status`/`logs` shell out to `systemctl`/
`journalctl` on systemd-based Linux systems. On systems without systemd
(e.g., local development or Windows), `setup-ai status` gracefully checks
the running HTTP API server, and `setup-ai serve` can be used to run the API
server directly.

## `setup-ai device`

Inspects physical GPU hardware across AMD (Radeon / Instinct), NVIDIA (GeForce / RTX / Tesla), Apple Silicon (M-series), Intel (Arc), and CPU. Detects whether PyTorch has matching acceleration active:
- Physical AMD GPU present with CPU PyTorch -> warns with exact ROCm/HIP install command.
- Physical NVIDIA GPU present with CPU PyTorch -> warns with exact CUDA install command.
- Auto-recommends optimal `device`, `dtype`, and `quantization` based on available VRAM.

## `setup-ai fix`

Non-destructively diagnoses and repairs system issues while **strictly preserving all user data**:
1. Creates a safety snapshot in `data/backups/repair_backup_<timestamp>/`.
2. Migrates database schemas non-destructively (`ALTER TABLE conversations ADD COLUMN ...`).
3. Rescues corrupted API key JSON stores via regex record salvage.
4. Generates missing configuration templates without clobbering existing settings.
5. Re-tunes device acceleration settings in `configs/firewing.yaml`.

## Interactive menu (`menu.sh`)

For anyone who'd rather click through numbered options than remember
subcommands, the repo root also ships `menu.sh`, a single entry point:

```bash
git clone https://github.com/untitledinfo/SetupAi.git
cd SetupAi/setup-ai
sudo bash menu.sh
```

```
0) Install Setup AI
1) Models Install
2) Uninstall
3) Domain Link (Cloudflare / IP / DNS)
4) Chat Locally
5) SSL / HTTPS Install
6) API
7) Database
8) Chat with Terminal AI (hi -> thinking -> reply, fully working test)
9) 1-Click Auto-Fix & Repair (Match Hardware AMD/NVIDIA, Fix Bugs, Keep Data)
10) Exit
```
