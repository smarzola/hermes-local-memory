from __future__ import annotations

from pathlib import Path

from hermes_local_memory.consolidation import build_maintenance_plan
from hermes_local_memory.store import LocalMemoryStore


def _maintenance_store(tmp_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    for peer_id, name, kind in [
        ("alice", "Alice", "human"),
        ("carol", "Carol", "human"),
        ("bob", "Bob", "ai"),
    ]:
        store.upsert_peer(peer_id, display_name=name, kind=kind)
    store.set_card(subject_peer_id="alice", observer_peer_id="bob", items=["Name: Alice"])
    store.set_card(subject_peer_id="carol", observer_peer_id="bob", items=["Name: Carol"])
    store.add_fact(
        fact_id="alice_candidate",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers local-first memory.",
        kind="preference",
        status="candidate",
    )
    store.add_fact(
        fact_id="carol_candidate",
        subject_peer_id="carol",
        observer_peer_id="bob",
        content="Carol prefers compact cards.",
        kind="preference",
        status="candidate",
    )
    return store


def test_maintenance_plan_covers_all_subject_observer_pairs(tmp_path: Path) -> None:
    store = _maintenance_store(tmp_path)

    plan = build_maintenance_plan(store, promote_candidates=True, apply=False)

    assert plan["mode"] == "dry-run"
    assert plan["counts"] == {
        "pairs": 2,
        "candidate_promotions": 2,
        "candidate_supersedes": 0,
        "card_additions": 2,
    }
    assert {(item["subject_peer_id"], item["observer_peer_id"]) for item in plan["pairs"]} == {
        ("alice", "bob"),
        ("carol", "bob"),
    }
    assert store.get_fact("alice_candidate")["status"] == "candidate"
    assert store.get_fact("carol_candidate")["status"] == "candidate"


def test_maintenance_apply_runs_all_pairs(tmp_path: Path) -> None:
    store = _maintenance_store(tmp_path)

    plan = build_maintenance_plan(store, promote_candidates=True, apply=True)

    assert plan["mode"] == "apply"
    assert plan["writes"] == {
        "pairs_applied": 2,
        "candidate_promotions": 2,
        "candidate_supersedes": 0,
        "cards_replaced": 2,
    }
    assert store.get_fact("alice_candidate")["status"] == "active"
    assert store.get_fact("carol_candidate")["status"] == "active"
    assert "Alice prefers local-first memory." in store.get_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
    )
    assert "Carol prefers compact cards." in store.get_card(
        subject_peer_id="carol",
        observer_peer_id="bob",
    )
