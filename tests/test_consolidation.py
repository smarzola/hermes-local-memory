from __future__ import annotations

from pathlib import Path

from hermes_local_memory.consolidation import build_consolidation_plan
from hermes_local_memory.store import LocalMemoryStore


def _store_with_candidates(tmp_path: Path) -> tuple[LocalMemoryStore, dict[str, str]]:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("simone", display_name="Simone", kind="human")
    store.upsert_peer("ambrogio", display_name="Ambrogio", kind="ai")
    store.set_card(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        items=["Name: Simone", "Simone lives in Kungsholmen."],
    )
    active = store.add_fact(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        content="Simone prefers lean memory.",
        kind="preference",
        status="active",
    )
    duplicate_card = store.add_fact(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        content="Simone lives in Kungsholmen",
        kind="personal",
        status="candidate",
    )
    duplicate_fact = store.add_fact(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        content="Simone prefers lean memory",
        kind="preference",
        status="candidate",
    )
    unique = store.add_fact(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        content="Simone prefers local-first memory.",
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
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
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
        "card_additions": 2,
    }
    assert [item["id"] for item in plan["candidate_promotions"]] == [ids["unique"]]
    assert {item["id"] for item in plan["candidate_supersedes"]} == {
        ids["duplicate_card"],
        ids["duplicate_fact"],
    }
    assert plan["card_additions"] == [
        "Simone prefers lean memory.",
        "Simone prefers local-first memory.",
    ]

    assert store.get_fact(ids["unique"])["status"] == "candidate"
    assert store.get_fact(ids["duplicate_card"])["status"] == "candidate"
    assert store.get_card(subject_peer_id="simone", observer_peer_id="ambrogio") == [
        "Name: Simone",
        "Simone lives in Kungsholmen.",
    ]


def test_consolidation_apply_promotes_candidates_supersedes_duplicates_and_updates_card(
    tmp_path: Path,
) -> None:
    store, ids = _store_with_candidates(tmp_path)

    plan = build_consolidation_plan(
        store,
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
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
    assert store.get_card(subject_peer_id="simone", observer_peer_id="ambrogio") == [
        "Name: Simone",
        "Simone lives in Kungsholmen.",
        "Simone prefers lean memory.",
        "Simone prefers local-first memory.",
    ]


def test_consolidation_without_candidate_promotion_only_adds_active_facts_to_card(
    tmp_path: Path,
) -> None:
    store, ids = _store_with_candidates(tmp_path)

    plan = build_consolidation_plan(
        store,
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        promote_candidates=False,
        apply=True,
    )

    assert plan["counts"]["candidate_promotions"] == 0
    assert store.get_fact(ids["unique"])["status"] == "candidate"
    assert store.get_card(subject_peer_id="simone", observer_peer_id="ambrogio") == [
        "Name: Simone",
        "Simone lives in Kungsholmen.",
        "Simone prefers lean memory.",
    ]
