from __future__ import annotations

import re
from typing import Any

from hermes_local_memory.store import LocalMemoryStore

PATCH_SCHEMA = "hermes-local-memory.consolidation-patch.v1"


def build_consolidation_plan(
    store: LocalMemoryStore,
    *,
    subject_peer_id: str,
    observer_peer_id: str,
    promote_candidates: bool = False,
    apply: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    """Preview or apply deterministic local memory consolidation.

    MVP consolidation is deliberately boring: it merges active facts into the
    compact card, optionally promotes non-duplicate candidate facts, and marks
    duplicate candidates as superseded. It does not call an LLM or delete rows.
    """

    current_card = store.get_card(
        subject_peer_id=subject_peer_id,
        observer_peer_id=observer_peer_id,
    )
    active_facts = store.list_facts(
        peer_id=subject_peer_id,
        observer_peer_id=observer_peer_id,
        status="active",
        limit=limit,
    )
    candidate_facts = store.list_facts(
        peer_id=subject_peer_id,
        observer_peer_id=observer_peer_id,
        status="candidate",
        limit=limit,
    )

    card_norms = {_normalize_line(item) for item in current_card}
    active_norms = {_normalize_line(fact["content"]) for fact in active_facts}
    known_norms = card_norms | active_norms

    candidate_promotions = []
    candidate_supersedes = []
    for fact in candidate_facts:
        norm = _normalize_line(fact["content"])
        if norm in known_norms:
            candidate_supersedes.append(_fact_ref(fact, reason="duplicate"))
            continue
        if promote_candidates:
            candidate_promotions.append(_fact_ref(fact, reason="promote_candidate"))
            known_norms.add(norm)

    card_additions = []
    card_addition_norms = set(card_norms)
    for fact in active_facts:
        norm = _normalize_line(fact["content"])
        if norm not in card_addition_norms:
            card_additions.append(fact["content"])
            card_addition_norms.add(norm)
    if promote_candidates:
        promoted_ids = {item["id"] for item in candidate_promotions}
        for fact in candidate_facts:
            norm = _normalize_line(fact["content"])
            if fact["id"] in promoted_ids and norm not in card_addition_norms:
                card_additions.append(fact["content"])
                card_addition_norms.add(norm)

    proposed_card = [*current_card, *card_additions]
    writes = {
        "candidate_promotions": 0,
        "candidate_supersedes": 0,
        "card_replaced": False,
    }
    if apply:
        for item in candidate_promotions:
            store.update_fact_status(item["id"], "active")
            writes["candidate_promotions"] += 1
        for item in candidate_supersedes:
            store.update_fact_status(item["id"], "superseded")
            writes["candidate_supersedes"] += 1
        if proposed_card != current_card:
            store.set_card(
                subject_peer_id=subject_peer_id,
                observer_peer_id=observer_peer_id,
                items=proposed_card,
            )
            writes["card_replaced"] = True

    return {
        "mode": "apply" if apply else "dry-run",
        "subject_peer_id": subject_peer_id,
        "observer_peer_id": observer_peer_id,
        "promote_candidates": promote_candidates,
        "counts": {
            "current_card_items": len(current_card),
            "active_facts": len(active_facts),
            "candidate_facts": len(candidate_facts),
            "candidate_promotions": len(candidate_promotions),
            "candidate_supersedes": len(candidate_supersedes),
            "card_additions": len(card_additions),
        },
        "candidate_promotions": candidate_promotions,
        "candidate_supersedes": candidate_supersedes,
        "card_additions": card_additions,
        "proposed_card": proposed_card,
        "writes": writes if apply else [],
    }


def build_consolidation_packet(
    store: LocalMemoryStore,
    *,
    subject_peer_id: str,
    observer_peer_id: str,
    max_candidates: int = 100,
    max_active: int = 100,
) -> dict[str, Any]:
    """Build a source-labeled packet for Hermes Agent review."""

    return {
        "schema": "hermes-local-memory.consolidation-packet.v1",
        "subject_peer_id": subject_peer_id,
        "observer_peer_id": observer_peer_id,
        "current_card": store.get_card(
            subject_peer_id=subject_peer_id,
            observer_peer_id=observer_peer_id,
        ),
        "active_facts": store.list_facts(
            peer_id=subject_peer_id,
            observer_peer_id=observer_peer_id,
            status="active",
            limit=max_active,
        ),
        "candidate_facts": store.list_facts(
            peer_id=subject_peer_id,
            observer_peer_id=observer_peer_id,
            status="candidate",
            limit=max_candidates,
        ),
        "known_aliases": _aliases_for_peer(store, subject_peer_id),
        "rules": {
            "patch_schema": PATCH_SCHEMA,
            "preserve_raw_history": True,
            "do_not_infer_without_evidence": True,
            "keep_card_compact": True,
        },
    }


def validate_consolidation_patch(
    store: LocalMemoryStore,
    patch: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    subject = str(patch.get("subject_peer_id") or "")
    observer = str(patch.get("observer_peer_id") or "")
    if not subject:
        errors.append("subject_peer_id is required")
    if not observer:
        errors.append("observer_peer_id is required")

    card = patch.get("card_replace")
    if card is not None:
        if not isinstance(card, list) or not all(isinstance(item, str) for item in card):
            errors.append("card_replace must be a list of strings")
        elif len({_normalize_line(item) for item in card}) != len(card):
            errors.append("card_replace contains duplicate items")

    for key in ["promote_fact_ids", "retract_fact_ids"]:
        value = patch.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{key} must be a list of fact id strings")
            continue
        for fact_id in value:
            _validate_fact_id(store, fact_id, subject, observer, errors)

    supersedes = patch.get("supersede_fact_ids", [])
    if not isinstance(supersedes, list):
        errors.append("supersede_fact_ids must be a list")
    else:
        for item in supersedes:
            fact_id = item.get("id") if isinstance(item, dict) else item
            if not isinstance(fact_id, str):
                errors.append("supersede_fact_ids items must be strings or objects with id")
                continue
            _validate_fact_id(store, fact_id, subject, observer, errors)

    new_facts = patch.get("new_facts", [])
    if not isinstance(new_facts, list):
        errors.append("new_facts must be a list")
    else:
        for index, fact in enumerate(new_facts):
            if not isinstance(fact, dict):
                errors.append(f"new_facts[{index}] must be an object")
                continue
            if not str(fact.get("content") or "").strip():
                errors.append(f"new_facts[{index}].content is required")

    return {"valid": not errors, "errors": errors}


def apply_consolidation_patch(
    store: LocalMemoryStore,
    patch: dict[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    validation = validate_consolidation_patch(store, patch)
    writes = {
        "card_replaced": False,
        "facts_promoted": 0,
        "facts_superseded": 0,
        "facts_retracted": 0,
        "facts_added": 0,
    }
    if not validation["valid"] or not apply:
        return {
            "mode": "apply" if apply else "dry-run",
            "validation": validation,
            "writes": writes if apply and validation["valid"] else [],
            "patch": patch,
        }

    subject = patch["subject_peer_id"]
    observer = patch["observer_peer_id"]
    if "card_replace" in patch:
        store.set_card(
            subject_peer_id=subject,
            observer_peer_id=observer,
            items=list(patch["card_replace"]),
        )
        writes["card_replaced"] = True

    for fact_id in patch.get("promote_fact_ids", []):
        store.update_fact_status(fact_id, "active")
        writes["facts_promoted"] += 1
    for item in patch.get("supersede_fact_ids", []):
        fact_id = item["id"] if isinstance(item, dict) else item
        store.update_fact_status(fact_id, "superseded")
        writes["facts_superseded"] += 1
    for fact_id in patch.get("retract_fact_ids", []):
        store.update_fact_status(fact_id, "retracted")
        writes["facts_retracted"] += 1
    for fact in patch.get("new_facts", []):
        store.add_fact(
            subject_peer_id=subject,
            observer_peer_id=observer,
            content=str(fact["content"]),
            kind=str(fact.get("kind") or "note"),
            source=str(fact.get("source") or "agent-consolidation"),
            status=str(fact.get("status") or "active"),
        )
        writes["facts_added"] += 1

    return {
        "mode": "apply",
        "validation": validation,
        "writes": writes,
        "patch": patch,
    }


def _validate_fact_id(
    store: LocalMemoryStore,
    fact_id: str,
    subject: str,
    observer: str,
    errors: list[str],
) -> None:
    fact = store.get_fact(fact_id)
    if fact is None:
        errors.append(f"unknown fact id: {fact_id}")
        return
    if subject and fact["subject_peer_id"] != subject:
        errors.append(f"fact {fact_id} subject mismatch")
    if observer and fact["observer_peer_id"] != observer:
        errors.append(f"fact {fact_id} observer mismatch")


def _aliases_for_peer(store: LocalMemoryStore, peer_id: str) -> list[str]:
    return [row["alias"] for row in store.list_aliases() if row["peer_id"] == peer_id]


def _fact_ref(fact: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "id": fact["id"],
        "content": fact["content"],
        "kind": fact.get("kind"),
        "source": fact.get("source"),
        "reason": reason,
    }


def _normalize_line(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"^preference:\s*", "", value)
    value = re.sub(r"[^\w\s]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()
