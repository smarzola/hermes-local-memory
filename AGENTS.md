# Agent Instructions

This repository is intended to be usable by both humans and autonomous coding agents.

## Project mission

Build a local-first Hermes Agent memory provider that is dramatically simpler than server-shaped systems while preserving the useful primitives: profiles, peers, aliases, raw history, facts, cards, summaries, deterministic retrieval, reflection/distillation, and migration-safe consolidation.

## Engineering principles

- Preserve raw history. Migrations must import or copy, not discard.
- Keep identity mapping explicit. Use aliases rather than hard-coded peer-name side effects.
- Prefer deterministic retrieval before adding LLM synthesis.
- Make context injection inspectable. If a memory line is injected, it should be traceable to a row.
- Keep the core local and boring: SQLite, stdlib, tests.
- Keep model calls and scheduling in Hermes Agent. Local Memory should build packets, validate patches, store rows, and render context.
- Avoid background daemons unless a later milestone proves they are necessary.

## Development rules

- Use test-driven development for behavior changes.
- Run `PYTHONPATH=src pytest -q` before committing.
- Run `ruff check .` before committing.
- Keep public APIs typed and documented enough for plugin users.
- Do not add required network services or heavyweight dependencies to the core package.
- Optional features such as embeddings should stay behind extras.

## Memory architecture quick model

```text
turn sync
  raw messages are appended every conversation turn

reflection / distillation
  stale raw-message windows -> Hermes Agent review -> candidate facts + session summaries

consolidation / maintenance
  candidate facts + active facts + cards -> promotions/supersedes/retractions/card updates

prompt injection
  identity + compact card + durable facts + session summaries/retrieval
```

Reflection should run before consolidation in scheduled maintenance. Candidate facts should generally not be injected into ordinary prompts unless the task is memory review.

## Current package layout

- `src/hermes_local_memory/schema.py` — SQLite schema.
- `src/hermes_local_memory/store.py` — store API and deterministic retrieval.
- `src/hermes_local_memory/reflection.py` — reflection packet/patch workflow.
- `src/hermes_local_memory/consolidation.py` — consolidation packet/patch/all-pairs maintenance workflow.
- `src/hermes_local_memory/provider.py` — Hermes-compatible provider wrapper.
- `src/hermes_local_memory/cli.py` — inspection, repair, import, reflection, and consolidation CLI.
- `tests/` — behavior tests.

## Setup and verification for agents

```bash
git status --short
PYTHONPATH=src pytest -q
ruff check .
```

Install the Hermes shim without switching the active provider:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
```

Use a trial DB before live migrations:

```bash
export LOCAL_MEMORY_DB=~/.hermes/memory/local_memory_trial.sqlite
PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" peers --json
```

## Scheduled maintenance guidance

Do not add a scheduler to this package. Instruct Hermes Agent to create a recurring Hermes cron job that:

1. runs `reflection-maintenance` for stale sessions,
2. has Hermes review reflection packets and produce reflection patches,
3. validates/applies safe reflection patches,
4. runs all-pairs `maintenance --dry-run`,
5. applies only narrow, validated consolidation changes,
6. reports reflected sessions, candidate facts, summaries, changed pairs, skipped pairs, and escalations.

Recommended starting cadence: nightly. High-volume deployments can move to every 6 hours once dry-run reports are clean.

## Near-term roadmap

1. Richer prompt context that includes session summaries in addition to cards/facts.
2. Safer candidate ranking/filtering for noisy imports.
3. Higher-level Hermes cron templates or setup helpers.
4. Live Hermes runtime validation of the generated `local_memory` plugin shim.
5. Optional embeddings.
