# Contributing

Thanks for helping make local-first agent memory boring, inspectable, and reliable.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
PYTHONPATH=src pytest
```

## Pull request expectations

- Add or update tests for behavior changes.
- Keep the core package dependency-light.
- Document user-facing APIs and migration behavior.
- Preserve raw history and identity mappings in migrations.
- Include a short explanation of how the change affects memory correctness, inspectability, or migration safety.

## Commit style

Use concise conventional-style subjects:

- `feat: add peer alias resolution`
- `fix: preserve evidence ids during import`
- `docs: explain deterministic context injection`
- `test: cover session-scoped facts`
