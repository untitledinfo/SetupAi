# Troubleshooting & Known Beta Limitations

## "Model is not loaded yet" (503)

Check `sudo journalctl -u firewing` or `docker compose logs` for a
`ModelLoadError`. Common causes: `model.model_path` unreachable (no
network, or wrong local path), missing `torch`/`transformers`, or
insufficient VRAM for the configured dtype/quantization.

## Rate limiting doesn't work across multiple instances

`firewing/api/security/rate_limit.py` is in-memory and per-process.
Running multiple FIREWING replicas (or multiple uvicorn workers) means
each has its own bucket — a client could get more effective throughput
than the configured limit. Fix: move to a shared store (Redis) before
scaling out.

## Long conversations lose early context

`Conversation.trim_to_budget()` drops the oldest turns once the
context budget is exceeded — there's no summarization yet. If this
matters for your use case, that's the function to extend.

## Quantization fails to install

`bitsandbytes` doesn't build on every platform. If `pip install -r
requirements.txt` fails on that line, remove/comment it and set
`model.quantization: null` in your config — you'll run full precision
(if hardware allows) instead.

## Manual uninstall

The installer wizard's "Uninstall" option is a placeholder in this
beta to avoid accidentally deleting model weights or logs. To remove
manually:

```bash
sudo systemctl stop firewing
sudo systemctl disable firewing
sudo rm /etc/systemd/system/firewing.service
sudo systemctl daemon-reload
sudo rm -rf /opt/firewing
sudo userdel firewing
```

Review before running — this deletes the venv, cached weights, and
config under `/opt/firewing`.
