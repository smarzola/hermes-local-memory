# Memory Maintenance Findings

Date: 2026-04-25
Repository: `hermes-local-memory`
Status: historical investigation notes / partially superseded by v0.2.0

## Summary

The current local-memory maintenance path is conservative and preserves data, but it does **not** yet perform a full autonomous rebuild from raw conversation history into rich peer facts and cards.

The practical consequence is that a peer can have substantial raw-message history while still showing a sparse compact card and only a few active durable facts. This is not primarily an identity-resolution failure; it is a missing pipeline stage between raw-message reflection packets and applied durable memory updates.

The current implemented flow is closer to:

```text
raw messages -> reflection packets -> agent review -> memory_apply_reflection_patch -> candidate review / maintenance -> memory_get_card / memory_context verification
```

A complete autonomous maintenance system needs to become:

```text
raw messages
  -> reflection packet selection
  -> evidence-linked fact extraction
  -> conservative candidate creation
  -> safe promotion / superseding
  -> compact card rebuild
  -> inspectable diff + verification
```

## Debug observations

### 1. Peer identity can be correct while memory remains sparse

Peer review showed the relevant peer had expected aliases and was not obviously split across many identities.

Example pattern:

```text
peer: secondary-user
aliases:
  - telegram:<id> verified
  - honcho:<id> unverified/imported
```

This means the sparse memory state cannot be explained only by alias fragmentation. The memory extraction/consolidation pipeline is the more likely failure point.

### 2. `memory_context(peer=...)` reports only active facts and the compact card

The context tool correctly exposes what the assistant would receive for a peer:

- identity
- aliases
- compact peer card
- active durable facts
- relevant search hits, when requested

In the failing case, the peer context contained only a small card and a small number of active facts. This confirmed that the live injected memory was sparse, not merely that the assistant failed to recall it.

### 3. `memory_search(peer=...)` only found the same sparse active facts

Search against the peer returned only the same few active facts already shown by `memory_context`.

This indicates that durable memory for the peer was sparse. It does **not** prove raw history is sparse.

### 4. Reflection packet building sees raw material, but packet building itself does not apply it

Reflection maintenance reported many sessions and unreflected messages.

Important finding: reflection maintenance currently builds or previews reflection packets. It does not automatically complete all of these steps:

1. read every packet,
2. extract peer-specific facts,
3. store candidate facts,
4. promote safe candidates,
5. rebuild compact cards.

Therefore the presence of unreflected packets explains why raw history can exist without becoming durable memory.

### 5. `memory_maintenance(...)` consolidates existing facts/cards; it does not mine raw messages

The maintenance tool currently operates over existing facts, candidate facts, cards, and summaries. It is not a raw-history distillation engine.

Therefore it cannot independently discover rich missing facts for a peer if those facts have not already been extracted from messages into candidate or active facts.

### 6. Candidate promotion must remain conservative

A previous dry-run produced suspiciously large numbers of proposed promotions/card additions. This exposed a dangerous class of bug: imported or noisy candidate facts can appear unique and therefore look promotable unless policy explicitly blocks them.

Policy outcome:

- Large ambiguous candidate promotions should be treated as tooling regressions.
- Imported Honcho-style candidates should not be blindly promoted.
- Maintenance should skip unsafe batches rather than fill memory with noisy speech reports.

### 7. The legacy `memory_profile` API was footgun-prone

`memory_profile(peer=...)` used to be a getter while `memory_profile(peer=..., card=[...])` was also a setter, which made accidental empty-card writes too easy. The canonical provider API now exposes separate tools:

```text
memory_get_card(peer="alice")
memory_set_card(peer="alice", card=[...])
```

The write path rejects accidental empty-card writes unless `allow_empty=true` is provided. `memory_profile` may remain as a hidden compatibility alias, but agents should not use it.

## Root cause hypothesis

The sparse-card issue is caused by a missing autonomous reflection-application stage, not by a lack of raw data.

Current state:

```text
raw messages exist
reflection packets can identify unprocessed message windows
and the provider now has tool-native reflection patch apply, candidate review, card review, and deterministic maintenance tools; scheduled agents must run the whole cycle rather than only packet selection
```

The system now depends on agents using the full provider-tool maintenance cycle rather than stopping after packet selection or manually calling everyday memory tools for repair.

That is prompt-dependent and not robust enough for a memory backend.

## Desired maintenance cycle

A trustworthy maintenance cycle should be explicit, code-policy-driven, and inspectable.

### Step 1: Backup

Before applying maintenance:

```text
create timestamped DB backup
record package version / git SHA
record maintenance command and options
```

### Step 2: Identity review

Use peer review to find:

- unresolved aliases
- duplicate peers
- unverified imported aliases
- sessions with ambiguous participants

Output should be a structured report and an optional safe apply step.

### Step 3: Reflection packet selection

Select raw-message windows that need reflection:

- enough unreflected messages
- known participant identities
- bounded packet size
- stable session ordering

