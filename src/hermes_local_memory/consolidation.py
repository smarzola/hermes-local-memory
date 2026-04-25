from __future__ import annotations

import re
from typing import Any

from hermes_local_memory.store import LocalMemoryStore


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
