# Hermes Local Memory

**Local-first, inspectable, agent-controlled memory for Hermes Agent.**

Hermes Local Memory is an open-source SQLite memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent). It is built for people who want the useful parts of agent memory — profiles, aliases, raw history, facts, cards, search, context injection, migration, and consolidation — without running a separate memory server or trusting an opaque background "dream" system.

The core idea is simple:

> Memory should be a first-class part of the Hermes Agent runtime: a local, auditable substrate that the agent can inspect, reason over, maintain, and update through explicit tools — not an opaque appendix bolted onto the side of the agent.

This project is inspired by the good ideas in Honcho, especially peers/cards/consolidation, but deliberately chooses boring engineering: one local SQLite DB, explicit identity mapping, deterministic retrieval, source-labeled context, dry-runs before writes, and agent-generated patches instead of hidden backend mutation.

> Status: **alpha**. The store, provider, plugin shim, CLI inspection/repair tools, Hermes markdown import, Honcho API import, identity maps, peer/candidate/card review, reflection, and deterministic consolidation are implemented and tested. Do not switch a production Hermes setup without doing a trial import and inspection first.

---

## Why this is different

Most memory systems are either too small — a few strings in a prompt — or too magical: server processes, queues, vector stores, hidden summaries, model-specific workers, and unclear identity rules.

Hermes Local Memory is opinionated in the other direction:

- **Local-first** — default storage is `~/.hermes/memory/local_memory.sqlite`.
- **No memory server** — no FastAPI, Docker, Redis, Postgres, or daemon required.
- **Agent-controlled** — Hermes is expected to inspect, curate, and maintain memory through normal tools like `memory_context`, `memory_search`, `memory_conclude`, and `memory_consolidate`.
- **Memory is first-class** — context, peers, aliases, cards, facts, summaries, and maintenance packets are part of the agent workflow, not a passive appendix.
- **Inspectable by design** — humans and agents can list peers, aliases, sessions, cards, messages, facts, and rendered context.
- **Identity is data** — aliases like `telegram:1001`, `honcho:Alice`, and `user` point to canonical peers such as `alice`.
- **Peers are agent-maintained** — scheduled peer review lets the agent map new platform identities to canonical peers or escalate ambiguous identities for human help.
- **Raw history is preserved** — imports copy raw messages; identity repair does not rewrite historical rows unless an explicit tool says so.
- **Consolidation is explicit** — deterministic dry-runs produce plans; future agent-assisted consolidation should produce validated patches.
- **Migration-safe** — Honcho import is additive/idempotent, supports identity maps, and never mutates Honcho.
- **Usable by agents** — CLI JSON output, clear docs, tests, and `AGENTS.md` are first-class.

---

## What it offers today

### Hermes provider tools

`LocalMemoryProvider` exposes:

| Tool | Purpose |
| --- | --- |
| `memory_profile` | Read or replace compact peer cards. |
| `memory_search` | Search active durable facts through SQLite FTS5. |
| `memory_context` | Show exactly what local memory would inject into the prompt. |
| `memory_conclude` | Add durable facts with evidence links to the most recent synced user turn. |
| `memory_consolidate` | Preview/apply deterministic card/fact consolidation for one peer. |
| `memory_maintenance` | Preview/apply deterministic consolidation across all subject/observer pairs. |
| `memory_peer_review` | Build peer review packets so the agent can maintain aliases and escalate ambiguous identities. |
| `memory_reflection_maintenance` | Build reflection packets for stale sessions before consolidation. |

### CLI capabilities

`hermes-local-memory` supports:

- inspect peers, aliases, sessions, cards, messages, facts, search, and rendered context
- explicit alias repair
- explicit fact add/retract
- full-card replacement from JSON
- Hermes built-in markdown memory dry-run/apply import from `USER.md` / `MEMORY.md`
- Honcho API dry-run/apply import
- Honcho identity maps for fragmented peers
- reflection packets for stale raw-message windows
- validated reflection patch dry-run/apply for candidate facts and session summaries
- candidate review packets for safe imported fact promotion
- validated candidate review patch dry-run/apply
- peer review packets for agent-controlled identity maintenance
- validated peer review patch dry-run/apply
- deterministic consolidation dry-run/apply
- consolidation packets for Hermes Agent review
- all-pairs maintenance dry-run/apply
- validated consolidation patch dry-run/apply
- Hermes plugin shim installation

### Data model

