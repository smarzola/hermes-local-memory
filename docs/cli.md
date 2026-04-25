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
- `candidate-review-packet`
- `card-review-packet`
- `peer-review-packet`

They do not mutate the database. They are intended for humans and agents to verify identity mappings, durable facts, and context injection before enabling or migrating a live memory provider.

Current write commands are explicit repair/mutation commands:

- `install-shim`
- `alias add` / `alias move`
- `fact add` / `fact retract`
- `card replace`
- `consolidate --apply`
- `apply-patch --apply`
- `apply-candidate-review-patch --apply`
- `apply-card-review-patch --apply`
- `apply-peer-review-patch --apply`
- `apply-reflection-patch --apply`

`install-shim` writes a tiny Hermes plugin shim under `$HERMES_HOME/plugins/local_memory/__init__.py`. It does not change `config.yaml` and does not switch the active memory provider.

Repair and consolidation commands are intentionally explicit: they name the object being changed and return the changed row or plan, preferably as JSON for auditability. They do not perform hidden rewrites. `consolidate --dry-run` is read-only; `consolidate --apply` is the mutating form.

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
telegram:1001 -> alice
user -> alice
ai -> bob
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
hermes-local-memory --db memory.sqlite cards --peer alice
hermes-local-memory --db memory.sqlite cards --peer telegram:1001 --observer bob --json
```

Cards are compact profile snapshots used for cheap context injection.

### List messages

```bash
hermes-local-memory --db memory.sqlite messages
hermes-local-memory --db memory.sqlite messages --session telegram-dm-1001
hermes-local-memory --db memory.sqlite messages --peer alice --json
```

Messages are raw history. This command is read-only and is intended for verification and evidence inspection.

### List facts

```bash
hermes-local-memory --db memory.sqlite facts
hermes-local-memory --db memory.sqlite facts --peer alice
hermes-local-memory --db memory.sqlite facts --peer telegram:1001 --json
```

Options:

- `--peer` — peer id or alias for the fact subject
- `--observer` — peer id or alias for the observer
- `--status` — default `active`; pass an empty value in shell-specific ways if all statuses are needed later
- `--limit` — default `100`

### Search facts

```bash
hermes-local-memory --db memory.sqlite search "migration history"
hermes-local-memory --db memory.sqlite search "migration history" --peer alice --json
```

Search currently uses SQLite FTS5 over active durable facts.

### Render context

```bash
hermes-local-memory --db memory.sqlite context \
  --peer alice \
  --observer bob \
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

### Build reflection packets from raw messages

Reflection/distillation is the dreaming-like step that happens **before** consolidation. It lets Hermes Agent review stale raw-message windows and propose candidate facts plus session summaries.

Build packets for all stale sessions for an observer:

```bash
hermes-local-memory --db memory.sqlite reflection-maintenance \
  --observer bob \
  --min-messages 20 \
  --max-messages 100 \
  --json
```

Build a packet for one session:

```bash
hermes-local-memory --db memory.sqlite reflection-packet \
  --session telegram-dm-1001 \
  --observer bob \
  --since-message-id 500 \
  --max-messages 100 \
  --json > /tmp/reflection-packet.json
```

Hermes Agent should use the packet to produce a patch like:

```json
{
  "schema": "hermes-local-memory.reflection-patch.v1",
  "session_id": "telegram-dm-1001",
  "observer_peer_id": "bob",
  "new_candidate_facts": [
    {
      "subject_peer_id": "alice",
      "kind": "preference",
      "content": "Alice prefers local-first memory systems.",
      "confidence": 0.91,
      "evidence_message_ids": [501, 508, 533]
    }
  ],
  "session_summary": {
    "content": "Alice and Bob discussed local-first memory and auditable maintenance.",
    "covered_from_message_id": 501,
    "covered_to_message_id": 533,
    "model": "hermes-agent"
  }
}
```

Validate without writing:

