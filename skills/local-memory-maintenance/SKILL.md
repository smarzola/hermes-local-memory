---
name: local-memory-maintenance
description: Policy-driven Hermes Local Memory maintenance runbook for scheduled or manual peer review, reflection, consolidation, card review, verification, and one-time migration review.
version: 2.0.0
author: Hermes Local Memory contributors
license: MIT
metadata:
  hermes:
    tags: [hermes, memory, local-memory, maintenance, sqlite, cron, runbook]
---

# Local Memory Maintenance Runbook

Use this skill when a Hermes Agent session is asked to maintain a Hermes Local Memory database. The skill is a **policy-driven runbook**: the prompt chooses the recipe, phases, apply policy, reporting policy, database, and runtime identity; this skill supplies the safe execution mechanics.

Prefer loading this as the plugin-bundled skill `local_memory:maintenance` so the runbook follows the installed Local Memory package version. The copied `local-memory-maintenance` skill remains a compatibility path for older Hermes installations.

## Operating model

Local Memory owns storage, packet building, validation, deterministic consolidation, and auditable apply tools. Hermes Agent owns scheduling, model judgment, and user policy. Do not turn maintenance into a hidden dreamer or raw SQLite rewrite.

A good cron prompt is short and policy-shaped:

```text
Load and follow `local_memory:maintenance`.

Recipe: quiet-deterministic | reflection-weekly | full-audit | report-only | custom
Phases: backup, peer-review, reflection, deterministic, candidate-review, card-review, verification
Apply policy: report-only | safe-deterministic | bounded-agent-review
Reporting: always | on-change | on-error | silent/local-only
Database: ~/.hermes/memory/local_memory.sqlite
Runtime identity: use the current Hermes memory context, or initialize LocalMemoryProvider with realistic platform/user/agent identity.
```

If the user provides a custom prompt, map it to these knobs and follow that policy. Do not force the default full-audit recipe on users who asked for quiet, split-schedule, report-only, or phase-specific maintenance.

## Policy knobs

### Recipes

- `quiet-deterministic`: backup if applying, run deterministic maintenance dry-run/apply if safe, verify. No semantic agent review. Report only on error/action required unless the prompt asks otherwise.
- `reflection-weekly`: backup if applying, build reflection packets, produce evidence-linked reflection patches, validate/apply according to policy, verify. Good for weekly or lower-frequency jobs.
- `full-audit`: backup, peer review, reflection, deterministic maintenance, optional candidate/card review, verification, concise audit report. Good for initial adoption and operator-facing runs.
- `report-only`: run selected phases with all apply flags false. Produce recommendations but no mutations beyond non-memory inspection.
- `migration-once`: one-time Honcho migration review only when explicitly requested or a fresh import batch needs adoption.
- `custom`: run only the phases specified by the prompt.

### Apply policy

- `report-only`: never apply provider mutations. Validate proposed patches with `apply=false` when useful.
- `safe-deterministic`: apply only deterministic, bounded changes from provider dry-runs: duplicate supersedes, safe local/reflection candidate promotions, and deterministic empty-card bootstraps. No agent-generated semantic patches are applied.
- `bounded-agent-review`: agent may produce peer/reflection/candidate/card patches, but must validate with `apply=false` first and apply only narrow, evidence-backed changes within the prompt's phase and reporting policy.

Never bulk-promote imported Honcho candidates through deterministic maintenance. Imported Honcho memories are migration material, not routine nightly promotion material.

### Reporting policy

- `always`: deliver a concise user-facing report.
- `on-change`: report only if changes were applied, important packets were reviewed, or human action is needed.
- `on-error`: report only blocked/error/action-required outcomes.
- `silent` or `local-only`: do not send a user-facing success report. If the platform requires a final response, keep it minimal. Still preserve auditability through tool outputs, backups, and local logs when available.

Respect the requested reporting policy. Do not send nightly migration/bulk-promotion noise after first migration has completed unless there is a new actionable issue.