The SQLite store includes:

- `profiles`
- `peers`
- `peer_aliases`
- `sessions`
- `session_peers`
- `messages` + FTS
- `facts` + FTS
- `cards`
- `summaries`

---

## Quick install for humans

### Option A: install as a tool

After a package release is available:

```bash
uv tool install hermes-local-memory
# or
pipx install hermes-local-memory
```

Before a package release, install from GitHub:

```bash
uv tool install git+https://github.com/smarzola/hermes-local-memory.git
# or
pipx install git+https://github.com/smarzola/hermes-local-memory.git
```

Verify:

```bash
hermes-local-memory --help
```

### Option B: run from a checkout

```bash
git clone https://github.com/smarzola/hermes-local-memory.git
cd hermes-local-memory
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
```

Without installing:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli --help
```

### Install the Hermes plugin shim

From an installed package:

```bash
hermes-local-memory install-shim --hermes-home ~/.hermes
```

From a checkout:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
```

This writes:

```text
~/.hermes/plugins/local_memory/__init__.py
```

It does **not** modify `~/.hermes/config.yaml` and does **not** switch your live memory provider.

### Configure Hermes

After validating the shim and trial DB, configure Hermes:

```yaml
memory:
  provider: local_memory
```

Then restart Hermes or start a fresh session.

> Recommended: keep your existing provider active until you have imported/inspected data in a separate trial DB.

Full setup/adoption guide: [docs/setup.md](docs/setup.md).

---

## Basic CLI examples

Global `--db` goes before the subcommand:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory.sqlite peers --json
```

Inspect memory:

```bash
hermes-local-memory --db memory.sqlite peers --json
hermes-local-memory --db memory.sqlite aliases --json
hermes-local-memory --db memory.sqlite cards --peer alice --observer bob --json
hermes-local-memory --db memory.sqlite facts --peer alice --observer bob --json
hermes-local-memory --db memory.sqlite context \
  --peer alice \
  --observer bob \
  --query "what should I remember?"
```

Add explicit memory:

```bash
hermes-local-memory --db memory.sqlite fact add \
  "Alice prefers local-first memory systems." \
  --peer alice \
  --observer bob \
  --kind preference \
  --json
```

Repair an alias:

```bash
hermes-local-memory --db memory.sqlite alias add telegram:1001 \
  --peer alice \
  --source telegram \
  --verified \
  --json
```

Preview consolidation:

```bash
hermes-local-memory --db memory.sqlite consolidate \
  --peer alice \
  --observer bob \
  --promote-candidates \
  --dry-run \
  --json
```

Apply only after review:

```bash
hermes-local-memory --db memory.sqlite consolidate \
  --peer alice \
  --observer bob \
  --promote-candidates \
  --apply \
  --json
```

Build an agent review packet and apply a validated patch:

```bash
hermes-local-memory --db memory.sqlite consolidation-packet \
  --peer alice \
  --observer bob \
  --json > /tmp/alice-packet.json

hermes-local-memory --db memory.sqlite apply-patch /tmp/alice-patch.json --dry-run --json
hermes-local-memory --db memory.sqlite apply-patch /tmp/alice-patch.json --apply --json
```

Run deterministic maintenance across all subject/observer pairs:

```bash
hermes-local-memory --db memory.sqlite maintenance \
  --promote-candidates \
  --dry-run \
  --json
```

---

## Migrating from Hermes built-in markdown memory

For users who only used Hermes' standard built-in markdown memory, migration is simpler than Honcho: import the local `USER.md` and `MEMORY.md` files from `~/.hermes/memories`.

Dry-run into a trial DB first:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory_trial.sqlite import hermes-markdown \
  --source-dir ~/.hermes/memories \
  --user-peer alice \
  --assistant-peer bob \
  --dry-run \
  --json
```

Apply only after reviewing the plan:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory_trial.sqlite import hermes-markdown \
  --source-dir ~/.hermes/memories \
  --user-peer alice \
  --assistant-peer bob \
  --apply \
  --json
