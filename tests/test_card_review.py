from __future__ import annotations

from pathlib import Path

from hermes_local_memory.card_review import (
    apply_card_review_patch,
    build_card_review_packet,
    validate_card_review_patch,
)
from hermes_local_memory.store import LocalMemoryStore


def _card_review_store(tmp_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=[
            "Name: Alice",
            "PREFERENCE: Prefers local-first memory",
            "PREFERENCE: Is willing to try suggested changes",
            "PREFERENCE: Agreed to proceed with testing a recommendation",
            "PREFERENCE: Prefers local-first memory",
        ],
    )
    store.add_fact(
        fact_id="fact_active",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers local-first memory.",
        kind="preference",
        status="active",
    )
    store.add_fact(
        fact_id="fact_candidate",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers concise durable cards.",
        kind="preference",
        status="candidate",
    )
    return store


def test_card_review_packet_includes_current_card_facts_and_migration_rules(tmp_path: Path) -> None:
    store = _card_review_store(tmp_path)

    packet = build_card_review_packet(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        max_active=10,
        max_candidates=10,
    )

    assert packet["schema"] == "hermes-local-memory.card-review-packet.v1"
    assert packet["subject_peer_id"] == "alice"
    assert packet["observer_peer_id"] == "bob"
    assert packet["current_card"][:2] == [
        "Name: Alice",
        "PREFERENCE: Prefers local-first memory",
    ]
    assert [fact["id"] for fact in packet["active_facts"]] == ["fact_active"]
    assert [fact["id"] for fact in packet["candidate_facts"]] == ["fact_candidate"]
    assert packet["rules"]["patch_schema"] == "hermes-local-memory.card-review-patch.v1"
    assert packet["rules"]["migration_step"] is True
    assert packet["rules"]["preserve_raw_history"] is True
    assert packet["rules"]["card_replace_is_full_card"] is True


def test_card_review_patch_rejects_wrong_scope_duplicates_and_empty_lines(tmp_path: Path) -> None:
    store = _card_review_store(tmp_path)
    packet = build_card_review_packet(store, subject_peer_id="alice", observer_peer_id="bob")
    patch = {
        "schema": "hermes-local-memory.card-review-patch.v1",
        "subject_peer_id": "mallory",
        "observer_peer_id": "bob",
        "card_replace": ["Name: Alice", "", "name: alice"],
    }

    result = validate_card_review_patch(store, packet, patch)

    assert result["valid"] is False
    assert "subject_peer_id must match card review packet" in result["errors"]
    assert "card_replace items must be non-empty strings" in result["errors"]
    assert "card_replace contains duplicate normalized items" in result["errors"]


def test_card_review_patch_dry_run_and_apply_replace_card_only(tmp_path: Path) -> None:
    store = _card_review_store(tmp_path)
    packet = build_card_review_packet(store, subject_peer_id="alice", observer_peer_id="bob")
    patch = {
        "schema": "hermes-local-memory.card-review-patch.v1",
        "subject_peer_id": "alice",
        "observer_peer_id": "bob",
        "card_replace": [
            "Name: Alice",
            "PREFERENCE: Prefers local-first memory",
            "PREFERENCE: Prefers concise durable cards",
        ],
    }

    dry_run = apply_card_review_patch(store, packet, patch, apply=False)

    assert dry_run["mode"] == "dry-run"
    assert dry_run["validation"]["valid"] is True
    assert dry_run["writes"] == []
    assert len(store.get_card(subject_peer_id="alice", observer_peer_id="bob")) == 5
    assert store.get_fact("fact_active")["status"] == "active"
    assert store.get_fact("fact_candidate")["status"] == "candidate"

    applied = apply_card_review_patch(store, packet, patch, apply=True)

    assert applied["mode"] == "apply"
    assert applied["writes"] == {
        "card_replaced": True,
        "before_count": 5,
        "after_count": 3,
    }
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "PREFERENCE: Prefers local-first memory",
        "PREFERENCE: Prefers concise durable cards",
    ]
    assert store.get_fact("fact_active")["status"] == "active"
    assert store.get_fact("fact_candidate")["status"] == "candidate"