## Invariants

- Preserve raw messages. Never edit or delete raw history during maintenance.
- Make or verify a recent SQLite backup before any apply step.
- Prefer provider tools over direct SQLite edits. CLI/Python wrappers are acceptable for backups, release checks, or reaching `LocalMemoryProvider.handle_tool_call(...)` when live provider tools are unavailable.
- Validate every agent-produced patch with the corresponding `memory_apply_*_patch(apply=false)` before applying.
- Treat large, noisy, ambiguous, identity-confused, or imported-candidate-heavy plans as skipped/action-required, not as work to force through.
- New memories derived from reflection should be candidate facts with evidence message IDs, not immediately active facts.
- Compact cards are synthesized views. Do not append every active fact into cards. Use full-card replacement only through explicit card review or `memory_set_card` when the prompt requested it.
- Never pass an empty card to `memory_set_card` unless intentionally clearing with `allow_empty=true`.

## Provider tools

Read/write and retrieval:

- `memory_get_card`
- `memory_set_card`
- `memory_search`
- `memory_context`
- `memory_conclude`

Deterministic maintenance:

- `memory_consolidate` — one subject/observer pair
- `memory_maintenance` — all subject/observer pairs

Packet/review/apply workflows:

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

Use canonical names above. Legacy aliases may exist but should not appear in new prompts, docs, or reports.

## Phase runbooks

Run only the phases selected by the prompt/recipe.

### Phase: backup

Required before any apply step.

- Create a timestamped copy of the SQLite DB.
- Report or record the backup path according to reporting policy.
- If the job is report-only and no mutation can occur, backup may be skipped unless requested.

### Phase: peer-review

Purpose: repair identity/alias issues before downstream reflection and retrieval.

1. Call `memory_build_peer_review_packet`.
2. If an alias move is obvious and evidence-supported, produce a peer review patch with `alias_moves`.
3. If a runtime/ephemeral peer is clearly the same identity as a canonical peer, produce a patch with `peer_merges`, `from_peer_id`, `to_peer_id`, `keep_source_alias=true`, `verified=true`, and a short reason.
4. Validate with `memory_apply_peer_review_patch(apply=false)`.
5. Apply only under `bounded-agent-review` or an explicit compatible policy.
6. Escalate ambiguous identities with concrete peer IDs/aliases.

Do not move aliases merely to mark imported Honcho aliases verified when they already resolve to the intended canonical peer.

### Phase: reflection

Purpose: turn stale raw-message windows into candidate facts and session summaries.

1. Call `memory_build_reflection_packets` with prompt-selected thresholds or defaults (`min_messages=20`, `max_messages=100`).
2. For each packet, derive only facts and summaries clearly supported by message IDs in the packet.
3. Prefer summary-only patches for historical/imported/task-local windows that are useful to checkpoint but not worth new durable facts.
4. Validate with `memory_apply_reflection_patch(apply=false)`.
5. Apply only if policy allows and validation passes.
6. Re-run packet build if needed to confirm the intended backlog was cleared.

Reflection facts should be candidates first. Do not create active facts directly from reflection.

### Phase: deterministic

Purpose: conservative all-pairs fact lifecycle maintenance.

1. Call `memory_maintenance(promote_candidates=true, apply=false)`.
2. Inspect counts and changed-pair summaries.
3. Apply only if the plan is bounded and compatible with the apply policy:
   - duplicate candidate supersedes;
   - high-confidence local or `agent-reflection` candidate promotions;
   - deterministic empty-card bootstrap from safe active facts.
4. If safe, call `memory_maintenance(promote_candidates=true, apply=true)`.
5. Skip/action-required if the plan is large, ambiguous, identity-confused, or mostly imported Honcho candidates.

### Phase: migration-once

Purpose: first adoption of imported Honcho memory, not routine maintenance.