```bash
hermes-local-memory --db memory.sqlite apply-reflection-patch /tmp/reflection-patch.json \
  --dry-run \
  --json
```

Apply after validation or policy approval:

```bash
hermes-local-memory --db memory.sqlite apply-reflection-patch /tmp/reflection-patch.json \
  --apply \
  --json
```

Reflection patches are validated against the message window. New memories from reflection are written as `candidate` facts with evidence IDs; summaries are stored as session summaries. Raw messages are never rewritten.

### Review candidate facts safely

Candidate review is the safer path for noisy imports. Instead of broadly running `maintenance --promote-candidates --apply`, build a packet for one subject/observer pair, optionally filter by source, let Hermes Agent choose narrow actions, and validate/apply the patch.

Build a packet:

```bash
hermes-local-memory --db memory.sqlite candidate-review-packet \
  --peer alice \
  --observer bob \
  --source honcho-import \
  --limit 100 \
  --json > /tmp/alice-candidates.json
```

Hermes Agent can produce a patch like:

```json
{
  "schema": "hermes-local-memory.candidate-review-patch.v1",
  "subject_peer_id": "alice",
  "observer_peer_id": "bob",
  "promote_fact_ids": ["fact_high_signal_preference"],
  "supersede_fact_ids": [{"id": "fact_duplicate", "reason": "already covered by card"}],
  "retract_fact_ids": ["fact_noisy_or_wrong"],
  "card_additions": ["PREFERENCE: Prefers local-first, auditable memory systems"]
}
```

Validate without writing:

```bash
hermes-local-memory --db memory.sqlite apply-candidate-review-patch /tmp/alice-candidate-patch.json \
  --dry-run \
  --json
```

Apply after validation or policy approval:

```bash
hermes-local-memory --db memory.sqlite apply-candidate-review-patch /tmp/alice-candidate-patch.json \
  --apply \
  --json
```

Candidate review patches only change fact status (`active`, `superseded`, `retracted`) and optional compact card additions. Raw messages are never rewritten.

### Review imported cards safely

Honcho and other memory systems may import compact cards that are useful but too verbose, duplicate, stale, or task-local. Card review is the migration cleanup step for that derived layer. It builds a packet containing the current card plus nearby active/candidate facts, lets Hermes Agent draft a cleaned full-card replacement, and validates the replacement before applying.

Build a packet:

```bash
hermes-local-memory --db memory.sqlite card-review-packet \
  --peer alice \
  --observer bob \
  --json > /tmp/alice-card.json
```

Hermes Agent can produce a patch like:

```json
{
  "schema": "hermes-local-memory.card-review-patch.v1",
  "subject_peer_id": "alice",
  "observer_peer_id": "bob",
  "card_replace": [
    "Name: Alice",
    "PREFERENCE: Prefers local-first, auditable memory systems"
  ]
}
```

Validate without writing:

```bash
hermes-local-memory --db memory.sqlite apply-card-review-patch /tmp/alice-card-patch.json \
  --dry-run \
  --json
```

Apply after validation or policy approval:

```bash
hermes-local-memory --db memory.sqlite apply-card-review-patch /tmp/alice-card-patch.json \
  --apply \
  --json
```

Card review is a full-card replacement only. It does not mutate facts and never rewrites raw messages.

### Review unresolved peers

Peer review gives Hermes Agent control over identity mapping while keeping ambiguity safe. A maintenance job can build a packet of newly observed or unverified peers. The agent may move obvious platform aliases to canonical peers, or it may emit human prompts when it cannot safely decide.

Build a packet:

```bash
hermes-local-memory --db memory.sqlite peer-review-packet \
  --json > /tmp/peer-review.json
```

Hermes Agent can produce a patch like:

```json
{
  "schema": "hermes-local-memory.peer-review-patch.v1",
  "alias_moves": [
    {
      "alias": "telegram:1001",
      "to_peer_id": "alice",
      "source": "agent-peer-review",
      "confidence": 0.92,
      "reason": "Conversation context and display name suggest Alice."
    }
  ],
  "human_prompts": [
    {
      "peer_id": "telegram-1002",
      "question": "Who is Telegram user 1002?",
      "suggested_aliases": ["telegram:1002"]
    }
  ]
}
```

Validate without writing:

```bash
hermes-local-memory --db memory.sqlite apply-peer-review-patch /tmp/peer-review-patch.json \
  --dry-run \
  --json
```

Apply after validation or policy approval:

```bash
hermes-local-memory --db memory.sqlite apply-peer-review-patch /tmp/peer-review-patch.json \
  --apply \
  --json
```

Peer review mutates aliases only. It does not rewrite raw messages or delete peer rows. Human prompts are returned in the result for the calling agent/scheduler to deliver through its normal user-interaction channel.

### Consolidate facts and cards

Consolidation produces an inspectable plan for a subject/observer pair. It should usually run after reflection or candidate review has produced candidate/active facts. Dry-run is read-only:

```bash
hermes-local-memory --db memory.sqlite consolidate \
  --peer alice \
  --observer bob \
  --promote-candidates \
  --dry-run \
  --json
```

Apply only after reviewing the plan:

```bash
hermes-local-memory --db memory.sqlite consolidate \
  --peer alice \
  --observer bob \
  --promote-candidates \
  --apply \
  --json
```

Current deterministic behavior:

- reads current card, active facts, and candidate facts
- supersedes candidate facts that duplicate existing card lines or active facts
- optionally promotes unique candidate facts when `--promote-candidates` is passed
- proposes card additions from active facts and promoted candidates
- never deletes raw messages or facts

For imported Honcho data, expect many noisy candidate facts. Prefer agent review, scoped apply decisions, and after-action summaries over blind broad promotion.

### Build a consolidation packet for Hermes Agent

A packet gives Hermes Agent the current card, active facts, candidate facts, aliases, and safety rules in one JSON object:

```bash
hermes-local-memory --db memory.sqlite consolidation-packet \
  --peer alice \
  --observer bob \
  --max-candidates 100 \
  --json > /tmp/alice-packet.json
```

Hermes Agent can reason over this packet and produce a patch with this shape:

```json
{
  "subject_peer_id": "alice",
  "observer_peer_id": "bob",
  "card_replace": ["Name: Alice", "PREFERENCE: Prefers local-first memory"],
  "promote_fact_ids": ["fact_candidate_1"],
  "supersede_fact_ids": [{"id": "fact_duplicate", "reason": "covered by card"}],
  "retract_fact_ids": [],
  "new_facts": []
}
```

Validate without writing:

```bash
hermes-local-memory --db memory.sqlite apply-patch /tmp/alice-patch.json --dry-run --json
```

Apply after validation or policy approval:

```bash
hermes-local-memory --db memory.sqlite apply-patch /tmp/alice-patch.json --apply --json
```

Patch application validates peer/fact IDs, never deletes raw messages, and changes fact lifecycle with status updates (`active`, `superseded`, `retracted`).

### Run all-pairs maintenance

Scheduled jobs usually should not target only one pair. Use `maintenance` to plan/apply deterministic consolidation across every subject/observer pair with cards or facts:

```bash
hermes-local-memory --db memory.sqlite maintenance \
  --promote-candidates \
  --dry-run \
  --json
```

Apply mode runs the same deterministic consolidation for all discovered pairs:

```bash
hermes-local-memory --db memory.sqlite maintenance \
  --promote-candidates \
  --apply \
  --json
```

Hermes cron jobs can use this all-pairs result as the first pass, then reason per pair about what should be applied, skipped, or escalated.

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
hermes-local-memory --db memory.sqlite alias add telegram:1002 \
  --peer carol \
  --source telegram \
  --verified \
  --json

hermes-local-memory --db memory.sqlite alias move telegram:1002 \
  --peer alice \
  --json
