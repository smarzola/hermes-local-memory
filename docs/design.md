# Hermes Local Memory Design

Hermes Local Memory is a local-first memory provider for Hermes Agent. It keeps the useful ideas from systems like Honcho — profiles, peers, sessions, cards, searchable memory, and consolidation — while rejecting the operational complexity of a separate memory server.

The core design target is simple:

> If memory is injected into an agent prompt, a human or another agent should be able to inspect where it came from, why it was selected, and how to edit or delete it.

## Motivation

Honcho demonstrated that agent memory is more useful when it is not just a flat list of notes. The important primitives are:

- **Peers** — humans, assistants, groups, and systems are all entities with identity.
- **Observer/subject perspective** — what an assistant knows about a human is distinct from what a human knows about themself.
- **Raw history plus derived memory** — chat logs should be preserved, while facts/cards/summaries are rebuildable derived layers.
- **Context injection and tools** — memory should be available both automatically and via explicit agent tools.
- **Consolidation** — long-running memory needs deduplication and summarization.

The problem is that a server-style implementation creates avoidable brittleness for a local personal agent:

- Separate API service, database, queue, worker, and model stack.
- Background processing failures that are not obvious to the agent.
- Derived representations that can drift from raw messages.
- Identity bugs where session separation exists but peer separation does not.
- Operational work to debug queues, workers, model compatibility, and migrations.

Local Memory is designed as a plugin-native alternative: one SQLite database, deterministic retrieval first, and explicit consolidation later.

## Design principles

### 1. Local-first by default

The core memory store is a SQLite database under the active Hermes home, normally:

```text
$HERMES_HOME/memory/local_memory.sqlite
```

There is no required API server, Docker stack, Redis queue, Postgres database, or cloud service.

### 2. Preserve raw history

Raw messages are the ground truth. Migrations must import or copy raw history, not rewrite it destructively or treat it as expendable legacy data.

Derived layers such as facts, cards, summaries, and embeddings can be rebuilt. Raw history should not be silently discarded.

### 3. Identity mapping is explicit data

Local Memory separates:

- Hermes profile/workspace
- peer identity
- platform account alias
- conversation session

A Telegram account, a human-readable name, and an imported Honcho peer name can all point to the same canonical peer through `peer_aliases`.

Example:

```text
telegram:1001 -> alice
honcho:Alice      -> alice
user               -> alice
```

This avoids hard-coded config values accidentally collapsing multiple humans into one peer.

### 4. Deterministic retrieval before LLM synthesis

The first retrieval path is deliberately boring:

- peer card
- active facts
- source labels
- evidence message IDs
- FTS search
- session ID context

LLM reasoning and consolidation are planned as explicit, inspectable layers on top of this, not hidden backend behavior.

### 5. Inspectable context injection

The `memory_context` tool returns the same text that `prefetch()` would inject. This makes prompt memory auditable and debuggable.

### 6. Plugin-native, not server-shaped

The package exposes a Hermes-compatible provider lifecycle without importing Hermes directly. A thin shim can register it as a Hermes memory provider. This keeps the core package independently testable and easier for other agents to work on.

## Current architecture

```text
src/hermes_local_memory/
  provider.py       Hermes-compatible provider lifecycle and tools
  store.py          SQLite store and deterministic retrieval core
  schema.py         SQLite schema
  honcho_import.py  Read-only Honcho import planner
  cli.py            Inspection, repair, and import-planning CLI
  __init__.py       Public exports
```

The current provider is intentionally standalone. It mirrors the important methods from Hermes' `MemoryProvider` interface:

- `initialize()`
- `is_available()`
- `system_prompt_block()`
- `get_tool_schemas()`
- `handle_tool_call()`
- `sync_turn()`
- `prefetch()`

A Hermes installation shim can import this class and register it with Hermes' plugin collector.

## Data model

### `profiles`

A profile is a Hermes memory boundary. The default profile is created automatically.

```sql
profiles(id, display_name, created_at)
```

Future Hermes profile integration should map the active Hermes profile to `profiles.id`.

### `peers`

Peers are humans, assistants, groups, or systems.

```sql
peers(id, display_name, kind, created_at, metadata_json)
```

Current peer kinds:

- `human`
- `ai`
- `group`
- `system`

### `peer_aliases`

Aliases map external or friendly identifiers onto canonical peers.

```sql
peer_aliases(alias, peer_id, source, confidence, verified, created_at)
```

This is the core mechanism for stable multi-person support.

### `sessions`

Sessions represent conversation lanes.

```sql
sessions(id, profile_id, platform, external_id, title, scope, timestamps, metadata_json)
```

The session title is metadata, not identity. Stable platform/session keys should remain stable even if a chat is renamed.

### `session_peers`

Join table between sessions and peers.

```sql
session_peers(session_id, peer_id, role, joined_at, left_at)
```

### `messages`

Raw conversation history.

```sql
messages(id, session_id, peer_id, role, content, created_at, source_message_id, metadata_json)
```

Messages are indexed with SQLite FTS5.

### `facts`

Durable memory statements.

```sql
facts(id, subject_peer_id, observer_peer_id, scope, scope_id, kind, content, confidence, status, source, evidence_json, timestamps)
```

