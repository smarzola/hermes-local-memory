from __future__ import annotations

from typing import Any

from hermes_local_memory.store import LocalMemoryStore

CARD_REVIEW_PACKET_SCHEMA = "hermes-local-memory.card-review-packet.v1"
CARD_REVIEW_PATCH_SCHEMA = "hermes-local-memory.card-review-patch.v1"


def build_card_review_packet(
    store: LocalMemoryStore,
    *,
    subject_peer_id: str,
    observer_peer_id: str,
    max_active: int = 50,
    max_candidates: int = 50,
) -> dict[str, Any]:
    """Build an agent-review packet for cleaning imported or noisy peer cards."""
    return {
        "schema": CARD_REVIEW_PACKET_SCHEMA,
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
        "rules": {
            "patch_schema": CARD_REVIEW_PATCH_SCHEMA,
            "migration_step": True,
            "preserve_raw_history": True,
            "card_replace_is_full_card": True,
            "keep_cards_compact": True,
            "remove_ephemeral_task_local_lines": True,
            "merge_duplicates": True,
            "facts_are_not_mutated_by_card_review": True,
        },
    }


def validate_card_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    del store
    errors: list[str] = []
    if patch.get("schema") not in (None, CARD_REVIEW_PATCH_SCHEMA):
        errors.append(f"schema must be {CARD_REVIEW_PATCH_SCHEMA}")
    if patch.get("subject_peer_id") != packet.get("subject_peer_id"):
        errors.append("subject_peer_id must match card review packet")
    if patch.get("observer_peer_id") != packet.get("observer_peer_id"):
        errors.append("observer_peer_id must match card review packet")

    replacement = patch.get("card_replace")
    if not isinstance(replacement, list):
        errors.append("card_replace must be a JSON list of strings")
    else:
        if not all(isinstance(item, str) and item.strip() for item in replacement):
            errors.append("card_replace items must be non-empty strings")
        normalized = [
            _normalize_line(item)
            for item in replacement
            if isinstance(item, str) and item.strip()
        ]
        if len(set(normalized)) != len(normalized):
            errors.append("card_replace contains duplicate normalized items")

    return {"valid": not errors, "errors": errors}


def apply_card_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    validation = validate_card_review_patch(store, packet, patch)
    replacement = patch.get("card_replace")
    writes = {
        "card_replaced": False,
        "before_count": len(packet.get("current_card", [])),
        "after_count": len(replacement) if isinstance(replacement, list) else 0,
    }
    if apply and validation["valid"]:
        store.set_card(
            subject_peer_id=patch["subject_peer_id"],
            observer_peer_id=patch["observer_peer_id"],
            items=patch["card_replace"],
        )
        writes["card_replaced"] = True

    return {
        "mode": "apply" if apply else "dry-run",
        "schema": CARD_REVIEW_PATCH_SCHEMA,
        "validation": validation,
        "writes": writes if apply and validation["valid"] else [],
    }


def _normalize_line(value: str) -> str:
    return " ".join(value.casefold().split())
