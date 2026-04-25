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
telegram:1001 -> telegram-1001
user               -> telegram-1001
ai                 -> Bob
```

Aliases include source, confidence, and verification flags. This makes peers a first-class agent-maintained layer: Hermes can review new platform identities, map obvious aliases to canonical peers, and escalate ambiguous identities for human help instead of silently fragmenting memory.

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

`prefetch()` builds an injected context block. `memory_context` returns the exact same block for inspection. Context Builder v2 renders explicit sections for identity/session metadata, aliases, compact peer card, active durable facts, latest session summary, and query-relevant active facts. Candidate facts and raw message windows are excluded from ordinary prompt injection.

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
    user_id="1001",
    agent_identity="Bob",
)

provider.sync_turn("Remember X", "Got it")
context = provider.prefetch("X")
```

The provider exposes these tool schemas:
- `memory_profile`
- `memory_search`
- `memory_context`
- `memory_conclude`
- `memory_consolidate`
- `memory_maintenance`
- `memory_peer_review`
- `memory_reflection_maintenance`

## Additional feature areas

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

The preferred importer path uses Honcho's HTTP API so it can work with local, remote, or hosted Honcho instances:

```bash
hermes-local-memory --db memory.sqlite import honcho-api \
  --base-url http://localhost:8000/v3 \
  --workspace hermes \
  --api-key "$HONCHO_API_KEY" \
  --dry-run \
  --json
```

Current API dry-run/apply support handles:

- peers
- `honcho:<peer>` aliases
- sessions
- session peer links
- raw messages
- peer cards from the peer-card API
- conclusions as `candidate` facts

Use `--dry-run` to preview and `--apply` to write. Apply mode is additive and idempotent; it does not mutate Honcho and does not switch the active Hermes provider. Existing target DBs are backed up automatically unless `--no-backup` is passed.

A secondary SQLite fixture importer remains available for tests and local forensic exports:

```bash
hermes-local-memory --db memory.sqlite import honcho \
  --source-db honcho-export.sqlite \
  --workspace hermes \
  --dry-run \
  --json
```

The SQLite fixture importer remains dry-run only. Identity map file support and richer collision detection remain planned.

### Reflection / distillation

Reflection is the dreaming-like process, but implemented as an explicit agent workflow instead of a hidden backend worker. It currently:

1. discovers stale sessions with unreflected raw messages
2. builds source-labeled reflection packets containing session metadata, participants, message windows, current cards, existing facts, and safety rules
3. lets Hermes Agent produce reflection patches
4. validates evidence message IDs against the packet window
5. writes new memories as `candidate` facts, not active facts
6. writes session summaries as reflection checkpoints

CLI examples:

```bash
hermes-local-memory --db memory.sqlite reflection-maintenance \
  --observer bob \
  --min-messages 20 \
  --max-messages 100 \
  --json

hermes-local-memory --db memory.sqlite apply-reflection-patch /tmp/reflection-patch.json \
  --dry-run \
  --json
```

Reflection should run before consolidation in scheduled maintenance.

### Candidate review

Candidate review is the safe adoption path for noisy imported memories. It builds a source-filterable packet for one subject/observer pair, lets Hermes Agent choose narrow actions, and validates a structured patch before changing fact status or compact card items.

Supported actions:

- promote candidate facts to `active`
- supersede duplicate candidates
- retract wrong/noisy candidates
- append compact card additions

This is preferable to blindly applying broad imported-candidate promotion.

### Card review

Card review is the migration cleanup path for imported compact cards. Imported cards can contain valuable profile lines while also carrying duplicate, stale, task-local, or overly verbose items. Card review makes that cleanup explicit:

1. build a `card-review-packet` for one subject/observer pair
2. let Hermes Agent draft a compact full-card replacement
3. validate the `card-review-patch`
4. apply only after dry-run or policy approval

Card review replaces only the derived card. It does not mutate facts, summaries, aliases, sessions, or raw messages.

### Peer review

Peer review gives Hermes Agent control of peer identity maintenance. It currently:

1. discovers unverified or platform-shaped peers such as `telegram-1001` or `honcho-abc`
2. builds a `peer-review-packet` with their aliases and candidate canonical peers
3. lets Hermes Agent decide whether to move aliases to existing canonical peers
4. lets Hermes Agent emit human prompts when the identity is ambiguous
5. validates and applies alias moves only with `apply-peer-review-patch --apply`

Peer review does not rewrite raw messages or delete peer rows. It changes the alias layer so future context, facts, and cards resolve to the right canonical person.

### Consolidation

Consolidation is explicit, deterministic, and inspectable. It currently:

1. reads the current peer card, active facts, and candidate facts for a subject/observer pair
2. supersedes candidate facts that duplicate an existing card line or active fact
3. optionally promotes unique candidate facts
4. proposes card additions from active facts and promoted candidates
5. can run for one pair or all subject/observer pairs with cards/facts
6. applies only with `--apply` or `memory_consolidate({"apply": true})`

CLI examples:

```bash
hermes-local-memory --db memory.sqlite consolidate \
  --peer alice \
  --observer bob \
  --promote-candidates \
  --dry-run \
  --json

hermes-local-memory --db memory.sqlite consolidate \
  --peer alice \
  --observer bob \
  --promote-candidates \
  --apply \
  --json

hermes-local-memory --db memory.sqlite maintenance \
  --promote-candidates \
  --dry-run \
  --json
```

Provider tool:

```json
{
  "peer": "user",
  "promote_candidates": true,
  "apply": false
}
```

The MVP does not call an LLM, delete raw history, or silently mutate memory during normal context injection. Hermes Agent owns the reasoning step for reflection and consolidation; Local Memory owns packet building, validation, storage, and auditable apply.

### Fact replacement/retraction

The CLI can now add and retract facts:

```bash
hermes-local-memory --db memory.sqlite fact add "..." --peer alice --observer bob
hermes-local-memory --db memory.sqlite fact retract fact_abc123
```

Provider tool support is still add-only; replace/supersede semantics remain planned.

- add: CLI done, provider done through `memory_conclude`
- retract: CLI done
- replace/supersede: planned

### Summaries

Session/profile/topic summaries should reduce the need to search raw messages for every turn.

### Optional embeddings

Embeddings should be an optional retrieval layer, not a core dependency. The deterministic FTS/fact/card path should remain functional without them.

### Inspection CLI

The CLI includes read-only inspection commands:

```bash
hermes-local-memory --db memory.sqlite peers
hermes-local-memory --db memory.sqlite aliases
hermes-local-memory --db memory.sqlite sessions
hermes-local-memory --db memory.sqlite cards --peer user
hermes-local-memory --db memory.sqlite messages --peer user
hermes-local-memory --db memory.sqlite facts --peer user
hermes-local-memory --db memory.sqlite search "migration history"
hermes-local-memory --db memory.sqlite context --peer user --observer ai --query "migration"
```

See [CLI](cli.md) for details.

## Feature boundaries

Local Memory deliberately does not currently include:

- required background workers
- required cloud APIs
- autonomous hidden dream loops
- hidden backend dialectic answers
- destructive migration paths

These boundaries are intentional. The project can add sophisticated features later only if they remain local, inspectable, and testable.
