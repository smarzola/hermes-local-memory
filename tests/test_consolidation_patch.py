from __future__ import annotations

from pathlib import Path

from hermes_local_memory.consolidation import (
    apply_consolidation_patch,
    build_consolidation_packet,
    validate_consolidation_patch,
)
from hermes_local_memory.store import LocalMemoryStore


def _store_for_patch(tmp_path: Path) -> tuple[LocalMemoryStore, dict[str, str]]:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_alias("chat:1001", peer_id="alice", source="chat", verified=True)
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=["Name: Alice"],
    )
    active = store.add_fact(
        fact_id="fact_active",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers inspectable memory.",
        kind="preference",
        status="active",
    )
    candidate = store.add_fact(
        fact_id="fact_candidate",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers agent-integrated memory.",
        kind="preference",
        status="candidate",
    )
    stale = store.add_fact(
        fact_id="fact_stale",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice wants duplicate memory entries.",
        kind="preference",
        status="candidate",
    )
    return store, {"active": active["id"], "candidate": candidate["id"], "stale": stale["id"]}


def test_build_consolidation_packet_contains_context_for_agent(tmp_path: Path) -> None:
    store, ids = _store_for_patch(tmp_path)

    packet = build_consolidation_packet(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        max_candidates=10,
    )

    assert packet["subject_peer_id"] == "alice"
    assert packet["observer_peer_id"] == "bob"
    assert packet["current_card"] == ["Name: Alice"]
    assert [fact["id"] for fact in packet["active_facts"]] == [ids["active"]]
    assert {fact["id"] for fact in packet["candidate_facts"]} == {
        ids["candidate"],
        ids["stale"],
    }
    assert packet["known_aliases"] == ["chat:1001"]
    assert packet["rules"]["preserve_raw_history"] is True
    assert packet["rules"]["patch_schema"] == "hermes-local-memory.consolidation-patch.v1"


def test_validate_consolidation_patch_rejects_unknown_fact_ids(tmp_path: Path) -> None:
    store, _ = _store_for_patch(tmp_path)
    patch = {
        "subject_peer_id": "alice",
        "observer_peer_id": "bob",
        "promote_fact_ids": ["missing_fact"],
    }

    result = validate_consolidation_patch(store, patch)

    assert result["valid"] is False
    assert "unknown fact id: missing_fact" in result["errors"]


def test_apply_consolidation_patch_dry_run_and_apply(tmp_path: Path) -> None:
    store, ids = _store_for_patch(tmp_path)
    patch = {
        "subject_peer_id": "alice",
        "observer_peer_id": "bob",
        "card_replace": [
            "Name: Alice",
            "PREFERENCE: Prefers inspectable memory",
            "PREFERENCE: Prefers agent-integrated memory",
        ],
        "promote_fact_ids": [ids["candidate"]],
        "supersede_fact_ids": [{"id": ids["stale"], "reason": "covered by card"}],
        "new_facts": [
            {
                "content": "Alice prefers maintenance jobs with clear audit logs.",
                "kind": "preference",
                "source": "agent-consolidation",
            }
        ],
    }

    dry_run = apply_consolidation_patch(store, patch, apply=False)

    assert dry_run["mode"] == "dry-run"
    assert dry_run["validation"]["valid"] is True
    assert dry_run["writes"] == []
    assert store.get_fact(ids["candidate"])["status"] == "candidate"
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == ["Name: Alice"]

    applied = apply_consolidation_patch(store, patch, apply=True)

    assert applied["mode"] == "apply"
    assert applied["writes"] == {
        "card_replaced": True,
        "facts_promoted": 1,
        "facts_superseded": 1,
        "facts_retracted": 0,
        "facts_added": 1,
    }
    assert store.get_fact(ids["candidate"])["status"] == "active"
    assert store.get_fact(ids["stale"])["status"] == "superseded"
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == patch["card_replace"]
    added = store.list_facts(peer_id="alice", observer_peer_id="bob", status="active", limit=10)
    assert any(
        fact["content"] == "Alice prefers maintenance jobs with clear audit logs."
        for fact in added
    )