```

Import behavior:

- `USER.md` entries become active user facts for `alice` observed by `bob`.
- `USER.md` entries also become Alice's compact card for Bob.
- `MEMORY.md` entries become active agent/self facts for `bob` observed by `bob`.
- `MEMORY.md` entries also become Bob's self-card.
- entries are split using Hermes' standard `§` delimiter.
- the import is additive and idempotent; existing facts are skipped on repeated apply.
- an existing target DB is backed up automatically unless `--no-backup` is passed.

Because markdown memory is already curated, imported facts are active by default. You can still run card review or consolidation afterward if you want a cleaner compact card before switching providers.

---

## Migrating from Honcho

Preferred path: use the Honcho HTTP API, not direct database reads.

Dry-run:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory_trial.sqlite import honcho-api \
  --base-url http://localhost:8000/v3 \
  --workspace hermes \
  --api-key "$HONCHO_API_KEY" \
  --dry-run \
  --json
```

Apply to a **trial DB**:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory_trial.sqlite import honcho-api \
  --base-url http://localhost:8000/v3 \
  --workspace hermes \
  --api-key "$HONCHO_API_KEY" \
  --apply \
  --json
```

Use identity maps to collapse fragmented Honcho identities into canonical local peers:

```json
{
  "peers": {
    "honcho:1001": "alice",
    "honcho:Alice": "alice",
    "honcho:1002": "carol",
    "honcho:Bob": "bob"
  },
  "patterns": {
    "honcho:user-default*": "alice"
  },
  "display_names": {
    "alice": "Alice",
    "carol": "Carol",
    "bob": "Bob"
  },
  "kinds": {
    "alice": "human",
    "carol": "human",
    "bob": "ai"
  }
}
```

Then pass:

```bash
--identity-map ~/.hermes/local-memory-identity-map.json
```

After import, treat candidate facts and imported cards as separate review steps:

1. use `candidate-review-packet` / `apply-candidate-review-patch` to promote only high-signal imported candidate facts;
2. use `card-review-packet` / `apply-card-review-patch` to clean imported cards so compact prompt context does not inherit stale, duplicate, or task-local lines.

Example card cleanup packet:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory_trial.sqlite card-review-packet \
  --peer alice \
  --observer bob \
  --json > /tmp/alice-card-packet.json
```

Example full-card replacement patch:

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

Apply only after a dry-run validation:

```bash
hermes-local-memory --db ~/.hermes/memory/local_memory_trial.sqlite apply-card-review-patch \
  /tmp/alice-card-patch.json \
  --dry-run \
  --json
```

See [CLI docs](docs/cli.md) for full importer and migration-review behavior.

---

## How the memory flow works

Local Memory separates **raw history**, **peers**, **reflection**, **durable facts**, **compact cards**, and **agent decisions**. The agent is not merely reading a memory appendix; it is responsible for operating this memory substrate through explicit tools and auditable maintenance jobs.

```text
Normal conversation turn
  -> Hermes injects a compact source-labeled context block
  -> user/assistant messages are stored immutably as raw history
  -> explicit facts can be added immediately with evidence

Scheduled peer review
  -> new or unverified platform identities become peer review packets
  -> Hermes Agent maps obvious aliases to canonical peers
  -> ambiguous identities are escalated as human prompts instead of guessed
  -> Local Memory validates and applies explicit alias moves

Scheduled reflection / distillation
  -> stale raw-message windows become reflection packets
  -> Hermes Agent reviews the packets
  -> Local Memory validates reflection patches
  -> candidate facts and session summaries are written with evidence

Scheduled consolidation / maintenance
  -> candidate facts + active facts + cards are reviewed across all subject/observer pairs
  -> Hermes Agent decides what to promote, supersede, retract, or compact into cards
  -> Local Memory validates and applies structured changes

Next prompt injection
  -> compact card + durable facts + session summary + relevant retrieval are injected
```

The important split is:

- **Local Memory** stores, retrieves, validates, and applies auditable changes.
- **Hermes Agent** owns memory decisions: peer mapping, candidate promotion, card cleanup, reflection review, and consolidation choices.
- **Humans** are asked only when the agent cannot safely infer a peer or when policy requires approval.
- **Hermes cron/scheduler** runs recurring peer review, reflection, and consolidation.

The profile/card is **not** the only thing injected. Context Builder v2 composes ordinary prompt context from:

1. identity/session information,
2. aliases for the current subject peer,
3. the compact subject/observer card,
4. active durable facts,
5. the current session summary when available,
6. relevant retrieved active facts for the current query.

Candidate facts and raw message windows are usually **not** injected into ordinary conversations. They are primarily used during maintenance/review jobs unless explicitly requested.

Why maintenance is needed:

