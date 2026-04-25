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

### Plan a Honcho import

```bash
hermes-local-memory --db memory.sqlite import honcho \
  --source-db honcho-export.sqlite \
  --workspace hermes \
  --dry-run \
  --json
```

The current Honcho importer is dry-run only. It reads a SQLite export or fixture containing Honcho-shaped tables and returns a plan with:

- proposed peers
- proposed `honcho:<peer>` aliases
- proposed sessions and session peer links
- raw messages with `source_message_id=honcho:<id>`
- peer cards from `peers.internal_metadata`
- Honcho documents as `candidate` facts
- counts and warnings

It does not create or modify the target Local Memory database. `--dry-run` is currently required.

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
