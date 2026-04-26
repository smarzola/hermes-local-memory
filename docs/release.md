# Release checklist

This project uses standard Python packaging metadata in `pyproject.toml` and GitHub Actions CI.

## Version policy

Until the first stable release, use `0.x.y` versions:

- `0.1.0`, `0.2.0`, ... for feature milestones
- patch versions for fixes after a released version

Before publishing a release, update:

- `pyproject.toml` → `[project].version`
- README status text if maturity changed
- `CHANGELOG.md` with user-facing changes
- release notes / GitHub tag body

## Pre-release checks

Run from the repository root:

```bash
git status --short
PYTHONPATH=src pytest -q
ruff check .
PYTHONPATH=src python -m compileall -q src tests
```

Build the package in a throwaway environment. With `uv`:

```bash
uv build
```

Or with standard Python tooling:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

Inspect artifacts:

```bash
python - <<'PY'
from pathlib import Path
for path in sorted(Path('dist').glob('*')):
    print(path, path.stat().st_size)
PY
```

## Smoke install from the wheel

Use a temporary virtualenv:

```bash
TMPDIR=$(mktemp -d)
python -m venv "$TMPDIR/venv"
"$TMPDIR/venv/bin/python" -m pip install dist/*.whl
"$TMPDIR/venv/bin/hermes-local-memory" --help
"$TMPDIR/venv/bin/python" - <<'PY'
from hermes_local_memory import LocalMemoryProvider, LocalMemoryStore
print(LocalMemoryProvider().name)
print(LocalMemoryStore)
PY
rm -rf "$TMPDIR"
```

If the default Python environment lacks `pip`, use `uv`:

```bash
TMPDIR=$(mktemp -d)
uv venv "$TMPDIR/venv"
uv pip install --python "$TMPDIR/venv/bin/python" dist/*.whl
"$TMPDIR/venv/bin/hermes-local-memory" --help
rm -rf "$TMPDIR"
```

## Shim smoke test

From an installed wheel or checkout:

```bash
TMP_HOME=$(mktemp -d /tmp/hermes-local-memory-release.XXXXXX)
hermes-local-memory install-shim --hermes-home "$TMP_HOME"
test -f "$TMP_HOME/plugins/local_memory/__init__.py"
rm -rf "$TMP_HOME"
```

## GitHub release and PyPI publish

Release creation and PyPI publication are handled by GitHub Actions, not by a developer machine.
The `Publish to PyPI` workflow runs only for pushed tags matching `v*`, builds the artifacts,
runs `twine check`, creates the GitHub release with those artifacts attached, and publishes the
exact tagged source to PyPI using Trusted Publishing / OIDC.

Do **not** run local `twine upload`, and do **not** create the GitHub release manually with local
artifacts. Local builds are only preflight/smoke checks.

Before pushing a release tag:

1. Configure a PyPI Trusted Publisher for this repository and the
   `.github/workflows/publish.yml` workflow.
2. Confirm local pre-release checks pass.
3. Push the version tag.

Tag and push:

```bash
VERSION=0.2.1
git tag -a "v$VERSION" -m "v$VERSION"
git push origin "v$VERSION"
```

After pushing the tag, monitor the `Publish to PyPI` workflow. The workflow-generated GitHub
release notes should include or be edited to include:

- headline summary
- install command
- migration paths supported
- safety notes: trial DB, dry-run first, raw history preserved
- known limitations / pre-alpha caveats
- maintenance safety notes when behavior changes candidate promotion, card synthesis, identity reconciliation, or scheduled jobs

The workflow publishes to PyPI and then creates the GitHub release from the same CI-built `dist/*`
artifacts, so the release artifacts and published package come from the same tagged build.

## Post-release verification

```bash
uv tool install hermes-local-memory
hermes-local-memory --help
hermes-local-memory install-shim --hermes-home /tmp/hermes-local-memory-postrelease
rm -rf /tmp/hermes-local-memory-postrelease
```

Then update any documentation that still references installing from GitHub only.
