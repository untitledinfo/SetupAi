# VPS Sizing

| Tier | Hardware | Use case |
|---|---|---|
| Minimum | 8+ vCPU, 32–64GB RAM, CPU-only | Testing the install/API/CLI stack; not for production latency |
| Recommended | 1x GPU ≥24GB VRAM, 32GB RAM | Quantized inference, small-team/personal use |
| Production | 1x GPU 48–80GB VRAM (or multi-GPU), 64GB+ RAM | Higher precision, higher concurrency |

These are starting points, not guarantees — validate with
`scripts/bench/benchmark.py` on your actual target instance.

## Production topology

```
Internet → Domain → Nginx (TLS) → Setup AI API (127.0.0.1:8000, internal) → FIREWING
```

Keep the FIREWING API bound to localhost or an internal network
interface; only nginx should be internet-facing. See
`scripts/deploy/nginx.conf.example` and `docs/security.md`.

## Required open ports

- 22 (SSH, restrict via firewall/key auth)
- 80/443 on the nginx host (if used)
- The FIREWING API port (default 8000) should **not** be exposed
  publicly — nginx proxies to it over localhost/internal network.
