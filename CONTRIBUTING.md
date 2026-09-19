# Contributing

Thanks for considering contributing to Setup AI / FIREWING.

## Before you start

- FIREWING is built on Qwen3-Omni (Apache 2.0) — see `/NOTICE`. Any
  contribution that touches model loading/attribution must keep that
  notice accurate. Don't remove or obscure upstream credit.
- No fabricated benchmark numbers, ever. If you add a claim about
  performance, it must come from `scripts/bench/benchmark.py` output
  on real hardware, with the hardware stated.
- No hardcoded secrets, API keys, or fake download URLs.

## Workflow

1. Fork and branch from `main`.
2. `pip install -e ".[dev]"`
3. Make your change, add/update tests under `tests/`.
4. `pytest tests/` must pass.
5. Open a PR using the template — describe what changed and why.

## Code style

- Type hints on new code where practical.
- Keep `firewing/model/` and `firewing/tokenizer/` as the only places
  that know about upstream Qwen3-Omni specifics; everything else
  should go through their thin interfaces.
- Prefer small, reviewable PRs over large ones.

## Reporting bugs

Open a GitHub issue with your OS, GPU (if any), `setup-ai doctor`
output, and steps to reproduce. For security issues, see
`SECURITY.md` instead — don't open a public issue.
