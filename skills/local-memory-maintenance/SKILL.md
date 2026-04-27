---
name: local-memory-maintenance
description: Product-oriented Hermes Local Memory maintenance runbook for daily autonomous upkeep, scheduled background care, targeted repair, audits, and one-time migration review.
version: 2.1.0
author: Hermes Local Memory contributors
license: MIT
metadata:
  hermes:
    tags: [hermes, memory, local-memory, maintenance, sqlite, cron, runbook]
---

# Local Memory Maintenance Runbook

Use this skill when Hermes Agent is asked to keep a Hermes Local Memory database healthy. The default product posture is **daily autonomous care**: do useful safe work in the background, stay quiet when healthy, and interrupt only for errors or genuinely human decisions.

Prefer loading this as the plugin-bundled skill `local_memory:maintenance` so the runbook follows the installed Local Memory package version. The copied `local-memory-maintenance` skill is legacy fallback only for older Hermes installations and should not coexist in normal installs.

## Product posture

Most users do not want to inspect maintenance. They want memory to keep working.

Default behavior, unless the prompt says otherwise:

```text
Recipe: daily-care
Autonomy: autopilot
Reporting: action-required
Database: current Local Memory provider/default DB
```

This means:

- run on a daily or more frequent schedule without user babysitting;
- apply bounded safe changes after dry-run validation;
- use Hermes Agent judgment for reflection and narrow repairs when evidence is clear;
- keep cards and facts useful without dumping every fact into prompts;
- send no verbose success report unless the user requested audit reporting;
- escalate only blocked, ambiguous, risky, or failed work.

The cron prompt should steer **policy**, not re-describe the maintenance algorithm:

```text
Load and follow `local_memory:maintenance`.
Recipe: daily-care.
Autonomy: autopilot.
Reporting: action-required.
Database: ~/.hermes/memory/local_memory.sqlite.
```

If the user gives a custom schedule or policy, follow it. This runbook is not Simone's personal audit ritual; it is a maintenance product surface with sane defaults and escape hatches.

## Recipes

### `daily-care` — default

For most users, daily or more frequent.

Runs:

1. backup when applying;
2. peer review for obvious identity repairs;
3. reflection for stale windows;
4. deterministic all-pairs maintenance;
5. targeted candidate/card cleanup only when a prior phase reveals a bounded, obvious need;
6. verification.

Applies safe work automatically under `autopilot`. Reports only action-required/error by default.

### `quiet-care`

Same as `daily-care`, but with stricter silence. Best for users who want background operation and local/auditable traces only.

Reports only if blocked, failed, or human input is required. If the platform requires a final response, keep it to a single line.

### `deep-care`

For weekly/monthly deeper housekeeping or after high-volume usage.

Runs daily-care plus broader candidate review and card review for peers with sparse, stale, verbose, or duplicate-heavy memory. Still validates before applying. Reports changes unless the prompt asks for silence.

### `audit`

For operators, debugging, release checks, and adoption validation.

Runs selected phases and produces an explicit report with backup path, changed counts, skipped/action-required items, and verification. Audit is a secondary mode, not the default product posture.

### `dry-run`

For cautious operators or new deployments.

No mutations except safe read-only inspection. Build packets/plans, validate candidate patches with `apply=false` when useful, and report what would happen.

### `migration-once`

For first adoption of imported Honcho memory or a fresh import batch.

This is never part of routine daily care unless explicitly requested or newly actionable. After first migration completes, do not keep reporting skipped imported-Honcho bulk promotion.

## Autonomy levels

### `autopilot` — default

Do the safe thing without asking:

- apply deterministic maintenance when dry-run counts are bounded and safe;
- apply clear peer alias/merge repairs when evidence is unambiguous;
- apply reflection patches when facts/summaries are directly supported by packet message IDs;
- apply narrow candidate/card repairs when they are compact, validated, and policy-compatible;
- skip and mark action-required when confidence is low.

### `conservative`

Apply deterministic maintenance only. Build semantic review packets, but do not apply agent-generated patches unless explicitly requested.

### `dry-run`

Never apply. Produce a report or local audit only.

## Reporting modes

### `action-required` — default

No user-facing success report. Report only when:

- a tool fails;
- a validation fails;
- a plan is too large/risky/ambiguous;
- identity is confused;
- human input is needed;
- verification finds unexpected residual work.

### `changes`

Report when changes were applied or action is required.

### `digest`

Send a compact scheduled digest even when healthy.

### `audit`

Send full operator-facing details.

### `silent`

Do not send messages unless the run cannot safely continue. Preserve auditability through backups, tool outputs, local files, or cron logs where available.

Respect reporting policy. Do not invent noisy reports just because a phase was skipped intentionally.

## Safety invariants

- Preserve raw messages. Never edit or delete raw history during maintenance.
- Make or verify a recent SQLite backup before applying mutations. If a deployment has its own backup policy, obey it; otherwise create a timestamped copy.
- Prefer provider tools over direct SQLite edits. CLI/Python wrappers are acceptable for backups, release checks, or reaching `LocalMemoryProvider.handle_tool_call(...)` when live provider tools are unavailable.
- Validate every agent-produced patch with the corresponding `memory_apply_*_patch(apply=false)` before applying.
- Skip/action-required large, noisy, ambiguous, identity-confused, or imported-candidate-heavy plans.
- New memories derived from reflection should be candidate facts with evidence message IDs, not immediately active facts.
- Compact cards are synthesized views. Do not append every active fact into cards. Use full-card replacement only through explicit card review or `memory_set_card` when the prompt requested it.
- Never pass an empty card to `memory_set_card` unless intentionally clearing with `allow_empty=true`.
- Never bulk-promote imported Honcho candidates through deterministic maintenance.

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

## Phase behavior