Run only when the prompt explicitly asks for migration review or a fresh Honcho import batch is being adopted. If first migration already ran and no new import batch exists, omit this phase and do not mention skipped bulk promotion in routine reports.

1. For relevant peers, call `memory_build_honcho_migration_review_packet`.
2. Promote only stable, high-signal imported memories that are not already active/carded.
3. Leave or retract noisy imported artifacts: raw numeric peer IDs, support/task-local notes, tool/system artifacts, duplicated prompt instructions, or one-off logistics unless explicitly requested.
4. Rebuild compact cards from selected imports plus existing active facts only when policy allows.
5. Validate with `memory_apply_honcho_migration_review_patch(apply=false)`.
6. Apply only under explicit migration policy.

### Phase: candidate-review

Purpose: narrow review of important remaining candidates.

1. Call `memory_build_candidate_review_packet` for a selected peer and optional source filter.
2. Promote, supersede, retract, or add compact card lines only when narrow and evidence-backed.
3. Validate with `memory_apply_candidate_review_patch(apply=false)`.
4. Apply only if policy allows.

This phase is not a license for broad imported-candidate promotion.

### Phase: card-review

Purpose: synthesize compact cards when they are sparse, stale, duplicate-heavy, too verbose, or polluted by task-local lines.

1. Call `memory_build_card_review_packet` for affected peers.
2. Produce a complete replacement card, not an append-only diff.
3. Keep cards compact, human-readable, and consistent with active facts plus selected high-signal candidates.
4. Validate with `memory_apply_card_review_patch(apply=false)`.
5. Apply only if policy allows and the replacement preserves important active facts.

### Phase: verification

Use enough verification for the selected recipe and reporting mode:

- `memory_get_card` for affected peers;
- `memory_context` to inspect actual prompt injection;
- `memory_search` for key facts expected to be retrievable;
- final `memory_maintenance(promote_candidates=true, apply=false)` to confirm no unexpected residual deterministic changes.

For quiet/silent jobs, verification failures or unexpected residual changes should become `action_required` and override silence.

## Report shape

Reports should be concise and policy-aware. Include only relevant sections for selected phases and reporting mode.

Useful audit fields:

- recipe/phases and apply/reporting policy;
- backup path, when created;
- peer aliases moved or unresolved identity prompts;
- reflection packets reviewed, candidate facts added, session summaries added;
- deterministic maintenance counts and changes applied;
- migration review changes only when migration was actually run or actionable;
- candidate review/card review changes applied;
- skipped/action-required items and why;
- verification results for cards, context injection, search, and final deterministic dry-run.

If reporting is `silent` or `on-error` and the run is clean, do not produce a verbose success report.

## Example prompts

### Quiet deterministic daily

```text
Load and follow `local_memory:maintenance`.
Recipe: quiet-deterministic.
Apply policy: safe-deterministic.
Reporting: on-error.
Database: ~/.hermes/memory/local_memory.sqlite.
```

### Weekly reflection

```text
Load and follow `local_memory:maintenance`.
Recipe: reflection-weekly.
Apply policy: bounded-agent-review for reflection summaries and candidate facts only.
Reporting: on-change.
```

### Full operator audit

```text
Load and follow `local_memory:maintenance`.
Recipe: full-audit.
Apply policy: bounded-agent-review.
Reporting: always.
Skip Honcho migration unless explicitly requested or a fresh import batch is pending.
```

### Report-only dry run

```text
Load and follow `local_memory:maintenance`.
Recipe: report-only.
Phases: peer-review, reflection, deterministic, candidate-review, card-review, verification.
Apply policy: report-only.
Reporting: always.
```

## Compatibility notes

- Preferred skill name when loaded from the plugin shim: `local_memory:maintenance`.
- Compatibility copied skill name: `local-memory-maintenance`.
- If live Hermes does not expose the provider tools for the target DB/identity, instantiate `LocalMemoryProvider` from the installed package and call `handle_tool_call(...)` with canonical tool names rather than editing SQLite directly.
