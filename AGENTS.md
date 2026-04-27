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

conservative consolidation / maintenance
  candidate facts + active facts + cards -> safe fact lifecycle changes
  card synthesis/cleanup happens through card review or validated card_replace patches

prompt injection
  identity + compact card + durable facts + session summaries/retrieval
```

Reflection should run before consolidation in scheduled maintenance. Candidate facts should generally not be injected into ordinary prompts unless the task is memory review. Do not bulk-promote imported Honcho candidates through deterministic maintenance, but do review high-signal Honcho memories during first migration with the Honcho migration review tools and use selected imports to rebuild cards. Do not append all active facts into cards; cards are compact synthesized views.

## Current package layout

- `src/hermes_local_memory/schema.py` — SQLite schema.
- `src/hermes_local_memory/store.py` — store API and deterministic retrieval.
- `src/hermes_local_memory/reflection.py` — reflection packet/patch workflow.
- `src/hermes_local_memory/consolidation.py` — consolidation packet/patch/all-pairs maintenance workflow.
- `src/hermes_local_memory/provider.py` — Hermes-compatible provider wrapper.
- `src/hermes_local_memory/cli.py` — inspection, repair, import, reflection, and consolidation CLI.
- `tests/` — behavior tests.

## Setup and verification for agents

### Normal adoption path

For human or agent setup, prefer the published package:

```bash
uv tool install hermes-local-memory
# or
pipx install hermes-local-memory
hermes-local-memory --help
```

Install the Hermes shim without switching the active provider:

```bash
hermes-local-memory install-shim --hermes-home ~/.hermes
```

Use a trial DB before live migrations:

```bash
export LOCAL_MEMORY_DB=~/.hermes/memory/local_memory_trial.sqlite
hermes-local-memory --db "$LOCAL_MEMORY_DB" peers --json
```

### Development path

Only clone GitHub when editing this repository, testing unreleased changes, or debugging from source:

```bash
git status --short
PYTHONPATH=src pytest -q
ruff check .
PYTHONPATH=src python -m compileall -q src tests
```

If package metadata changed, also run:

```bash
uv build
```

From a checkout, run the shim installer as:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
```

Full setup/adoption instructions live in `docs/setup.md`. Release steps live in `docs/release.md`.

## Scheduled maintenance guidance

Do not add a scheduler to this package. The reusable agent workflow is packaged as the plugin-provided skill `local_memory:maintenance` when the shim is installed and enabled. Keep cron prompts short and policy-focused; load the plugin skill rather than copying the flow into the prompt. The copied `skills/local-memory-maintenance/SKILL.md` path remains a compatibility fallback. A recurring Hermes cron job should:

1. creates a timestamped SQLite backup before any apply step,
2. runs `memory_build_peer_review_packet` and resolves only deterministic aliases through `memory_apply_peer_review_patch`, otherwise emits human prompts,
3. runs `memory_build_reflection_packets` for stale sessions,
4. has Hermes review reflection packets and produce evidence-linked reflection patches,
5. validates/applies safe reflection patches with `memory_apply_reflection_patch`,
6. runs all-pairs `memory_maintenance(promote_candidates=true, apply=false)`,
7. applies only bounded fact-lifecycle changes such as duplicate supersedes or high-confidence local/reflection candidate promotions,
8. during first Honcho migration, uses `memory_build_honcho_migration_review_packet` plus `memory_apply_honcho_migration_review_patch` to promote selected high-signal Honcho memories and rebuild compact cards,
9. uses `memory_build_candidate_review_packet` for remaining noisy candidates and `memory_build_card_review_packet` plus `memory_apply_card_review_patch` for compact card synthesis/cleanup,
10. verifies with `memory_context`, `memory_search`, and `memory_get_card`,
11. reports peer prompts, reflected sessions, candidate facts, summaries, Honcho migration review changes, changed pairs, skipped pairs, and escalations.

Recommended starting cadence: nightly. High-volume deployments can move to every 6 hours once dry-run reports are clean.

## Near-term roadmap

1. Package/release hardening and smoke installs from built artifacts.
2. Higher-level Hermes cron templates or setup helpers.
3. Live Hermes runtime validation of the generated `local_memory` plugin shim.
4. Higher-level autonomous maintenance helpers that produce patches with less prompt scaffolding.
5. Optional embeddings.
