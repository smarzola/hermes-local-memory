# Features

This document describes current and planned Hermes Local Memory features.

## Current features

### Local SQLite database

Local Memory stores its data in SQLite. The default provider location is:

```text
$HERMES_HOME/memory/local_memory.sqlite
```

The store uses SQLite FTS5 for text search and WAL mode for practical local concurrency.

### Profiles

A profile represents a memory boundary. The store creates a `default` profile automatically. Future Hermes integration will map active Hermes profiles into this table.

### Peers

Peers represent humans, assistants, groups, and systems. The current schema supports:

- `human`
- `ai`
- `group`
- `system`

### Aliases

Aliases map external identifiers or friendly names onto canonical peer IDs.

Example:

```text
telegram:151011988 -> telegram-151011988
user               -> telegram-151011988
ai                 -> Ambrogio
```

Aliases include source, confidence, and verification flags.

### Sessions

Sessions represent conversation lanes. A Telegram DM, CLI conversation, or group chat can each have its own session. Session titles are metadata rather than primary identity.

### Raw messages

`sync_turn()` stores user and assistant messages as raw history. Raw history is intended to be the durable ground truth for future consolidation and migration verification.

### Durable facts

`memory_conclude` writes durable facts. Facts include:

- subject peer
- observer peer
- kind
- status
- source
- confidence
- evidence message IDs

### Peer cards

`memory_profile` reads or replaces a compact peer card. Cards are optimized for cheap context injection and quick inspection.

### Deterministic search

`memory_search` searches active facts through SQLite FTS5.

### Inspectable context injection

`prefetch()` builds an injected context block. `memory_context` returns the exact same block for inspection.

### GitHub CI

The repository has GitHub Actions CI running tests and Ruff linting on Python 3.10, 3.11, and 3.12.

## Current provider API

```python
from hermes_local_memory import LocalMemoryProvider

provider = LocalMemoryProvider()
provider.initialize(
    "session-1",
    hermes_home="/tmp/hermes-home",
    platform="telegram",
    user_id="151011988",
    agent_identity="Ambrogio",
)

provider.sync_turn("Remember X", "Got it")
context = provider.prefetch("X")
```

The provider exposes these tool schemas:

- `memory_profile`
- `memory_search`
- `memory_context`
- `memory_conclude`

## Planned features

### Hermes plugin shim

Local Memory can generate a tiny Hermes user-plugin shim:

```text
$HERMES_HOME/plugins/local_memory/__init__.py
```

Install it from a checkout:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
```

The shim calls Hermes' `register_memory_provider` hook and instantiates `LocalMemoryProvider`.

Safe validation path without switching the live provider:

```bash
# Confirm the shim can be discovered and loaded by Hermes' plugin loader.
PYTHONPATH="/path/to/hermes-agent:/path/to/hermes-local-memory/src" python - <<'PY'
from plugins.memory import discover_memory_providers, load_memory_provider
assert any(p[0] == 'local_memory' and p[2] for p in discover_memory_providers())
provider = load_memory_provider('local_memory')
assert provider is not None
print(provider.name)
PY
```

This does not change `memory.provider` and therefore does not replace the active memory backend.

### Honcho importer

The importer should preserve raw history and migrate useful derived artifacts:

- peers
- aliases
- sessions
- messages
- peer cards
- documents/conclusions as facts or candidates

It should support dry-run mode before any writes.

### Consolidation

Consolidation should be explicit and inspectable:

1. collect candidate facts
2. deduplicate or merge them
3. propose card/fact changes as a diff
4. apply only when approved or configured

### Fact replacement/retraction

`memory_conclude` should grow beyond add-only behavior:

- add
- replace
- retract
- supersede

### Summaries

Session/profile/topic summaries should reduce the need to search raw messages for every turn.

### Optional embeddings

Embeddings should be an optional retrieval layer, not a core dependency. The deterministic FTS/fact/card path should remain functional without them.

### Inspection CLI

A CLI should make it easy to inspect and repair local memory:

```bash
local-memory peers
local-memory aliases
local-memory search "migration history"
local-memory context --peer user --query "migration"
```

## Feature boundaries

Local Memory deliberately does not currently include:

- required background workers
- required cloud APIs
- autonomous hidden dream loops
- hidden backend dialectic answers
- destructive migration paths

These boundaries are intentional. The project can add sophisticated features later only if they remain local, inspectable, and testable.
