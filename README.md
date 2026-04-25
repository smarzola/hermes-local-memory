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

## Planned surfaces

The Hermes provider will expose tools equivalent to:

- `memory_profile` — read/write compact peer cards.
- `memory_search` — search facts, summaries, and raw messages.
- `memory_context` — show exactly what would be injected.
- `memory_conclude` — add/replace/retract durable facts.
- `memory_consolidate` — optional preview/apply consolidation jobs.

## Development

```bash
git clone https://github.com/smarzola/hermes-local-memory.git
cd hermes-local-memory
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Repository layout

```text
src/hermes_local_memory/
  __init__.py       Public package exports
  store.py          SQLite store and deterministic retrieval core
  schema.py         Schema migrations
  types.py          TypedDict/public data shapes

tests/
  test_store.py     Store behavior tests
```

## License

MIT
