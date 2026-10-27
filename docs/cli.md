# CLI Reference

```bash
setup-ai start      # systemctl start firewing (or check local server status)
setup-ai stop       # systemctl stop firewing
setup-ai restart    # systemctl restart firewing
setup-ai status     # checks systemctl service or queries local API /health
setup-ai logs       # journalctl -u firewing -f
setup-ai update     # git pull + reinstall dependencies + restart
setup-ai config     # print resolved configuration
setup-ai doctor     # hardware/environment check (OS, CPU, RAM, GPU, CUDA, disk, Docker)
setup-ai chat       # interactive REPL against the local model
setup-ai chat --self-test    # sends "hi" first, shows thinking + reply, then continues to the REPL
setup-ai chat --persona <name> # specify persona preset (default, coding, concise, creative)
setup-ai bench      # run performance and latency benchmarks directly
setup-ai serve      # launch local Uvicorn API server (--host, --port, --reload, --workers)
setup-ai --version
setup-ai --config <path>   # use a specific config file for any subcommand

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

## `model set` / `model upgrade`

These edit `model_path` / `adapter_path` in your config YAML — they
don't download or validate anything themselves; the actual weights are
fetched by `transformers` the next time the service loads the model.
"Upgrading" the model means pointing at a newer upstream revision, a
different base checkpoint, or (for something that's genuinely yours)
your own LoRA adapter from [Fine-Tuning](training.md). FIREWING does
not — and cannot honestly claim to — turn the upstream Qwen3-Omni
weights themselves into an independently trained model; see the
[Model Card](model-card.md).

```bash
setup-ai model set --path Qwen/Qwen3-Omni-30B-A3B-Instruct
setup-ai model set --adapter /opt/firewing/adapters/my-finetune
sudo systemctl restart firewing   # apply the change
```

## Interactive menu (`menu.sh`)

For anyone who'd rather click through numbered options than remember
subcommands, the repo root also ships `menu.sh`, a single entry point
covering install, model management, uninstall, domain/DNS + SSL setup,
local chat, API key management, the database, and a one-shot chat
self-test:

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
9) Exit
```
