# Hermes Local Memory

Local-first SQLite memory for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

This project is an open-source, boring-engineering replacement for server-shaped agent memory stacks. It is inspired by the useful parts of Honcho — peers, profiles, cards, search, consolidation — but is designed to run locally as a Hermes memory plugin with no API server, no Docker, no Redis, and no Postgres.

> Status: pre-alpha. The first milestone is the local SQLite store and deterministic retrieval core. The Hermes plugin wrapper and Honcho importer come next.

## Goals

- **Local-only by default** — one SQLite database under the user's Hermes home.
- **Multi-profile and multi-peer** — separate Hermes profiles, humans, assistants, groups, and aliases.
- **Migration-safe** — preserve raw history; derived facts/cards can be rebuilt.
- **Inspectable** — every injected memory line should be traceable to stored facts or summaries.
- **Agent-friendly** — clear APIs, tests, docs, and contribution instructions so humans and coding agents can extend it.
- **Boring first** — deterministic FTS/search/context before optional embeddings or LLM consolidation.

## Non-goals

- No background server.
- No required cloud service.
- No hidden dialectic/dream worker as the core behavior.
- No destructive migration that treats old history as expendable.

## Documentation

- [Features](docs/features.md)
- [Design](docs/design.md)
- [Contributing](CONTRIBUTING.md)
- [Agent instructions](AGENTS.md)

## Current surfaces

The package now includes a Hermes-compatible `LocalMemoryProvider` with these tools:

- `memory_profile` — read/write compact peer cards.
- `memory_search` — search durable facts.
- `memory_context` — show exactly what would be injected.
- `memory_conclude` — add durable facts with evidence links to the most recent synced user turn.

The provider is intentionally independently testable and does not import Hermes. A thin Hermes plugin shim can wrap this class from `$HERMES_HOME/plugins/local_memory/` or upstream Hermes later.

Planned next surfaces:

- `memory_consolidate` — optional preview/apply consolidation jobs.
- Honcho importer — preserve raw history and migrate cards/documents into local facts/candidates.

## Development

```bash
git clone https://github.com/smarzola/hermes-local-memory.git
cd hermes-local-memory
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Install the Hermes plugin shim

From a checkout:

```bash
cd hermes-local-memory
PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
```

If installed as a package, use the console script:

```bash
hermes-local-memory install-shim --hermes-home ~/.hermes
```

Then configure Hermes:

```yaml
memory:
  provider: local_memory
```

Restart Hermes or start a fresh session after changing memory providers.

## Repository layout

```text
src/hermes_local_memory/
  __init__.py       Public package exports
  cli.py            Developer/install CLI
  hermes_plugin.py  Hermes user-plugin shim renderer
  provider.py       Hermes-compatible provider lifecycle and tools
  store.py          SQLite store and deterministic retrieval core
  schema.py         Schema migrations

tests/
  test_provider.py  Provider lifecycle/tool behavior tests
  test_store.py     Store behavior tests
```

## License

MIT