- ordinary conversations create useful memories that are not explicitly saved during the turn
- conversations also create duplicate or overlapping memories
- imported systems can contain stale identities or noisy derived facts
- candidate facts need promotion, superseding, or retraction
- compact cards should stay useful instead of growing into transcripts
- raw history should remain intact while derived layers improve over time

This is why the project supports both reflection/distillation and deterministic all-pairs consolidation, orchestrated by Hermes scheduled jobs rather than hidden backend workers.

---

## Setup checklist for agents

If a human hands this repository to an agent, the agent should be able to bootstrap safely with this checklist:

1. **Inspect repository state**

   ```bash
   git status --short
   PYTHONPATH=src pytest -q
   ruff check .
   ```

2. **Install the Hermes shim without switching providers**

   ```bash
   PYTHONPATH=src python -m hermes_local_memory.cli install-shim --hermes-home ~/.hermes
   ```

3. **Create or choose a trial DB**

   ```bash
   export LOCAL_MEMORY_DB=~/.hermes/memory/local_memory_trial.sqlite
   ```

4. **Import external memory only into the trial DB first**

   ```bash
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" import honcho-api \
     --base-url http://localhost:8000/v3 \
     --workspace hermes \
     --identity-map ~/.hermes/local-memory-identity-map.json \
     --dry-run \
     --json
   ```

5. **Review imported candidates and cards before judging context quality**

   ```bash
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" candidate-review-packet \
     --peer alice \
     --observer bob \
     --source honcho-api-conclusion \
     --limit 100 \
     --json > /tmp/alice-candidates.json

   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" card-review-packet \
     --peer alice \
     --observer bob \
     --json > /tmp/alice-card.json
   ```

   Have Hermes Agent produce validated patches, dry-run them first, and apply only narrow, reviewed changes to the trial DB.

6. **Inspect identity and context**

   ```bash
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" peers --json
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" aliases --json
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" context \
     --peer alice \
     --observer bob \
     --query "memory quality"
   ```

