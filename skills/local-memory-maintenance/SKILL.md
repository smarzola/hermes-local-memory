---
name: local-memory-maintenance
description: Run Hermes Local Memory peer review, reflection, deterministic maintenance, candidate review, card review, and verification through provider tools.
version: 1.0.0
author: Hermes Local Memory contributors
license: MIT
metadata:
  hermes:
    tags: [hermes, memory, local-memory, maintenance, sqlite, cron]
---

# Local Memory Maintenance

Use this skill when maintaining a Hermes Local Memory SQLite database from inside Hermes Agent or an autonomous cron job.

This skill is intentionally provider-tool-first. Use CLI commands only for non-memory-tool tasks such as creating timestamped file backups, release checks, or deep offline inspection.

## Non-negotiable safety rules

- Never mutate raw messages during maintenance.
- Always make or verify a recent DB backup before applying maintenance changes.
- Prefer provider tools over direct SQLite edits for memory lifecycle changes.
- Treat large, noisy, ambiguous, or identity-confused plans as skipped/escalated, not as work to force through.
- Imported Honcho candidate facts must not be bulk-promoted automatically by deterministic maintenance. They are still valuable first-migration material; review high-signal Honcho memories explicitly and use selected ones to rebuild cards.
- New facts derived from reflection should be candidates first, with evidence message IDs.
- Cards are compact synthesized views. Do not dump every active fact into an existing card.
- Empty-card bootstrap from high-confidence safe active facts is okay when deterministic maintenance proposes it.
- Use `memory_set_card` only for explicit full-card replacement, and never pass an empty card unless intentionally clearing with `allow_empty=true`.

## Canonical provider tools

Read / write cards:

- `memory_get_card`
- `memory_set_card`

Everyday facts and verification:

- `memory_conclude`
- `memory_search`
- `memory_context`

Deterministic consolidation:

- `memory_consolidate` — one subject/observer pair
- `memory_maintenance` — all subject/observer pairs

Packet/review/apply tools:

- `memory_build_peer_review_packet`
- `memory_apply_peer_review_patch`
- `memory_build_reflection_packets`
- `memory_apply_reflection_patch`
- `memory_build_candidate_review_packet`
- `memory_apply_candidate_review_patch`
- `memory_build_card_review_packet`
- `memory_apply_card_review_patch`
- `memory_build_honcho_migration_review_packet`
- `memory_apply_honcho_migration_review_patch`

Legacy names may exist as hidden compatibility aliases, but agents should prefer the canonical names above.

## Full maintenance cycle

1. **Backup**
   - Create a timestamped copy of the SQLite DB before applying changes.
   - If running in Hermes cron, a short Python `shutil.copy2` backup is acceptable.

2. **Peer review / identity**
   - Call `memory_build_peer_review_packet`.
   - If an alias move is obvious and evidence-supported, produce a peer review patch.
   - Validate first with `memory_apply_peer_review_patch(apply=false)`.
   - Apply only narrow alias moves with `memory_apply_peer_review_patch(apply=true)`.
   - Escalate ambiguous identities with concrete peer IDs and aliases.

3. **Reflection / distillation**
   - Call `memory_build_reflection_packets`.
   - For each packet, derive only facts and summaries clearly supported by packet message IDs.
   - Validate with `memory_apply_reflection_patch(apply=false)`.
   - Apply safe patches with `memory_apply_reflection_patch(apply=true)`.
   - New memories from reflection should be candidate facts, not active facts.

4. **Deterministic all-pairs maintenance**
   - Call `memory_maintenance(promote_candidates=true, apply=false)`.
   - Inspect changed-pair summaries.
   - Apply only when the plan is bounded and clearly safe:
     - duplicate candidate supersedes
     - high-confidence local/reflection candidate promotions
     - deterministic empty-card bootstrap from safe active facts
   - If safe, call `memory_maintenance(promote_candidates=true, apply=true)`.
   - Skip large or imported-candidate-heavy plans.

5. **First Honcho migration review**
   - If this is the first adoption/migration from Honcho, do not ignore Honcho candidate memories just because deterministic maintenance will not bulk-promote them.
   - For peers with imported Honcho candidates/cards, call `memory_build_honcho_migration_review_packet`.
   - Inspect the packet's current card, active facts, and candidate facts before drafting a patch. Some peers may already have the useful facts active/carded and only noisy Honcho candidates remaining.
   - Promote only high-signal stable Honcho facts. Prefer not to promote episodic support/chat artifacts, facts phrased around raw numeric peer IDs, tool/system-note artifacts, or one-off medical/logistics questions unless the user has asked to remember them.
   - For noisy imported candidates, either leave them as candidates if unsure or retract them when they are clearly not durable memory material. Supersede duplicates when they overlap with already active/carded facts.
   - Rebuild the compact card from selected imported memories plus existing active facts, keeping it concise and human-readable.
   - Validate with `memory_apply_honcho_migration_review_patch(apply=false)`.
   - Apply safe first-migration patches with `memory_apply_honcho_migration_review_patch(apply=true)`.

6. **Candidate review for noisy imports**
   - For pairs with remaining important candidates, call `memory_build_candidate_review_packet` with a peer and optional source filter.
   - Produce narrow candidate review patches.
   - Validate with `memory_apply_candidate_review_patch(apply=false)`.
   - Apply only selected promotions/supersedes/retractions/card additions.

7. **Card review / synthesis**
   - For sparse, stale, duplicate-heavy, or overly verbose cards, call `memory_build_card_review_packet`.
   - Produce a compact full-card replacement patch.
   - Validate with `memory_apply_card_review_patch(apply=false)`.
   - Apply only if the replacement is compact, evidence-grounded, and preserves important active facts.

8. **Verification**
   - Use `memory_get_card` for affected peers.
   - Use `memory_context` to inspect exactly what prompt injection will contain.
   - Use `memory_search` for key facts that should be retrievable.
   - Re-run `memory_maintenance(promote_candidates=true, apply=false)` and confirm no unexpected residual changes.

## Report format

Report these sections concisely:

- backup path
- peer aliases moved
- unresolved identity prompts
- reflection packets reviewed
- candidate facts added
- session summaries added
- deterministic maintenance changes applied
- Honcho migration review changes applied
- candidate review changes applied
- card review changes applied
- skipped/escalated items and why
- verification results for cards, context injection, and search

## Cron prompt skeleton

```text
Load the local-memory-maintenance skill and run a full Hermes Local Memory maintenance cycle.

Repository: /path/to/hermes-local-memory
Database: ~/.hermes/memory/local_memory.sqlite

Use provider tools first. Do not directly edit the SQLite DB except to create a timestamped backup copy before apply. Never mutate raw messages. Prefer dry-run/validate before apply for every patch. Apply only bounded, policy-safe changes; skip and report ambiguous, noisy, identity-confused, or large plans.

Run: backup -> memory_build_peer_review_packet -> memory_apply_peer_review_patch dry-run/apply for obvious alias moves -> memory_build_reflection_packets -> memory_apply_reflection_patch dry-run/apply for evidence-grounded reflection patches -> memory_maintenance dry-run/apply for bounded deterministic changes -> memory_build_honcho_migration_review_packet / memory_apply_honcho_migration_review_patch for first-migration Honcho memories when present -> memory_build_candidate_review_packet / memory_apply_candidate_review_patch for selected remaining candidates -> memory_build_card_review_packet / memory_apply_card_review_patch for card cleanup -> verify with memory_get_card, memory_context, memory_search, and a final dry-run memory_maintenance.

Deliver a concise report with applied, skipped, escalated, and verification sections.
```
