# Hermes Local Memory

**Local-first, inspectable, agent-integrated memory for Hermes Agent.**

Hermes Local Memory is an open-source SQLite memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent). It is built for people who want the useful parts of agent memory — profiles, aliases, raw history, facts, cards, search, context injection, migration, and consolidation — without running a separate memory server or trusting an opaque background "dream" system.

The core idea is simple:

> Memory should be a local, auditable substrate that the agent can inspect, reason over, and update through explicit tools — not an opaque appendix bolted onto the side of the agent.

This project is inspired by the good ideas in Honcho, especially peers/cards/consolidation, but deliberately chooses boring engineering: one local SQLite DB, explicit identity mapping, deterministic retrieval, source-labeled context, dry-runs before writes, and agent-generated patches instead of hidden backend mutation.

> Status: **pre-alpha but functional**. The store, provider, plugin shim, CLI inspection/repair tools, Honcho API import, identity maps, and deterministic consolidation MVP are implemented and tested. Do not switch a production Hermes setup without doing a trial import and inspection first.

---

## Why this is different

Most memory systems are either too small — a few strings in a prompt — or too magical: server processes, queues, vector stores, hidden summaries, model-specific workers, and unclear identity rules.

Hermes Local Memory is opinionated in the other direction:

- **Local-first** — default storage is `~/.hermes/memory/local_memory.sqlite`.
- **No memory server** — no FastAPI, Docker, Redis, Postgres, or daemon required.
- **Agent-integrated** — Hermes accesses memory through normal tools like `memory_context`, `memory_search`, `memory_conclude`, and `memory_consolidate`.
- **Inspectable by design** — humans and agents can list peers, aliases, sessions, cards, messages, facts, and rendered context.
- **Identity is data** — aliases like `telegram:1001`, `honcho:Alice`, and `user` point to canonical peers such as `alice`.
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
| `memory_consolidate` | Preview/apply deterministic card/fact consolidation. |

### CLI capabilities

`hermes-local-memory` supports:

- inspect peers, aliases, sessions, cards, messages, facts, search, and rendered context
- explicit alias repair
- explicit fact add/retract
- full-card replacement from JSON
- Honcho API dry-run/apply import
- Honcho identity maps for fragmented peers
- deterministic consolidation dry-run/apply
- consolidation packets for Hermes Agent review
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

### 1. Clone and install

```bash
git clone https://github.com/<owner>/hermes-local-memory.git
cd hermes-local-memory
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
```

If you do not want to install yet, most examples can be run from the checkout with:

```bash
PYTHONPATH=src python -m hermes_local_memory.cli --help
```

### 2. Install the Hermes plugin shim

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

### 3. Configure Hermes

After validating the shim and trial DB, configure Hermes:

```yaml
memory:
  provider: local_memory
```

Then restart Hermes or start a fresh session.

> Recommended: keep your existing provider active until you have imported/inspected data in a separate trial DB.

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

See [CLI docs](docs/cli.md) for full importer behavior.

---

## How the memory flow works

Local Memory separates **raw history**, **durable facts**, **compact cards**, and **agent decisions**.

```text
Conversation turn
  -> raw messages are stored immutably
  -> explicit facts can be added with evidence
  -> search/context retrieve facts and cards deterministically
  -> consolidation periodically reviews candidates and card quality
  -> Hermes Agent decides what to promote, supersede, retract, or summarize
  -> Local Memory validates and applies structured changes
```

The important split is:

- **Local Memory** stores, retrieves, validates, and applies auditable changes.
- **Hermes Agent** reasons about ambiguous memory quality decisions.
- **Hermes cron/scheduler** runs recurring maintenance jobs.

Why maintenance is needed:

- conversations create duplicate or overlapping memories
- imported systems can contain stale identities or noisy derived facts
- candidate facts need promotion, superseding, or retraction
- compact cards should stay useful instead of growing into transcripts
- raw history should remain intact while derived layers improve over time

This is why the project supports both deterministic consolidation and agent-orchestrated scheduled maintenance.

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

5. **Inspect identity and context**

   ```bash
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" peers --json
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" aliases --json
   PYTHONPATH=src python -m hermes_local_memory.cli --db "$LOCAL_MEMORY_DB" context \
     --peer alice \
     --observer bob \
     --query "memory quality"
   ```

6. **Set up scheduled maintenance in Hermes, not in this package**

   Use the cron prompt in [Scheduled maintenance with Hermes cron](#scheduled-maintenance-with-hermes-cron). Start with the trial DB. Only move to a live DB once import, identity mapping, context, and rollback expectations are clear.

7. **Only switch Hermes after validation**

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

## Scheduled maintenance with Hermes cron

Regular memory maintenance is a first-class use case. The recommended path is to let Hermes schedule an autonomous maintenance job that has enough context, clear constraints, and permission boundaries to make routine cleanup decisions itself.

The package should stay simple and local; Hermes should own scheduling, model calls, and judgment.

Recommended autonomous schedule:

- run weekly or after a configurable number of new turns
- discover every subject/observer pair with cards or facts
- inspect each pair's current card, active facts, candidate facts, aliases, and rendered context
- use Hermes Agent to decide which pairs need consolidation
- apply narrow, validated changes per pair when the plan is clearly safe
- deliver a concise all-pairs summary of what changed and what was skipped
- escalate individual pairs to human review when their plan is large, noisy, ambiguous, or would rewrite the card heavily

Example Hermes cron prompt:

```text
Run a Hermes Local Memory maintenance job.
Repository: /path/to/hermes-local-memory
Database: ~/.hermes/memory/local_memory.sqlite

Use Local Memory as the auditable substrate and use Hermes reasoning for judgment.
Inspect all subject/observer pairs with cards or facts.
Run all-pairs maintenance with --dry-run first.
For each pair, apply only narrow, coherent, non-duplicative changes that are clearly supported by facts/cards and fit the pair's identity.
If a pair is noisy, large, ambiguous, identity-confused, or mostly imported Honcho meta-facts, skip that pair and summarize what blocked automatic consolidation.
Never modify raw messages. Never switch the live Hermes provider config. Report exactly what changed, skipped, and escalated for each pair.
```

A more prudent/report-only variant is also useful for new deployments or risky imports:

```text
Run the same all-pairs maintenance job, but do not apply changes. Produce only a dry-run report with pair counts, top proposed card additions, top promotions/supersedes, skipped pairs, and recommendations.
```

This gives both modes:

- **autonomous by default** for well-scoped, well-validated maintenance
- **report-only** when a human wants extra caution

## Documentation

- [CLI reference](docs/cli.md)
- [Features](docs/features.md)
- [Design](docs/design.md)
- [Contributing](CONTRIBUTING.md)
- [Agent instructions](AGENTS.md)

---

## Repository layout

```text
src/hermes_local_memory/
  cli.py             CLI for inspection, repair, import, consolidation, shim install
  consolidation.py   Deterministic consolidation planner/apply logic
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

CI runs on Python 3.10, 3.11, and 3.12.

---

## License

MIT
