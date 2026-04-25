from __future__ import annotations

from typing import Any

from hermes_local_memory.store import LocalMemoryStore

CANDIDATE_REVIEW_PACKET_SCHEMA = "hermes-local-memory.candidate-review-packet.v1"
CANDIDATE_REVIEW_PATCH_SCHEMA = "hermes-local-memory.candidate-review-patch.v1"


def build_candidate_review_packet(
    store: LocalMemoryStore,
    *,
    subject_peer_id: str,
    observer_peer_id: str,
    source: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    candidates = _candidate_facts(
        store,
        subject_peer_id=subject_peer_id,
        observer_peer_id=observer_peer_id,
        source=source,
        limit=limit,
    )
    return {
        "schema": CANDIDATE_REVIEW_PACKET_SCHEMA,
        "subject_peer_id": subject_peer_id,
        "observer_peer_id": observer_peer_id,
        "source_filter": source,
        "current_card": store.get_card(
            subject_peer_id=subject_peer_id,
            observer_peer_id=observer_peer_id,
        ),
        "active_facts": store.list_facts(
            peer_id=subject_peer_id,
            observer_peer_id=observer_peer_id,
            status="active",
            limit=50,
        ),
        "candidate_facts": candidates,
        "rules": {
            "patch_schema": CANDIDATE_REVIEW_PATCH_SCHEMA,
            "preserve_raw_history": True,
            "prefer_promoting_high_signal_preferences": True,
            "do_not_bulk_promote_imported_candidates": True,
            "prefer_superseding_duplicates_over_deleting": True,
            "card_additions_should_be_compact": True,
        },
    }


def validate_candidate_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if patch.get("schema") not in (None, CANDIDATE_REVIEW_PATCH_SCHEMA):
        errors.append(f"schema must be {CANDIDATE_REVIEW_PATCH_SCHEMA}")
    subject = str(patch.get("subject_peer_id") or "")
    observer = str(patch.get("observer_peer_id") or "")
    if subject != packet.get("subject_peer_id"):
        errors.append("subject_peer_id must match candidate review packet")
    if observer != packet.get("observer_peer_id"):
        errors.append("observer_peer_id must match candidate review packet")

    packet_ids = {fact["id"] for fact in packet.get("candidate_facts", [])}
    for key in ["promote_fact_ids", "retract_fact_ids"]:
        value = patch.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{key} must be a list of fact id strings")
            continue
        for fact_id in value:
            _validate_candidate_id(store, fact_id, packet_ids, errors)

    supersedes = patch.get("supersede_fact_ids", [])
    if not isinstance(supersedes, list):
        errors.append("supersede_fact_ids must be a list")
    else:
        for item in supersedes:
            fact_id = item.get("id") if isinstance(item, dict) else item
            if not isinstance(fact_id, str):
                errors.append("supersede_fact_ids items must be strings or objects with id")
                continue
            _validate_candidate_id(store, fact_id, packet_ids, errors)

    card_additions = patch.get("card_additions", [])
    if not isinstance(card_additions, list) or not all(
        isinstance(item, str) for item in card_additions
    ):
        errors.append("card_additions must be a list of strings")
    elif len({_normalize_line(item) for item in card_additions}) != len(card_additions):
        errors.append("card_additions contains duplicate items")

    actions = []
    actions.extend(patch.get("promote_fact_ids", []))
    actions.extend(patch.get("retract_fact_ids", []))
    actions.extend(
        item.get("id") if isinstance(item, dict) else item
        for item in patch.get("supersede_fact_ids", [])
    )
    action_ids = [item for item in actions if isinstance(item, str)]
    if len(set(action_ids)) != len(action_ids):
        errors.append("a fact id can only appear in one action")

    return {"valid": not errors, "errors": errors}


def apply_candidate_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    validation = validate_candidate_review_patch(store, packet, patch)
    writes = {
        "facts_promoted": 0,
        "facts_superseded": 0,
        "facts_retracted": 0,
        "card_replaced": False,
    }
    if apply and validation["valid"]:
        for fact_id in patch.get("promote_fact_ids", []):
            store.update_fact_status(fact_id, "active")
            writes["facts_promoted"] += 1
        for item in patch.get("supersede_fact_ids", []):
            fact_id = item.get("id") if isinstance(item, dict) else item
            store.update_fact_status(fact_id, "superseded")
            writes["facts_superseded"] += 1
        for fact_id in patch.get("retract_fact_ids", []):
            store.update_fact_status(fact_id, "retracted")
            writes["facts_retracted"] += 1
        additions = patch.get("card_additions", [])
        if additions:
            card = list(packet.get("current_card", []))
            known = {_normalize_line(item) for item in card}
            for item in additions:
                norm = _normalize_line(item)
                if norm not in known:
                    card.append(item)
                    known.add(norm)
            store.set_card(
                subject_peer_id=patch["subject_peer_id"],
                observer_peer_id=patch["observer_peer_id"],
                items=card,
            )
            writes["card_replaced"] = True

    return {
        "mode": "apply" if apply else "dry-run",
        "schema": CANDIDATE_REVIEW_PATCH_SCHEMA,
        "validation": validation,
        "writes": writes if apply and validation["valid"] else [],
    }


def _candidate_facts(
    store: LocalMemoryStore,
    *,
    subject_peer_id: str,
    observer_peer_id: str,
    source: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["subject_peer_id = ?", "observer_peer_id = ?", "status = 'candidate'"]
    params: list[Any] = [subject_peer_id, observer_peer_id]
    if source:
        clauses.append("source = ?")
        params.append(source)
    params.append(limit)
    with store.connect() as conn:
        rows = conn.execute(
            f"""
            select * from facts
            where {' and '.join(clauses)}
            order by confidence desc, updated_at desc, created_at desc, id
            limit ?
            """,
            params,
        ).fetchall()
        return [store._hydrate_fact(row) for row in rows]  # noqa: SLF001


def _validate_candidate_id(
    store: LocalMemoryStore,
    fact_id: str,
    packet_ids: set[str],
    errors: list[str],
) -> None:
    if not store.fact_exists(fact_id):
        errors.append(f"unknown candidate fact id: {fact_id}")
        return
    if fact_id not in packet_ids:
        errors.append(f"fact id not present in candidate review packet: {fact_id}")
        return
    fact = store.get_fact(fact_id)
    if fact and fact.get("status") != "candidate":
        errors.append(f"fact id is not candidate status: {fact_id}")


def _normalize_line(value: str) -> str:
    return " ".join(value.casefold().split())
