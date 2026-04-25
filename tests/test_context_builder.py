from __future__ import annotations

from pathlib import Path

from hermes_local_memory import LocalMemoryStore


def _context_store(tmp_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_alias("telegram:1001", peer_id="alice", source="telegram", verified=True)
    store.set_alias("user", peer_id="alice", source="builtin", verified=True)
    store.set_alias("ai", peer_id="bob", source="builtin", verified=True)
    store.upsert_session(
        "telegram-dm-1001",
        profile_id="default",
        platform="telegram",
        external_id="1001",
        title="Telegram DM with Alice",
    )
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=["Name: Alice", "Prefers local-first memory"],
    )
    store.add_fact(
        fact_id="fact_pinned",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice wants Sweden-related searches performed in Swedish and reported in English.",
        kind="preference",
        source="manual",
        status="active",
    )
    for index in range(8):
        store.add_fact(
            fact_id=f"fact_filler_{index}",
            subject_peer_id="alice",
            observer_peer_id="bob",
            content=f"Alice durable filler fact {index}.",
            kind="note",
            source="manual",
            status="active",
        )
    store.add_fact(
        fact_id="fact_relevant",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice is adopting a local memory provider for Hermes.",
        kind="project",
        source="agent-reflection",
        status="active",
    )
    store.add_fact(
        fact_id="fact_candidate",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice may want noisy imported facts promoted blindly.",
        kind="preference",
        source="honcho-import",
        status="candidate",
    )
    store.add_summary(
        scope="session",
        scope_id="telegram-dm-1001",
        content="Alice and Bob discussed adopting Local Memory in shadow mode.",
        covered_from_message_id=1,
        covered_to_message_id=12,
        model="hermes-agent",
    )
    return store


def test_context_v2_injects_identity_card_facts_summary_and_retrieval(tmp_path: Path) -> None:
    store = _context_store(tmp_path)

    context = store.build_context(
        subject_peer_id="alice",
        observer_peer_id="bob",
        session_id="telegram-dm-1001",
        query="Hermes local memory adoption",
    )

    assert context.startswith("# Local Memory")
    assert "## Identity" in context
    assert "Subject peer: `alice`" in context
    assert "Subject display name: Alice" in context
    assert "Observer peer: `bob`" in context
    assert "Session: `telegram-dm-1001`" in context
    assert "Session title: Telegram DM with Alice" in context
    assert "Aliases: `telegram:1001`, `user`" in context

    assert "## Compact peer card" in context
    assert "- Name: Alice" in context
    assert "- Prefers local-first memory" in context

    assert "## Durable facts" in context
    assert "durable filler fact" in context
    assert "source=manual" in context

    assert "## Current session summary" in context
    assert "shadow mode" in context
    assert "covered=1-12" in context

    assert "## Relevant retrieved memories" in context
    assert "local memory provider" in context

    assert "candidate" not in context.lower()
    assert "promoted blindly" not in context


def test_context_v2_has_explicit_empty_sections_for_auditing(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")

    context = store.build_context(subject_peer_id="alice", observer_peer_id="bob")

    assert "## Identity" in context
    assert "Subject peer: `alice`" in context
    assert "## Compact peer card" in context
    assert "(no card)" in context
    assert "## Durable facts" in context
    assert "(no active facts)" in context
    assert "## Current session summary" not in context
