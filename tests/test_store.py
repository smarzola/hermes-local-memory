from __future__ import annotations

from pathlib import Path

from hermes_local_memory import LocalMemoryStore


def test_store_initializes_schema_and_default_profile(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite"

    store = LocalMemoryStore(db_path)
    store.initialize()

    profile = store.get_profile("default")
    assert profile is not None
    assert profile["id"] == "default"
    assert profile["display_name"] == "Default"


def test_resolve_alias_creates_verified_peer_mapping(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()

    peer = store.upsert_peer("alice", display_name="Alice", kind="human")
    store.set_alias("telegram:1001", peer_id=peer["id"], source="telegram", verified=True)

    resolved = store.resolve_peer("telegram:1001")

    assert resolved is not None
    assert resolved["id"] == "alice"
    assert resolved["display_name"] == "Alice"


def test_records_raw_turn_and_searches_facts_with_evidence(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.upsert_session(
        "telegram-dm-1001",
        profile_id="default",
        platform="telegram",
        external_id="1001",
        title="Telegram DM with Alice",
    )

    user_msg = store.add_message(
        session_id="telegram-dm-1001",
        peer_id="alice",
        role="user",
        content="Remember that Sweden searches should be in Swedish and reported in English.",
    )
    store.add_message(
        session_id="telegram-dm-1001",
        peer_id="bob",
        role="assistant",
        content="Got it.",
    )
    fact = store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers Sweden-related searches in Swedish and answers in English.",
        kind="preference",
        evidence_message_ids=[user_msg["id"]],
    )

    results = store.search("Sweden Swedish English", peer_id="alice")

    assert results
    assert results[0]["id"] == fact["id"]
    assert results[0]["evidence_message_ids"] == [user_msg["id"]]


def test_context_block_is_deterministic_and_source_labeled(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.upsert_session("telegram-dm-1001", profile_id="default", platform="telegram")
    store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice values migration paths that preserve history.",
        kind="preference",
        source="manual",
    )
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=["Name: Alice", "Lives in Example District, Example City, Sweden"],
    )

    context = store.build_context(
        subject_peer_id="alice",
        observer_peer_id="bob",
        session_id="telegram-dm-1001",
        query="memory migration",
    )

    assert "# Local Memory" in context
    assert "## Compact peer card" in context
    assert "Name: Alice" in context
    assert "## Durable facts" in context
    assert "preserve history" in context
    assert "source=manual" in context