```

`alias move` is intentionally just an explicit alias rewrite. It does not rewrite raw messages or facts.

### Add or retract facts

```bash
hermes-local-memory --db memory.sqlite fact add \
  "Alice prefers local-first tools." \
  --peer alice \
  --observer bob \
  --kind preference \
  --json

hermes-local-memory --db memory.sqlite fact retract fact_abc123 --json
```

Retracting a fact marks it `retracted`; it does not delete the row.

### Replace cards

Cards are replaced as a full JSON list of strings:

```bash
cat > /tmp/alice-card.json <<'JSON'
[
  "Name: Alice",
  "Preference: explicit repair commands"
]
JSON

hermes-local-memory --db memory.sqlite card replace \
  --peer alice \
  --observer bob \
  --from-file /tmp/alice-card.json \
  --json
```

Full replacement is intentional: it makes card repair auditable and avoids hidden merge behavior.

## Scheduled reflection and consolidation with Hermes cron

This package intentionally does not embed its own scheduler. Regular memory maintenance should be orchestrated by Hermes' scheduling/cron layer, because Hermes owns model calls, tools, policy, and judgment.

Recommended primary pattern: autonomous but auditable. Reflection runs first; consolidation runs second.

1. schedule a Hermes job with clear repository path, database path, and permission boundaries
2. run `reflection-maintenance` to discover stale sessions and build raw-message review packets
3. have Hermes Agent review each packet and produce reflection patches with candidate facts and session summaries
4. validate every reflection patch with `apply-reflection-patch --dry-run`; apply only narrow, evidence-backed patches
5. run all-pairs `maintenance --dry-run` after reflection so new candidates can be considered
6. inspect every subject/observer pair's card, active facts, candidate facts, aliases, summaries, and rendered context
7. apply narrow, validated consolidation changes for pairs whose plans are clearly safe
8. skip/report sessions or pairs whose plans are large, noisy, ambiguous, identity-confused, or mostly imported meta-facts
9. produce an after-action summary listing reflected sessions, candidate facts, summaries, changed pairs, skipped pairs, and escalations

Example autonomous scheduled job prompt:

```text
Run a Hermes Local Memory reflection + consolidation job.
Repository: /path/to/hermes-local-memory
Database: ~/.hermes/memory/local_memory.sqlite

Use Hermes Agent reasoning to make maintenance decisions. Use Local Memory as the auditable substrate.
Never modify raw messages. Never switch live Hermes provider config.

Phase 1: Reflection / distillation
- Run reflection-maintenance for stale sessions first.
- Review each reflection packet and create reflection patches only for facts clearly supported by packet message IDs.
- New memories from reflection must be candidate facts, not active facts.
- Add session summaries only for the exact message windows reviewed.
- Validate each reflection patch with apply-reflection-patch --dry-run before applying.
- Skip sessions that are noisy, identity-confused, too large, or ambiguous.

Phase 2: Consolidation / all-pairs maintenance
- Run all-pairs maintenance with --dry-run.
- Inspect all subject/observer pairs with cards or facts.
- Apply only narrow, coherent, non-duplicative changes clearly supported by facts/cards/summaries and compatible with that pair's identity.
- Skip pairs whose plan is noisy, large, ambiguous, identity-confused, or mostly imported meta-facts.

Report exactly: reflected sessions, candidate facts added, summaries added, pairs changed, pairs skipped, pairs escalated, and why.
```

Prudent/report-only variant for new deployments, risky imports, or cautious operators:

```text
Run the same Hermes Local Memory reflection + all-pairs consolidation job, but do not apply changes. Produce only a dry-run report with stale session counts, proposed candidate facts/summaries, pair counts, top card additions, top promotions/supersedes, skipped items, and recommendations.
```

Suggested cadence: start nightly. High-volume agents can move to every 6 hours once dry-run reports look clean.

Both patterns keep scheduling and intelligence in Hermes while Local Memory remains local, deterministic, inspectable, and patch-oriented.

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
