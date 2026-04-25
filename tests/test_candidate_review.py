from __future__ import annotations

from pathlib import Path

from hermes_local_memory.candidate_review import (
    apply_candidate_review_patch,
    build_candidate_review_packet,
    validate_candidate_review_patch,
)
from hermes_local_memory.store import LocalMemoryStore


def _candidate_store(tmp_path: Path) -> tuple[LocalMemoryStore, dict[str, str]]:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_card(subject_peer_id="alice", observer_peer_id="bob", items=["Name: Alice"])
    high = store.add_fact(
        fact_id="fact_high",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers local-first, auditable memory systems.",
        kind="preference",
        source="honcho-import",
        status="candidate",
        confidence=0.95,
        evidence_message_ids=[1, 2],
    )
    duplicate = store.add_fact(
        fact_id="fact_duplicate",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Name: Alice",
        kind="note",
        source="honcho-import",
        status="candidate",
        confidence=0.8,
    )
    noisy = store.add_fact(
        fact_id="fact_noisy",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice maybe said something vague about stuff.",
        kind="note",
        source="honcho-import",
        status="candidate",
        confidence=0.3,
    )
    other = store.add_fact(
        fact_id="fact_other",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice candidate from reflection.",
        kind="note",
        source="agent-reflection",
        status="candidate",
        confidence=0.9,
    )
    return store, {
        "high": high["id"],
        "duplicate": duplicate["id"],
        "noisy": noisy["id"],
        "other": other["id"],
    }


def test_candidate_review_packet_filters_candidates_and_includes_rules(tmp_path: Path) -> None:
    store, ids = _candidate_store(tmp_path)

    packet = build_candidate_review_packet(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        source="honcho-import",
        limit=10,
    )

    assert packet["schema"] == "hermes-local-memory.candidate-review-packet.v1"
    assert packet["subject_peer_id"] == "alice"
    assert packet["observer_peer_id"] == "bob"
    assert packet["source_filter"] == "honcho-import"
    assert packet["current_card"] == ["Name: Alice"]
    assert {fact["id"] for fact in packet["candidate_facts"]} == {
        ids["high"],
        ids["duplicate"],
        ids["noisy"],
    }
    assert ids["other"] not in {fact["id"] for fact in packet["candidate_facts"]}
    assert packet["rules"]["patch_schema"] == "hermes-local-memory.candidate-review-patch.v1"
    assert packet["rules"]["prefer_promoting_high_signal_preferences"] is True
    assert packet["rules"]["do_not_bulk_promote_imported_candidates"] is True


def test_candidate_review_patch_rejects_unknown_or_wrong_scope_ids(
    tmp_path: Path,
) -> None:
    store, _ = _candidate_store(tmp_path)
    store.upsert_peer("carol", display_name="Carol", kind="human")
    wrong_scope = store.add_fact(
        fact_id="fact_wrong_scope",
        subject_peer_id="carol",
        observer_peer_id="bob",
        content="Carol prefers something else.",
        status="candidate",
    )
    packet = build_candidate_review_packet(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
    )
    patch = {
        "schema": "hermes-local-memory.candidate-review-patch.v1",
        "subject_peer_id": "alice",
        "observer_peer_id": "bob",
        "promote_fact_ids": ["missing", wrong_scope["id"]],
    }

    result = validate_candidate_review_patch(store, packet, patch)

    assert result["valid"] is False
    assert "unknown candidate fact id: missing" in result["errors"]
    assert "fact id not present in candidate review packet: fact_wrong_scope" in result["errors"]


def test_candidate_review_patch_dry_run_and_apply(tmp_path: Path) -> None:
    store, ids = _candidate_store(tmp_path)
    packet = build_candidate_review_packet(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        source="honcho-import",
    )
    patch = {
        "schema": "hermes-local-memory.candidate-review-patch.v1",
        "subject_peer_id": "alice",
        "observer_peer_id": "bob",
        "promote_fact_ids": [ids["high"]],
        "supersede_fact_ids": [{"id": ids["duplicate"], "reason": "already covered by card"}],
        "retract_fact_ids": [ids["noisy"]],
        "card_additions": ["PREFERENCE: Prefers local-first, auditable memory systems"],
    }

    dry_run = apply_candidate_review_patch(store, packet, patch, apply=False)

    assert dry_run["mode"] == "dry-run"
    assert dry_run["validation"]["valid"] is True
    assert dry_run["writes"] == []
    assert store.get_fact(ids["high"])["status"] == "candidate"

    applied = apply_candidate_review_patch(store, packet, patch, apply=True)

    assert applied["mode"] == "apply"
    assert applied["writes"] == {
        "facts_promoted": 1,
        "facts_superseded": 1,
        "facts_retracted": 1,
        "card_replaced": True,
    }
    assert store.get_fact(ids["high"])["status"] == "active"
    assert store.get_fact(ids["duplicate"])["status"] == "superseded"
    assert store.get_fact(ids["noisy"])["status"] == "retracted"
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "PREFERENCE: Prefers local-first, auditable memory systems",
    ]
