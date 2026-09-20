# CLI Reference

```
setup-ai start      # systemctl start firewing
setup-ai stop       # systemctl stop firewing
setup-ai restart    # systemctl restart firewing
setup-ai status     # systemctl status firewing
setup-ai logs       # journalctl -u firewing -f
setup-ai update     # pull + reinstall + restart (placeholder — wire to your deploy method)
setup-ai config     # print resolved configuration
setup-ai doctor     # hardware/environment check (OS, CPU, RAM, GPU, CUDA, disk, Docker)
setup-ai chat        # interactive REPL against the local model
setup-ai --version
setup-ai --config <path>   # use a specific config file for any subcommand

setup-ai model info                          # base model + license + configured path
setup-ai model set --path <hf-repo-or-path>  # point at a different base model
setup-ai model set --adapter <path>          # attach/replace a LoRA adapter
setup-ai model upgrade --path <hf-repo-or-path> [--adapter <path>]
```

`start`/`stop`/`restart`/`status`/`logs` shell out to `systemctl`/
`journalctl` and expect the systemd service installed by `install.sh`
to exist. Running them without that service installed will just
surface the underlying `systemctl` error.

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
local chat, API key management, and the database:

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
8) Exit
```

Every option shells out to a real, readable command (`install.sh`,
`uninstall.sh`, the `setup-ai` CLI above, `nginx`, `certbot`, and the
Cloudflare API) — nothing is hidden, so it's worth reading `menu.sh`
once before running it against a production box. See
[Installation](installation.md) for what each underlying step does.
