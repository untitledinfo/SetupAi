# Installation

## Requirements

- Ubuntu 22.04 or 24.04 LTS (other Linux distros may work but aren't tested)
- Python 3.10+
- 32GB+ RAM recommended (see `docs/vps.md` for tiers)
- Optional: NVIDIA GPU with CUDA 12.x for faster inference (see `docs/gpu.md`)

## Option A: git clone + install.sh (recommended)

```bash
git clone <repository>   # replace with your actual repo URL — none is published yet
cd setup-ai
sudo bash install.sh
```

This creates a dedicated `firewing` system user, a Python virtualenv
under `/opt/firewing`, a systemd service, and default config files.

## Option B: manual / local development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp configs/firewing.example.yaml configs/firewing.yaml
cp .env.example .env   # set FIREWING_API_KEYS
```

## Option C: Docker

```bash
cp .env.example .env
docker compose up -d
```

## No curl-pipe installer yet

`curl -fsSL https://example.com/install.sh | bash` is **not** available
because there is no public hosting URL for this project yet. Once you
publish this repository, you can host `install.sh` at a stable URL and
document the one-liner here — don't advertise a URL that doesn't exist.

## After installing

```bash
sudo systemctl start firewing
sudo systemctl status firewing
curl http://localhost:8000/health
```
