# Agent Instructions

This repository is intended to be usable by both humans and autonomous coding agents.

## Project mission

Build a local-first Hermes Agent memory provider that is dramatically simpler than server-shaped systems while preserving the useful primitives: profiles, peers, aliases, raw history, facts, cards, summaries, deterministic retrieval, and migration-safe consolidation.

## Engineering principles

- Preserve raw history. Migrations must import or copy, not discard.
- Keep identity mapping explicit. Use aliases rather than hard-coded peer-name side effects.
- Prefer deterministic retrieval before adding LLM synthesis.
- Make context injection inspectable. If a memory line is injected, it should be traceable to a row.
- Keep the core local and boring: SQLite, stdlib, tests.
- Avoid background daemons unless a later milestone proves they are necessary.

## Development rules

- Use test-driven development for behavior changes.
- Run `PYTHONPATH=src pytest` before committing.
- Keep public APIs typed and documented enough for plugin users.
- Do not add required network services or heavyweight dependencies to the core package.
- Optional features such as embeddings should stay behind extras.

## Current package layout

- `src/hermes_local_memory/schema.py` — SQLite schema.
- `src/hermes_local_memory/store.py` — store API and deterministic retrieval.
- `tests/test_store.py` — behavior tests for the store.

## Near-term roadmap

1. Live Hermes runtime validation of the generated `local_memory` plugin shim.
2. CLI/dev utility for inspecting the SQLite database.
3. Honcho importer with dry-run/apply modes.
4. Consolidation previews and card rebuilds.
5. Optional embeddings.