7. **Set up scheduled maintenance in Hermes, not in this package**

   Use the cron prompt in [Scheduled maintenance with Hermes cron](#scheduled-maintenance-with-hermes-cron). Start with the trial DB. Only move to a live DB once import, identity mapping, context, and rollback expectations are clear.

8. **Only switch Hermes after validation**

   ```yaml
   memory:
     provider: local_memory
   ```

Full command reference: [docs/cli.md](docs/cli.md).

---

## Agent workflow

Agents should treat Local Memory as an auditable system of record.

Before repairs or migration:

```bash
hermes-local-memory --db memory.sqlite peers --json
hermes-local-memory --db memory.sqlite aliases --json
hermes-local-memory --db memory.sqlite cards --peer <peer> --observer <assistant> --json
hermes-local-memory --db memory.sqlite facts --peer <peer> --observer <assistant> --json
hermes-local-memory --db memory.sqlite messages --peer <peer> --json
hermes-local-memory --db memory.sqlite context --peer <peer> --observer <assistant> --query "current task"
```

When consolidating, prefer an autonomous-but-auditable agent loop:

1. generate a consolidation packet or plan with enough evidence and constraints
2. let Hermes Agent reason over it and choose the action
3. have Hermes produce a structured patch or call the appropriate memory tool
4. validate/diff/apply through Local Memory
5. inspect rendered context after apply
6. never mutate raw messages as part of consolidation

Agent-assisted consolidation should follow this pattern:

```text
SQLite packet -> Hermes Agent reasoning -> structured patch/tool call -> validation/diff -> explicit or policy-approved apply
```

The memory package should not own model calls. Hermes should.

---

## Scheduled peer review, reflection, and consolidation with Hermes cron

Regular memory maintenance is a first-class use case. The recommended path is to let Hermes schedule an autonomous job that has enough context, clear constraints, and permission boundaries to make routine memory-quality decisions itself.

The package should stay simple and local; Hermes should own scheduling, model calls, and judgment.

Recommended autonomous cadence:

- run nightly for most users, or every 6 hours for high-volume agents
- first run **peer review** so new platform identities can be mapped before downstream reflection/consolidation
- then run **reflection/distillation** over stale sessions so ordinary conversation can become candidate facts and summaries
- then run **all-pairs consolidation** across every subject/observer pair with cards or facts
- inspect each pair's current card, active facts, candidate facts, aliases, summaries, and rendered context
- apply narrow, validated changes when the plan is clearly safe
- deliver a concise report of reflected sessions, changed pairs, skipped pairs, and escalations
- escalate individual sessions/pairs when plans are large, noisy, ambiguous, identity-confused, or would rewrite cards heavily

Peer review should generally run before reflection and consolidation:

```text
new platform identities -> peer review packets -> alias moves or human prompts
raw messages -> reflection packets -> candidate facts + session summaries
candidate facts + active facts + cards -> consolidation -> compact cards
compact cards + durable facts + summaries + retrieval -> prompt injection
```

Example Hermes cron prompt:

```text
Run a Hermes Local Memory peer review + reflection + consolidation job.
Repository: /path/to/hermes-local-memory
Database: ~/.hermes/memory/local_memory.sqlite

Use Local Memory as the auditable substrate and use Hermes reasoning for judgment.
Never modify raw messages. Never switch the live Hermes provider config.

Phase 1: Peer review / identity maintenance
- Run peer-review-packet first.
- If a new platform peer clearly maps to an existing canonical peer, produce a peer-review patch that moves only the alias.
- If identity is ambiguous, produce a human prompt with the concrete peer id, aliases, and question instead of guessing.
- Validate each peer-review patch with apply-peer-review-patch --dry-run before applying.
- Do not delete peer rows or rewrite raw message history.

Phase 2: Reflection / distillation
- Run reflection-maintenance for stale sessions after peer review.
- Review each reflection packet and create reflection patches only for facts clearly supported by packet message IDs.
- New memories from reflection must be candidate facts, not active facts.
- Add session summaries only for the exact message windows reviewed.
- Validate each reflection patch with apply-reflection-patch --dry-run before applying.
- Skip sessions that are noisy, identity-confused, too large, or ambiguous.

Phase 3: Consolidation / all-pairs maintenance
- Run all-pairs maintenance with --dry-run.
- Inspect all subject/observer pairs with cards or facts.
- Apply only narrow, coherent, non-duplicative changes clearly supported by facts/cards/summaries and compatible with that pair's identity.
- Skip pairs whose plan is noisy, large, ambiguous, identity-confused, or mostly imported meta-facts.

Report exactly: peer aliases moved, human identity prompts, reflected sessions, candidate facts added, summaries added, pairs changed, pairs skipped, pairs escalated, and why.
```

A more prudent/report-only variant is also useful for new deployments or risky imports:

```text
Run the same peer review + reflection + all-pairs consolidation job, but do not apply changes. Produce only a dry-run report with unresolved peer counts, proposed alias moves, human identity questions, stale session counts, proposed candidate facts/summaries, pair counts, top card additions, top promotions/supersedes, skipped items, and recommendations.
```

This gives both modes:

- **autonomous by default** for well-scoped, well-validated maintenance
- **report-only** when a human wants extra caution

To schedule this from Hermes, create a recurring Hermes cron job with a self-contained version of the prompt above. Recommended starting schedule: nightly. High-volume deployments can move to every 6 hours after the dry-run reports look clean.

## Documentation

- [Setup and adoption guide](docs/setup.md)
- [CLI reference](docs/cli.md)
- [Features](docs/features.md)
- [Design](docs/design.md)
- [Release checklist](docs/release.md)
- [Contributing](CONTRIBUTING.md)
- [Agent instructions](AGENTS.md)

---

## Repository layout

```text
src/hermes_local_memory/
  cli.py             CLI for inspection, repair, import, consolidation, shim install
  consolidation.py   Deterministic consolidation planner/apply logic
  peer_review.py     Agent peer/alias review packet and patch logic
  hermes_markdown_import.py  Hermes USER.md / MEMORY.md importer
  hermes_plugin.py   Hermes user-plugin shim renderer
  honcho_api.py      stdlib Honcho HTTP API exporter
  honcho_import.py   Honcho import planner/apply logic + identity maps
  provider.py        Hermes-compatible provider lifecycle and tools
  schema.py          SQLite schema bootstrap
  store.py           SQLite store and deterministic retrieval core

tests/
  test_*.py          Store, provider, CLI, import, plugin, consolidation tests
```

---

## Development

```bash
cd hermes-local-memory
PYTHONPATH=src pytest -q
ruff check .
PYTHONPATH=src python -m compileall -q src tests
```

Build package artifacts before release:

```bash
uv build
# or: python -m build
```

CI runs on Python 3.11, 3.12, 3.13, and 3.14. See [docs/release.md](docs/release.md) for the release checklist.

---

## License

MIT
