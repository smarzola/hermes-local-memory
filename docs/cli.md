# CLI

`hermes-local-memory` provides developer and inspection commands for the local SQLite memory database.

## Safety model

The inspection and planning commands in this document are read-only:

- `peers`
- `aliases`
- `sessions`
- `cards`
- `messages`
- `facts`
- `search`
- `context`
- `import honcho-api --dry-run`
- `import honcho --dry-run`

They do not mutate the database. They are intended for humans and agents to verify identity mappings, durable facts, and context injection before enabling or migrating a live memory provider.

Current write commands are explicit repair/mutation commands:

- `install-shim`
- `alias add` / `alias move`
- `fact add` / `fact retract`
- `card replace`

`install-shim` writes a tiny Hermes plugin shim under `$HERMES_HOME/plugins/local_memory/__init__.py`. It does not change `config.yaml` and does not switch the active memory provider.

Repair commands are intentionally explicit: they name the object being changed and return the changed row, preferably as JSON for auditability. They do not perform automatic consolidation or hidden rewrites.

## Database selection

All inspection commands accept `--db` before the subcommand:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory.sqlite peers
```

Default:

```text
~/.hermes/memory/local_memory.sqlite
```

## Commands

### Install Hermes shim

```bash
hermes-local-memory install-shim --hermes-home ~/.hermes
```

From a checkout without installing the package:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
```

### List peers

```bash
hermes-local-memory --db memory.sqlite peers
hermes-local-memory --db memory.sqlite peers --json
```

Shows canonical peers such as humans, assistants, groups, and systems.

### List aliases

```bash
hermes-local-memory --db memory.sqlite aliases
hermes-local-memory --db memory.sqlite aliases --json
```

Shows alias mappings such as:

```text
telegram:151011988 -> simone
user -> simone
ai -> ambrogio
```

### List sessions

```bash
hermes-local-memory --db memory.sqlite sessions
hermes-local-memory --db memory.sqlite sessions --json
```

Shows conversation lanes and their metadata.

### List cards

```bash
hermes-local-memory --db memory.sqlite cards
hermes-local-memory --db memory.sqlite cards --peer simone
hermes-local-memory --db memory.sqlite cards --peer telegram:151011988 --observer ambrogio --json
```

Cards are compact profile snapshots used for cheap context injection.

### List messages

```bash
hermes-local-memory --db memory.sqlite messages
hermes-local-memory --db memory.sqlite messages --session telegram-dm-151011988
hermes-local-memory --db memory.sqlite messages --peer simone --json
```

Messages are raw history. This command is read-only and is intended for verification and evidence inspection.

### List facts

```bash
hermes-local-memory --db memory.sqlite facts
hermes-local-memory --db memory.sqlite facts --peer simone
hermes-local-memory --db memory.sqlite facts --peer telegram:151011988 --json
```

Options:

- `--peer` — peer id or alias for the fact subject
- `--observer` — peer id or alias for the observer
- `--status` — default `active`; pass an empty value in shell-specific ways if all statuses are needed later
- `--limit` — default `100`

### Search facts

```bash
hermes-local-memory --db memory.sqlite search "migration history"
hermes-local-memory --db memory.sqlite search "migration history" --peer simone --json
```

Search currently uses SQLite FTS5 over active durable facts.

### Render context

```bash
hermes-local-memory --db memory.sqlite context \
  --peer simone \
  --observer ambrogio \
  --query "migration history"
```

This renders the same source-labeled context shape used by provider `prefetch()`.

### Plan or apply a Honcho API import

Prefer the API importer when possible. It works with local, remote, or hosted Honcho instances and depends on Honcho's HTTP API rather than private database tables.

Dry-run first:

```bash
hermes-local-memory --db memory.sqlite import honcho-api \
  --base-url http://localhost:8000/v3 \
  --workspace hermes \
  --api-key "$HONCHO_API_KEY" \
  --dry-run \
  --json
```

Apply after reviewing the plan:

```bash
hermes-local-memory --db memory.sqlite import honcho-api \
  --base-url http://localhost:8000/v3 \
  --workspace hermes \
  --api-key "$HONCHO_API_KEY" \
  --apply \
  --json
```

The importer pages through public API endpoints and plans/imports:

- peers
- `honcho:<peer>` aliases
- sessions and session peer links
- raw messages with `source_message_id=honcho-api:<id>`
- peer cards from the peer-card API
- conclusions as `candidate` facts
- counts and warnings

Apply mode is additive and idempotent:

- peers, aliases, sessions, session peers, and cards are upserted
- messages are skipped when their `source_message_id` already exists
- facts are skipped when their planned fact ID already exists
- no Honcho data is mutated
- the active Hermes memory provider is not switched
- an existing target DB is backed up automatically unless `--no-backup` is passed

### Plan a Honcho SQLite fixture import

The SQLite importer is a fallback for tests, fixtures, and local forensic work where a Honcho-shaped SQLite export is available:

```bash
hermes-local-memory --db memory.sqlite import honcho \
  --source-db honcho-export.sqlite \
  --workspace hermes \
  --dry-run \
  --json
```

This path can read internal artifacts such as `peers.internal_metadata`, but it is not the preferred user migration path because it depends on Honcho's database shape.

## Repair commands

Repair commands mutate the DB and should be used deliberately. Prefer `--json` and commit/export the output in migration notes when doing larger repairs.

### Add or move aliases

```bash
hermes-local-memory --db memory.sqlite alias add telegram:7973745978 \
  --peer andra \
  --source telegram \
  --verified \
  --json

hermes-local-memory --db memory.sqlite alias move telegram:7973745978 \
  --peer simone \
  --json
```

`alias move` is intentionally just an explicit alias rewrite. It does not rewrite raw messages or facts.

### Add or retract facts

```bash
hermes-local-memory --db memory.sqlite fact add \
  "Simone prefers local-first tools." \
  --peer simone \
  --observer ambrogio \
  --kind preference \
  --json

hermes-local-memory --db memory.sqlite fact retract fact_abc123 --json
```

Retracting a fact marks it `retracted`; it does not delete the row.

### Replace cards

Cards are replaced as a full JSON list of strings:

```bash
cat > /tmp/simone-card.json <<'JSON'
[
  "Name: Simone",
  "Preference: explicit repair commands"
]
JSON

hermes-local-memory --db memory.sqlite card replace \
  --peer simone \
  --observer ambrogio \
  --from-file /tmp/simone-card.json \
  --json
```

Full replacement is intentional: it makes card repair auditable and avoids hidden merge behavior.

## Agent usage pattern

Before making a memory migration or identity repair, an agent should run:

```bash
hermes-local-memory --db memory.sqlite peers --json
hermes-local-memory --db memory.sqlite aliases --json
hermes-local-memory --db memory.sqlite cards --peer <peer> --json
hermes-local-memory --db memory.sqlite facts --peer <peer> --json
hermes-local-memory --db memory.sqlite messages --peer <peer> --json
hermes-local-memory --db memory.sqlite context --peer <peer> --observer <assistant> --query "current task"
```

This gives a quick view of whether the right person, aliases, facts, and injected context are lined up.