Facts are currently the main searchable memory unit. They can link to evidence message IDs.

Current statuses:

- `active`
- `candidate`
- `superseded`
- `retracted`

### `cards`

Compact peer cards for fast injection.

```sql
cards(subject_peer_id, observer_peer_id, scope, scope_id, content_json, updated_at)
```

Cards are stored for speed and clarity, but should be rebuildable from facts and summaries.

### `summaries`

Planned summary layer for session/profile/topic summarization.

```sql
summaries(id, scope, scope_id, content, covered_from_message_id, covered_to_message_id, model, timestamps)
```

## Current provider tools

### `memory_profile`

Read or replace a compact peer card.

Use cases:

- Get a quick profile snapshot.
- Write a curated card after migration or consolidation.
- Keep high-value identity/preferences cheap to inject.

### `memory_search`

Search active durable facts for the current or specified peer.

Current implementation uses FTS5 over facts. Future retrieval can blend facts, summaries, messages, and optional embeddings.

### `memory_context`

Return exactly the source-labeled context block that automatic injection would use.

This is a key debugging and trust feature.

### `memory_conclude`

Add a durable fact about a peer.

Current behavior:

- defaults to the current user peer
- stores facts with `source=manual`
- links evidence to the latest synced user message when available

Future behavior should add replace/retract actions and candidate fact workflows.

## Context injection

`prefetch(query)` currently returns a deterministic Markdown block like:

```markdown
# Local Memory

Subject peer: `telegram-1001`
Observer peer: `Bob`
Session: `session-1`

## Peer card
- Name: Alice

## Durable facts
- Alice wants memory migrations to preserve history. (kind=preference, source=manual, evidence=[1])
```

The same block is available through `memory_context`.

Trivial prompts such as `ok`, `yes`, and `thanks` do not inject memory.

## Design choices versus Honcho

### No background server

Honcho uses an API server and worker pipeline. Local Memory starts as an in-process provider. This removes an entire class of operational failures.

### No hidden dialectic as the default retrieval path

Honcho can synthesize answers through a backend dialectic agent. Local Memory's default is deterministic retrieval. Hermes itself can reason over returned context.

This makes the reasoning step visible in the main agent trace rather than hidden inside a memory backend.

### No autonomous dream worker as the first consolidation path

Honcho's dreamer is powerful but opaque. Local Memory will add consolidation as explicit preview/apply jobs:

```text
collect candidates -> show diff -> apply facts/card updates
```

The goal is to make consolidation auditable and reversible.

### Peer aliases instead of fixed peer config

A fixed `peerName` can accidentally collapse multiple humans into the same peer. Local Memory treats aliases as first-class rows, so platform IDs and friendly names can be mapped deliberately and migrated safely.

### Cards are views, not sacred truth

Cards are useful compact artifacts, but raw messages and evidence-backed facts are the durable base. Cards should be easy to rebuild.

## Migration philosophy

Migration from Honcho or any other memory system should be additive:

1. Import raw peers/sessions/messages.
2. Preserve original IDs in metadata.
3. Import aliases for old names and platform IDs.
4. Import cards as cards and/or candidate facts.
5. Import derived documents as candidate or active facts depending on confidence.
6. Verify with search/context before switching providers.

No migration should require pretending old history is disposable.

## Roadmap

### Milestone 1: Local store and provider wrapper

Done:

- SQLite schema
- raw messages
- peers, aliases, sessions
- facts and cards
- deterministic context
- Hermes-compatible provider wrapper
- tests and CI

### Milestone 2: Hermes install shim

Done:

- generate/install `$HERMES_HOME/plugins/local_memory/__init__.py`
- register `LocalMemoryProvider` with Hermes' memory plugin loader
- document `memory.provider: local_memory`

Still to verify manually in a live Hermes runtime after installation.

### Milestone 3: Inspection CLI

Done for read-only inspection:

- print peers/aliases/sessions/cards/messages/facts
- show injected context
- search facts
- inspect card items, raw messages, and evidence IDs in JSON output

Repair commands are now explicit and auditable for alias mapping, fact add/retract, and full card replacement. They intentionally do not perform hidden rewrites of raw messages or derived facts.

### Milestone 4: Honcho importer

Partially done:

- preferred dry-run/apply path through Honcho's HTTP API
- fallback dry-run planner from Honcho-shaped SQLite exports/fixtures
- proposed peer/session/message/card/fact counts
- `honcho:<peer>` alias planning
- raw-message preservation plan with source IDs and metadata
- idempotent API apply mode with automatic backup for existing target DBs
- peer-card planning from the peer-card API or SQLite `peers.internal_metadata`
- Honcho conclusions/documents planned as `candidate` facts

Still planned:

- optional advanced forensic DB import/export paths if API export misses data
- identity map file support
- richer collision detection and warnings

### Milestone 5: Consolidation

Planned:

- candidate fact extraction
- card rebuilds
- dry-run diffs
- explicit apply/retract flows

### Milestone 6: Optional embeddings

Planned as an optional extra, not a required core dependency.

## Testing philosophy

The project is built test-first. New behavior should have a failing test before implementation. Tests should favor real SQLite stores and real provider behavior over mocks.

Run:

```bash
PYTHONPATH=src pytest -q
ruff check .
```
