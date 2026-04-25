from __future__ import annotations

from pathlib import Path

from hermes_local_memory.consolidation import build_consolidation_plan, build_maintenance_plan
from hermes_local_memory.store import LocalMemoryStore


def test_maintenance_does_not_append_active_facts_to_existing_cards(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=[
            "Name: Alice",
            "Prefers local-first, auditable memory.",
        ],
    )
    store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers local-first memory.",
        kind="preference",
        status="active",
        source="manual",
    )

    plan = build_maintenance_plan(
        store,
        promote_candidates=True,
        apply=True,
    )

    assert plan["counts"]["card_additions"] == 0
    assert plan["writes"]["cards_replaced"] == 0
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "Prefers local-first, auditable memory.",
    ]


def test_maintenance_repairs_empty_cards_from_high_confidence_active_facts(
    tmp_path: Path,
) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("andra", display_name="Andra", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.add_fact(
        subject_peer_id="andra",
        observer_peer_id="bob",
        content="Andra is Simone's wife.",
        kind="relation",
        status="active",
        source="conversation",
        confidence=1.0,
    )
    store.add_fact(
        subject_peer_id="andra",
        observer_peer_id="bob",
        content=(
            "Andra and Simone are expecting a newborn with planned delivery date "
            "June 16, 2026."
        ),
        kind="personal",
        status="active",
        source="conversation",
        confidence=1.0,
    )

    plan = build_consolidation_plan(
        store,
        subject_peer_id="andra",
        observer_peer_id="bob",
        promote_candidates=True,
        apply=False,
    )

    assert plan["mode"] == "dry-run"
    assert plan["counts"]["card_additions"] == 3
    assert plan["card_additions"][0] == "Name: Andra"
    assert set(plan["card_additions"][1:]) == {
        "Andra is Simone's wife.",
        "Andra and Simone are expecting a newborn with planned delivery date June 16, 2026.",
    }
    assert store.get_card(subject_peer_id="andra", observer_peer_id="bob") == []

    applied = build_consolidation_plan(
        store,
        subject_peer_id="andra",
        observer_peer_id="bob",
        promote_candidates=True,
        apply=True,
    )

    assert applied["writes"]["card_replaced"] is True
    card = store.get_card(subject_peer_id="andra", observer_peer_id="bob")
    assert card[0] == "Name: Andra"
    assert set(card[1:]) == {
        "Andra is Simone's wife.",
        "Andra and Simone are expecting a newborn with planned delivery date June 16, 2026.",
    }


def test_imported_honcho_candidates_are_not_bulk_promoted(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    imported = store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Bob said the latest commit is abc123 and CI is green.",
        kind="conclusion",
        status="candidate",
        source="honcho-api-conclusion",
        confidence=0.7,
    )

    plan = build_consolidation_plan(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        promote_candidates=True,
        apply=True,
    )

    assert plan["counts"]["candidate_promotions"] == 0
    assert plan["counts"]["card_additions"] == 0
    assert store.get_fact(imported["id"])["status"] == "candidate"


def test_high_confidence_local_candidates_can_be_promoted(tmp_path: Path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    local = store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers local-first memory.",
        kind="preference",
        status="candidate",
        source="reflection",
        confidence=0.95,
    )

    plan = build_consolidation_plan(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        promote_candidates=True,
        apply=True,
    )

    assert plan["counts"]["candidate_promotions"] == 1
    assert [item["id"] for item in plan["candidate_promotions"]] == [local["id"]]
    assert store.get_fact(local["id"])["status"] == "active"


def _store_with_candidates(tmp_path: Path) -> tuple[LocalMemoryStore, dict[str, str]]:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=["Name: Alice", "Alice lives in Example District."],
    )
    active = store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers lean memory.",
        kind="preference",
        status="active",
    )
    duplicate_card = store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice lives in Example District",
        kind="personal",
        status="candidate",
    )
    duplicate_fact = store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers lean memory",
        kind="preference",
        status="candidate",
    )
    unique = store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers local-first memory.",
        kind="preference",
        status="candidate",
    )
    return store, {
        "active": active["id"],
        "duplicate_card": duplicate_card["id"],
        "duplicate_fact": duplicate_fact["id"],
        "unique": unique["id"],
    }


def test_consolidation_plan_is_preview_only_by_default(tmp_path: Path) -> None:
    store, ids = _store_with_candidates(tmp_path)

    plan = build_consolidation_plan(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        promote_candidates=True,
        apply=False,
    )

    assert plan["mode"] == "dry-run"
    assert plan["counts"] == {
        "current_card_items": 2,
        "active_facts": 1,
        "candidate_facts": 3,
        "candidate_promotions": 1,
        "candidate_supersedes": 2,
        "card_additions": 1,
    }
    assert [item["id"] for item in plan["candidate_promotions"]] == [ids["unique"]]
    assert {item["id"] for item in plan["candidate_supersedes"]} == {
        ids["duplicate_card"],
        ids["duplicate_fact"],
    }
    assert plan["card_additions"] == [
        "Alice prefers local-first memory.",
    ]

    assert store.get_fact(ids["unique"])["status"] == "candidate"
    assert store.get_fact(ids["duplicate_card"])["status"] == "candidate"
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "Alice lives in Example District.",
    ]


def test_consolidation_apply_promotes_candidates_supersedes_duplicates_and_updates_card(
    tmp_path: Path,
) -> None:
    store, ids = _store_with_candidates(tmp_path)

    plan = build_consolidation_plan(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        promote_candidates=True,
        apply=True,
    )

    assert plan["mode"] == "apply"
    assert plan["writes"] == {
        "candidate_promotions": 1,
        "candidate_supersedes": 2,
        "card_replaced": True,
    }
    assert store.get_fact(ids["unique"])["status"] == "active"
    assert store.get_fact(ids["duplicate_card"])["status"] == "superseded"
    assert store.get_fact(ids["duplicate_fact"])["status"] == "superseded"
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "Alice lives in Example District.",
        "Alice prefers local-first memory.",
    ]


def test_consolidation_without_candidate_promotion_leaves_card_unchanged(
    tmp_path: Path,
) -> None:
    store, ids = _store_with_candidates(tmp_path)

    plan = build_consolidation_plan(
        store,
        subject_peer_id="alice",
        observer_peer_id="bob",
        promote_candidates=False,
        apply=True,
    )

    assert plan["counts"]["candidate_promotions"] == 0
    assert plan["counts"]["card_additions"] == 0
    assert store.get_fact(ids["unique"])["status"] == "candidate"
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "Alice lives in Example District.",
    ]