### Step 4: Evidence-linked extraction

For each packet, extract structured candidate facts with evidence:

```json
{
  "subject_peer_id": "alice",
  "observer_peer_id": "assistant",
  "kind": "preference",
  "content": "Alice prefers compact memory summaries.",
  "confidence": 0.86,
  "evidence_message_ids": [123, 124],
  "source": "reflection"
}
```

Extraction must avoid turning assistant narration into user facts.

Bad:

```text
Assistant said Alice likes X.
```

Good:

```text
Alice explicitly said she likes X.
```

### Step 5: Candidate storage

Store extracted facts as candidates unless they meet strict active-fact criteria.

Immediate active write is appropriate when:

- user explicitly says to remember it,
- the assistant calls the memory conclusion tool intentionally,
- the fact is a high-confidence stable preference or identity fact,
- the fact is corroborated across multiple evidence points.

### Step 6: Conservative promotion and superseding

Promote candidates only when safe:

- unique,
- evidence-linked,
- not imported-noise,
- not merely assistant speech,
- not contradicted by active facts,
- not sensitive without user intent.

Supersede older facts rather than duplicating them.

### Step 7: Compact card rebuild

Rebuild compact cards from active facts and selected high-value summaries.

The card should be a projection of durable facts, not a separate ungrounded truth source.

Card rebuilds should produce a diff:

```diff
+ Alice prefers compact memory summaries.
~ Alice lives in Example City -> Alice lives in Example City, Example Country.
- Duplicate imported phrasing removed.
```

### Step 8: Verification

After applying maintenance, verify with tools:

- `memory_context(peer=...)`
- `memory_search(query=..., peer=...)`
- `memory_get_card(peer=...)`
- maintenance summary counters

The final report should include counts such as:

```text
packets_reviewed: 12
candidate_facts_created: 31
facts_promoted: 4
facts_superseded: 2
card_updates: 3
unsafe_promotions_skipped: 19
```

## Required product changes

### 1. Tool-native reflection apply step

Implemented provider tool:

```text
memory_apply_reflection_patch(packet=..., patch=..., apply=false|true)
```

or a higher-level tool:

```text
memory_reflect(apply=false, peer="alice", since="7d")
```

It should return a diff and counters before applying.

### 2. Make maintenance autonomous but policy-bound

Maintenance should not rely on a long prompt to be safe. Safety rules should live in code and tests.

Examples:

- Do not auto-promote imported Honcho conclusions.
- Do not promote assistant-speech facts as user facts.
- Do not apply huge promotion batches without review.
- Do not write compact-card entries without traceable evidence.

### 3. Make card writes explicit

Avoid accidental destructive writes by changing the API shape around card updates.

At minimum:

- prefer `memory_get_card` and `memory_set_card` as separate canonical tools,
- reject empty cards by default,
- return a before/after diff.

### 4. Add regression tests for sparse-peer rebuilds

Test scenario:

1. create two peers,
2. add many raw messages involving the second peer,
3. run reflection maintenance,
4. apply reflection,
5. verify second peer receives extracted facts and a rebuilt card.

Assertions:

- raw messages are preserved,
- facts have evidence IDs,
- assistant narration is not converted into user facts,
- card entries are grounded in active facts,
- large ambiguous candidate batches are skipped.

### 5. Add debug reporting to maintenance

Maintenance output should always make clear which stages ran:

```text
identity_review: ran
reflection_packet_selection: ran
reflection_extraction: skipped/no extractor configured
candidate_creation: skipped
candidate_promotion: ran
card_rebuild: ran
verification: ran
```

This avoids the misleading impression that `memory_maintenance` performed raw-history distillation when it only consolidated existing facts/cards.

## Operational guidance until fixed

Operational guidance for rich peer-card repair:

1. inspect peer context,
2. search durable facts,
3. generate reflection packets,
4. manually extract conservative high-confidence facts,
5. apply reflection/candidate/card patches through provider apply tools,
6. update compact cards with `memory_set_card` only for explicit full-card replacement,
7. verify with `memory_get_card` and `memory_context`.

Do not repair normal memory/card state by editing SQLite directly.

## Open questions

1. Should reflection extraction use the main Hermes model, a cheaper local model, or a configurable extractor provider?
2. Should extracted facts default to `candidate` or should high-confidence identity/preferences become `active` immediately?
3. What exact policy should define a "large suspicious batch"?
4. Should compact cards be fully rebuilt from active facts every time, or patched incrementally with diffs?
5. How should shared sessions assign facts between participants when messages mention several peers?

## Conclusion

The local memory design is on the right track: SQLite, explicit peers, aliases, facts, cards, summaries, and inspectable tools are the right primitives.

The historical weakness was that agents could stop after packet generation or use ad hoc card writes. The next engineering milestone is to keep the provider-tool maintenance cycle documented, packaged as a project skill, and covered by regression tests so other agents do not drift back into out-of-band repairs.
