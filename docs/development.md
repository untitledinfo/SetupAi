# Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

## Running tests

Config/API/health tests run without any GPU or downloaded weights:

```bash
pytest tests/
```

Full generation-path testing needs real Qwen3-Omni weights downloaded
and is intentionally kept out of the default test run — see
`tests/README.md` (add one if you introduce GPU-tagged tests).

## Code layout

See the tree in `README.md`. Key boundary to keep in mind: anything
under `firewing/model/` and `firewing/tokenizer/` talks to the
upstream Qwen3-Omni model; everything else in `firewing/` is FIREWING's
own application layer and should not assume details of a specific
base model beyond that thin interface.

## Linting / formatting

Not yet configured — add `ruff`/`black` and a pre-commit config as the
project matures.
