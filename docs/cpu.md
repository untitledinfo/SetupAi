# CPU-Only Deployment

Set `model.device: cpu` (or leave `auto` on a machine with no GPU) and
strongly consider `model.quantization: int8` or `int4` — a 30B-total
MoE model in full float32 on CPU needs a large amount of RAM and will
be slow.

Minimum realistic tier: 8+ vCPU, 32–64GB RAM, quantized weights. This
is fine for testing the install/API/CLI stack end-to-end; it is not a
low-latency production configuration. Run
`python scripts/bench/benchmark.py` on your actual instance before
committing to it for production traffic — don't rely on assumed
numbers.
