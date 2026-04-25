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

    peer = store.upsert_peer("simone", display_name="Simone", kind="human")
    store.set_alias("telegram:151011988", peer_id=peer["id"], source="telegram", verified=True)

    resolved = store.resolve_peer("telegram:151011988")

    assert resolved is not None
    assert resolved["id"] == "simone"
    assert resolved["display_name"] == "Simone"


def test_records_raw_turn_and_searches_facts_with_evidence(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("simone", display_name="Simone", kind="human")
    store.upsert_peer("ambrogio", display_name="Ambrogio", kind="ai")
    store.upsert_session(
        "telegram-dm-151011988",
        profile_id="default",
        platform="telegram",
        external_id="151011988",
        title="Telegram DM with Simone",
    )

    user_msg = store.add_message(
        session_id="telegram-dm-151011988",
        peer_id="simone",
        role="user",
        content="Remember that Sweden searches should be in Swedish and reported in English.",
    )
    store.add_message(
        session_id="telegram-dm-151011988",
        peer_id="ambrogio",
        role="assistant",
        content="Got it.",
    )
    fact = store.add_fact(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        content="Simone prefers Sweden-related searches in Swedish and answers in English.",
        kind="preference",
        evidence_message_ids=[user_msg["id"]],
    )

    results = store.search("Sweden Swedish English", peer_id="simone")

    assert results
    assert results[0]["id"] == fact["id"]
    assert results[0]["evidence_message_ids"] == [user_msg["id"]]


def test_context_block_is_deterministic_and_source_labeled(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("simone", display_name="Simone", kind="human")
    store.upsert_peer("ambrogio", display_name="Ambrogio", kind="ai")
    store.upsert_session("telegram-dm-151011988", profile_id="default", platform="telegram")
    store.add_fact(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        content="Simone values migration paths that preserve history.",
        kind="preference",
        source="manual",
    )
    store.set_card(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        items=["Name: Simone", "Lives in Kungsholmen, Stockholm, Sweden"],
    )

    context = store.build_context(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        session_id="telegram-dm-151011988",
        query="memory migration",
    )

    assert "# Local Memory" in context
    assert "## Compact peer card" in context
    assert "Name: Simone" in context
    assert "## Durable facts" in context
    assert "preserve history" in context
    assert "source=manual" in context
