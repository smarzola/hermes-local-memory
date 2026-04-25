from __future__ import annotations

from typing import Any

from hermes_local_memory.candidate_review import (
    apply_candidate_review_patch,
    build_candidate_review_packet,
    validate_candidate_review_patch,
)
from hermes_local_memory.card_review import (
    apply_card_review_patch,
    build_card_review_packet,
    validate_card_review_patch,
)
from hermes_local_memory.store import LocalMemoryStore

HONCHO_MIGRATION_REVIEW_PACKET_SCHEMA = "hermes-local-memory.honcho-migration-review-packet.v1"
HONCHO_MIGRATION_REVIEW_PATCH_SCHEMA = "hermes-local-memory.honcho-migration-review-patch.v1"
DEFAULT_HONCHO_SOURCE = "honcho-api-conclusion"


def build_honcho_migration_review_packet(
    store: LocalMemoryStore,
    *,
    subject_peer_id: str,
    observer_peer_id: str,
    source: str = DEFAULT_HONCHO_SOURCE,
    max_candidates: int = 100,
    max_active: int = 50,
) -> dict[str, Any]:
    """Build a first-migration packet for reviewing imported Honcho memories.

    Honcho conclusions are imported as candidates because bulk deterministic
    promotion is unsafe. First migration is different from ordinary maintenance:
    an agent should actively inspect high-signal Honcho candidates and use them
    to rebuild the compact card through explicit review patches.
    """

    candidate_packet = build_candidate_review_packet(
        store,
        subject_peer_id=subject_peer_id,
        observer_peer_id=observer_peer_id,
        source=source,
        limit=max_candidates,
    )
    card_packet = build_card_review_packet(
        store,
        subject_peer_id=subject_peer_id,
        observer_peer_id=observer_peer_id,
        max_active=max_active,
        max_candidates=max_candidates,
    )
    candidate_packet["rules"]["review_high_signal_imports"] = True
    candidate_packet["rules"]["honcho_imports_are_first_migration_material"] = True
    card_packet["rules"]["use_honcho_candidates_for_first_migration"] = True
    card_packet["rules"]["candidate_promotions_should_precede_card_rebuild"] = True
    return {
        "schema": HONCHO_MIGRATION_REVIEW_PACKET_SCHEMA,
        "subject_peer_id": subject_peer_id,
        "observer_peer_id": observer_peer_id,
        "source_filter": source,
        "candidate_review_packet": candidate_packet,
        "card_review_packet": card_packet,
        "rules": {
            "patch_schema": HONCHO_MIGRATION_REVIEW_PATCH_SCHEMA,
            "first_migration_step": True,
            "review_honcho_candidates_instead_of_ignoring_them": True,
            "do_not_bulk_promote_imported_candidates": True,
            "promote_only_high_signal_stable_facts": True,
            "retract_or_leave_noisy_candidates": True,
            "rebuild_card_from_selected_imported_memories": True,
            "preserve_raw_history": True,
        },
    }


def validate_honcho_migration_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if patch.get("schema") not in (None, HONCHO_MIGRATION_REVIEW_PATCH_SCHEMA):
        errors.append(f"schema must be {HONCHO_MIGRATION_REVIEW_PATCH_SCHEMA}")
    if patch.get("subject_peer_id") != packet.get("subject_peer_id"):
        errors.append("subject_peer_id must match honcho migration review packet")
    if patch.get("observer_peer_id") != packet.get("observer_peer_id"):
        errors.append("observer_peer_id must match honcho migration review packet")

    candidate_patch = patch.get("candidate_patch")
    if not isinstance(candidate_patch, dict):
        errors.append("candidate_patch must be an object")
    else:
        candidate_validation = validate_candidate_review_patch(
            store,
            packet["candidate_review_packet"],
            candidate_patch,
        )
        errors.extend(f"candidate_patch: {error}" for error in candidate_validation["errors"])

    card_patch = patch.get("card_patch")
    if not isinstance(card_patch, dict):
        errors.append("card_patch must be an object")
    else:
        card_validation = validate_card_review_patch(
            store,
            packet["card_review_packet"],
            card_patch,
        )
        errors.extend(f"card_patch: {error}" for error in card_validation["errors"])

    return {"valid": not errors, "errors": errors}


def apply_honcho_migration_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    validation = validate_honcho_migration_review_patch(store, packet, patch)
    writes = {
        "facts_promoted": 0,
        "facts_superseded": 0,
        "facts_retracted": 0,
        "card_replaced": False,
    }
    if apply and validation["valid"]:
        candidate_result = apply_candidate_review_patch(
            store,
            packet["candidate_review_packet"],
            patch["candidate_patch"],
            apply=True,
        )
        card_result = apply_card_review_patch(
            store,
            packet["card_review_packet"],
            patch["card_patch"],
            apply=True,
        )
        candidate_writes = candidate_result.get("writes") or {}
        card_writes = card_result.get("writes") or {}
        writes = {
            "facts_promoted": int(candidate_writes.get("facts_promoted", 0)),
            "facts_superseded": int(candidate_writes.get("facts_superseded", 0)),
            "facts_retracted": int(candidate_writes.get("facts_retracted", 0)),
            "card_replaced": bool(card_writes.get("card_replaced", False)),
        }

    return {
        "mode": "apply" if apply else "dry-run",
        "schema": HONCHO_MIGRATION_REVIEW_PATCH_SCHEMA,
        "validation": validation,
        "writes": writes if apply and validation["valid"] else [],
    }