Run the phases implied by the selected recipe/custom prompt.

### Backup

Before applying, create or verify a recent timestamped SQLite backup. Keep backup details in audit output. Under `action-required` or `silent`, do not send backup path unless reporting is triggered.

### Peer review

Purpose: keep identity resolution healthy.

1. Call `memory_build_peer_review_packet`.
2. Apply obvious alias moves or peer merges only when evidence is unambiguous.
3. Preserve retired peer IDs as aliases with `keep_source_alias=true` when merging runtime/ephemeral peers.
4. Validate with `memory_apply_peer_review_patch(apply=false)` before applying.
5. If uncertain, skip/action-required with concrete peer IDs and aliases.

Do not move imported Honcho aliases merely to mark them verified when they already resolve correctly.

### Reflection

Purpose: make recent conversations useful as candidate facts and summaries.

1. Call `memory_build_reflection_packets` with prompt-selected thresholds or defaults (`min_messages=20`, `max_messages=100`).
2. For each packet, create only evidence-linked candidate facts and/or session summaries.
3. Prefer summary-only patches for historical/imported/task-local windows.
4. Validate with `memory_apply_reflection_patch(apply=false)`.
5. Under `autopilot`, apply clear, narrow reflection patches; otherwise follow autonomy policy.
6. Re-run packet build only when needed to confirm backlog progress.

### Deterministic maintenance

Purpose: do routine safe work.

1. Call `memory_maintenance(promote_candidates=true, apply=false)`.
2. If counts are bounded and sources are safe, apply with `memory_maintenance(promote_candidates=true, apply=true)`.
3. Safe routine changes include duplicate supersedes, high-confidence local/`agent-reflection` promotions, and deterministic empty-card bootstrap from safe active facts.
4. Skip/action-required if the plan is large, ambiguous, identity-confused, or mostly imported Honcho candidates.

This phase is the backbone of daily-care.

### Candidate review

Purpose: handle important candidate facts that deterministic maintenance cannot safely decide.

Daily-care should run this only when a prior phase shows a small, obvious candidate set. Deep-care can inspect broader candidate packets.

1. Call `memory_build_candidate_review_packet` for selected peer/source.
2. Promote/supersede/retract only narrow, evidence-backed facts.
3. Validate with `memory_apply_candidate_review_patch(apply=false)`.
4. Apply under `autopilot` only when the patch is compact and low-risk.

### Card review

Purpose: keep prompt-facing cards compact and helpful.

Daily-care should not rewrite cards casually. It may fix obviously empty/sparse/polluted cards when bounded. Deep-care may do broader card synthesis.

1. Call `memory_build_card_review_packet` for affected peers.
2. Produce a complete replacement card, not an append-only diff.
3. Keep cards compact, human-readable, and consistent with active facts plus selected high-signal candidates.
4. Validate with `memory_apply_card_review_patch(apply=false)`.
5. Apply only if the replacement clearly preserves important active facts.

### Migration-once

Purpose: adopt imported Honcho memories once.

Run only when explicitly requested or a fresh import batch is being adopted. Imported Honcho memories are migration material, not daily-care material.

1. Call `memory_build_honcho_migration_review_packet` for relevant peers.
2. Promote stable, high-signal imported memories that are not already active/carded.
3. Leave or retract noisy imported artifacts: raw numeric peer IDs, support/task-local notes, tool/system artifacts, duplicated prompt instructions, or one-off logistics unless explicitly requested.
4. Rebuild compact cards only when policy allows.
5. Validate/apply with `memory_apply_honcho_migration_review_patch`.

After migration completes, omit this phase and omit skipped bulk-promotion noise from routine reports.

### Verification

For daily-care, verify cheaply and act on surprises:

- final `memory_maintenance(promote_candidates=true, apply=false)` for unexpected residual deterministic changes;
- `memory_get_card`, `memory_context`, or `memory_search` only for affected peers or when verification is requested/needed.

For audit/deep-care, include fuller verification details.

## Reporting behavior

Do not confuse auditability with messaging. A background maintenance product can be auditable without spamming the user.

When reporting is triggered, include relevant compact fields:

- recipe/autonomy/reporting mode;
- backup path if created;
- changes applied by phase;
- action-required items and why;
- validation or tool errors;
- verification surprises;
- migration review only when actually run or newly actionable.

For clean `daily-care` with `action-required`, return no verbose report. If the platform requires a final message, use a minimal success line.

## Example prompts

### Default daily care

```text
Load and follow `local_memory:maintenance`.
Recipe: daily-care.
Autonomy: autopilot.
Reporting: action-required.
Database: ~/.hermes/memory/local_memory.sqlite.
```

### More frequent quiet care

```text
Load and follow `local_memory:maintenance`.
Recipe: quiet-care.
Autonomy: autopilot.
Reporting: silent.
Run only routine safe maintenance and escalate failures.
```

### Weekly deep care

```text
Load and follow `local_memory:maintenance`.
Recipe: deep-care.
Autonomy: autopilot.
Reporting: changes.
```

### Operator audit

```text
Load and follow `local_memory:maintenance`.
Recipe: audit.
Autonomy: autopilot.
Reporting: audit.
Skip Honcho migration unless explicitly requested or a fresh import batch is pending.
```

### Dry run

```text
Load and follow `local_memory:maintenance`.
Recipe: dry-run.
Autonomy: dry-run.
Reporting: audit.
```

## Compatibility notes

- Preferred skill name when loaded from the plugin shim: `local_memory:maintenance`.
- Compatibility copied skill name: `local-memory-maintenance`.
- If live Hermes does not expose the provider tools for the target DB/identity, instantiate `LocalMemoryProvider` from the installed package and call `handle_tool_call(...)` with canonical tool names rather than editing SQLite directly.
