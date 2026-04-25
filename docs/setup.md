# Setup and adoption guide

This guide is for both humans and agents setting up Hermes Local Memory.

Hermes Local Memory is deliberately split into two pieces:

1. the installable Python package and CLI (`hermes-local-memory`), and
2. a small Hermes plugin shim installed into `$HERMES_HOME/plugins/local_memory/`.

The shim lets Hermes discover the provider. Installing the shim does **not** switch the active memory provider. Switching happens only when the Hermes config sets `memory.provider: local_memory`.

## Install options

### Recommended: install the published package

For normal human or agent use, install the published PyPI package as a CLI tool:

```bash
uv tool install hermes-local-memory
# or
pipx install hermes-local-memory
```

If you are already inside a virtualenv:

```bash
pip install hermes-local-memory
```

Then verify the CLI:

```bash
hermes-local-memory --help
```

### Development path: clone from GitHub

Use a checkout only when developing the package, testing unreleased changes, or debugging from source:

```bash
git clone https://github.com/smarzola/hermes-local-memory.git
cd hermes-local-memory
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
PYTHONPATH=src pytest -q
ruff check .
```

Run commands from a checkout with:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli --help
```

## Install the Hermes plugin shim

If installed from PyPI/pipx/uv:

```bash
hermes-local-memory install-shim --hermes-home ~/.hermes
```

If running from a GitHub checkout:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
```

This writes:

```text
~/.hermes/plugins/local_memory/__init__.py
```

The shim imports `LocalMemoryProvider` and registers it with Hermes. It does not edit `~/.hermes/config.yaml`.

## Validate without switching providers

Use a temporary Hermes home first:

```bash
TMP_HOME=$(mktemp -d /tmp/hermes-local-memory.XXXXXX)
hermes-local-memory install-shim --hermes-home "$TMP_HOME"
cat > "$TMP_HOME/config.yaml" <<'YAML'
memory:
  provider: local_memory
YAML
```

Then run a small provider smoke test from a checkout:

```bash
HERMES_HOME="$TMP_HOME" \
PYTHONPATH="/path/to/hermes-agent:/path/to/hermes-local-memory/src" \
python - <<'PY'
from plugins.memory import discover_memory_providers, load_memory_provider
assert any(p[0] == 'local_memory' and p[2] for p in discover_memory_providers())
provider = load_memory_provider('local_memory')
assert provider is not None
provider.initialize(
    'setup-smoke',
    hermes_home='/tmp/local-memory-smoke',
    platform='cli',
    user_id='alice',
    agent_identity='bob',
)
print(provider.name)
print(sorted(schema['name'] for schema in provider.get_tool_schemas()))
PY
```

For an installed package, the checkout path is not needed; include only the Hermes Agent path in `PYTHONPATH` if your Hermes install requires it.

## Create a trial database

Do not start by writing into the live provider database. Pick a trial DB:

```bash
export LOCAL_MEMORY_DB=~/.hermes/memory/local_memory_trial.sqlite
```

Inspect the empty DB:

```bash
hermes-local-memory --db "$LOCAL_MEMORY_DB" peers --json
hermes-local-memory --db "$LOCAL_MEMORY_DB" aliases --json
```

## Migrate existing memory

### From Hermes built-in markdown memory

```bash
hermes-local-memory --db "$LOCAL_MEMORY_DB" import hermes-markdown \
  --source-dir ~/.hermes/memories \
  --user-peer alice \
  --assistant-peer bob \
  --dry-run \
  --json
```

Apply after reviewing the dry-run:

```bash
hermes-local-memory --db "$LOCAL_MEMORY_DB" import hermes-markdown \
  --source-dir ~/.hermes/memories \
  --user-peer alice \
  --assistant-peer bob \
  --apply \
  --json
```

### From Honcho

Prefer the API importer:

```bash
hermes-local-memory --db "$LOCAL_MEMORY_DB" import honcho-api \
  --base-url http://localhost:8000/v3 \
  --workspace hermes \
  --identity-map ~/.hermes/local-memory-identity-map.json \
  --dry-run \
  --json
```

Then apply after reviewing counts, peers, aliases, cards, and warnings:

```bash
hermes-local-memory --db "$LOCAL_MEMORY_DB" import honcho-api \
  --base-url http://localhost:8000/v3 \
  --workspace hermes \
  --identity-map ~/.hermes/local-memory-identity-map.json \
  --apply \
  --json
```

## Inspect before switching

```bash
hermes-local-memory --db "$LOCAL_MEMORY_DB" peers --json
hermes-local-memory --db "$LOCAL_MEMORY_DB" aliases --json
hermes-local-memory --db "$LOCAL_MEMORY_DB" cards --json
hermes-local-memory --db "$LOCAL_MEMORY_DB" facts --status active --json
hermes-local-memory --db "$LOCAL_MEMORY_DB" context \
  --peer alice \
  --observer bob \
  --query "memory setup"
```

For Honcho imports, run review workflows before judging quality:

```bash
hermes-local-memory --db "$LOCAL_MEMORY_DB" peer-review-packet --json
hermes-local-memory --db "$LOCAL_MEMORY_DB" candidate-review-packet \
  --peer alice \
  --observer bob \
  --limit 100 \
  --json
hermes-local-memory --db "$LOCAL_MEMORY_DB" card-review-packet \
  --peer alice \
  --observer bob \
  --json
```

## Configure Hermes after validation

Only after the shim loads and the trial DB/context look correct, configure Hermes:

```yaml
memory:
  provider: local_memory
```

Then restart Hermes or start a new session.

## Agent handoff checklist

If a human asks an agent to set up Local Memory, the agent should:

1. install the published package with `uv tool install hermes-local-memory` or `pipx install hermes-local-memory`;
2. verify `hermes-local-memory --help` works;
3. install the shim with `hermes-local-memory install-shim --hermes-home ~/.hermes` without switching providers;
4. choose a trial DB;
5. import existing memory with `--dry-run` first;
6. apply only after reviewing counts/warnings;
7. render `memory_context` / `context` and compare quality;
8. run peer/candidate/card review packets for imported data;
9. schedule maintenance as dry-run/report-first; allow autonomous apply only for bounded, conservative fact-lifecycle changes;
10. use card review or validated `card_replace` patches for compact card synthesis/cleanup;
11. switch `memory.provider` only after explicit human approval.

Agents should clone the GitHub repo and run `PYTHONPATH=src ...` commands only when they are developing the package or testing unreleased changes.

## Rollback basics

- Installing the shim is reversible: remove `~/.hermes/plugins/local_memory/`.
- Imports are additive and back up existing DBs on apply unless `--no-backup` is used.
- Keep the previous provider configured until the Local Memory trial DB is inspected.
- To roll back provider selection, restore the previous `memory.provider` value in `~/.hermes/config.yaml` and restart Hermes.
