from __future__ import annotations

from typing import Any

from hermes_local_memory.store import LocalMemoryStore

REFLECTION_PACKET_SCHEMA = "hermes-local-memory.reflection-packet.v1"
REFLECTION_PATCH_SCHEMA = "hermes-local-memory.reflection-patch.v1"
REFLECTION_MAINTENANCE_SCHEMA = "hermes-local-memory.reflection-maintenance-plan.v1"


def build_reflection_packet(
    store: LocalMemoryStore,
    *,
    session_id: str,
    observer_peer_id: str,
    since_message_id: int | None = None,
    max_messages: int = 100,
) -> dict[str, Any]:
    """Build an agent-review packet from raw, unreflected session messages.

    Reflection is the local, explicit replacement for opaque background
    "dreaming": Hermes Agent reviews this packet and returns a structured patch
    with candidate facts and summaries. Local Memory validates and applies it.
    """

    session = store.get_session(session_id)
    if session is None:
        raise KeyError(f"session not found: {session_id}")

    if since_message_id is None:
        since_message_id = (
            store.last_summary_to_message_id(scope="session", scope_id=session_id) or 0
        )

    messages = store.list_messages_after(
        session_id=session_id,
        after_message_id=since_message_id,
        limit=max_messages,
    )
    participants = store.list_session_participants(session_id)
    subject_ids = _subject_peer_ids(participants, messages, observer_peer_id)

    current_cards = {
        subject: store.get_card(subject_peer_id=subject, observer_peer_id=observer_peer_id)
        for subject in subject_ids
    }
    existing_facts = {
        subject: store.list_facts(
            peer_id=subject,
            observer_peer_id=observer_peer_id,
            status="active",
            limit=25,
        )
        for subject in subject_ids
    }

    return {
        "schema": REFLECTION_PACKET_SCHEMA,
        "session": session,
        "observer_peer_id": observer_peer_id,
        "since_message_id": since_message_id,
        "participants": participants,
        "message_window": messages,
        "current_cards": current_cards,
        "existing_facts": existing_facts,
        "rules": {
            "patch_schema": REFLECTION_PATCH_SCHEMA,
            "create_candidates_not_active_facts": True,
            "require_evidence_message_ids": True,
            "preserve_raw_history": True,
            "do_not_infer_private_sensitive_facts_without_explicit_evidence": True,
            "summaries_should_cover_only_packet_messages": True,
        },
    }


def build_reflection_maintenance_plan(
    store: LocalMemoryStore,
    *,
    observer_peer_id: str,
    min_messages: int = 20,
    max_messages: int = 100,
) -> dict[str, Any]:
    """Find stale sessions and build reflection packets for each.

    A session is stale when it has at least ``min_messages`` raw messages after
    the most recent session summary checkpoint.
    """

    sessions = store.list_sessions()
    packets = []
    unreflected_total = 0
    for session in sessions:
        last_reflected = store.last_summary_to_message_id(
            scope="session",
            scope_id=session["id"],
        ) or 0
        unreflected = store.count_messages_after(
            session_id=session["id"],
            after_message_id=last_reflected,
        )
        if unreflected < min_messages:
            continue
        unreflected_total += unreflected
        packets.append(
            build_reflection_packet(
                store,
                session_id=session["id"],
                observer_peer_id=observer_peer_id,
                since_message_id=last_reflected,
                max_messages=max_messages,
            )
        )

    return {
        "schema": REFLECTION_MAINTENANCE_SCHEMA,
        "observer_peer_id": observer_peer_id,
        "policy": {
            "min_messages": min_messages,
            "max_messages": max_messages,
            "run_before_consolidation": True,
        },
        "counts": {
            "sessions": len(sessions),
            "packets": len(packets),
            "unreflected_messages": unreflected_total,
        },
        "packets": packets,
    }


def validate_reflection_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if patch.get("schema") not in (None, REFLECTION_PATCH_SCHEMA):
        errors.append(f"schema must be {REFLECTION_PATCH_SCHEMA}")

    session_id = str(patch.get("session_id") or "")
    observer = str(patch.get("observer_peer_id") or "")
    if session_id != packet.get("session", {}).get("id"):
        errors.append("session_id must match reflection packet")
    if observer != packet.get("observer_peer_id"):
        errors.append("observer_peer_id must match reflection packet")

    packet_message_ids = {message["id"] for message in packet.get("message_window", [])}
    participant_ids = {participant["peer_id"] for participant in packet.get("participants", [])}
    message_peer_ids = {message["peer_id"] for message in packet.get("message_window", [])}
    known_subjects = (participant_ids | message_peer_ids) - {packet.get("observer_peer_id")}

    facts = patch.get("new_candidate_facts", [])
    if not isinstance(facts, list):
        errors.append("new_candidate_facts must be a list")
    else:
        for index, fact in enumerate(facts):
            if not isinstance(fact, dict):
                errors.append(f"new_candidate_facts[{index}] must be an object")
                continue
            subject = str(fact.get("subject_peer_id") or "")
            if not subject:
                errors.append(f"new_candidate_facts[{index}].subject_peer_id is required")
            elif subject not in known_subjects:
                errors.append(
                    f"new_candidate_facts[{index}].subject_peer_id is not in packet subjects"
                )
            if store.resolve_peer(subject) is None:
                errors.append(f"new_candidate_facts[{index}].subject_peer_id is unknown: {subject}")
            if not str(fact.get("content") or "").strip():
                errors.append(f"new_candidate_facts[{index}].content is required")
            evidence = fact.get("evidence_message_ids")
            if not isinstance(evidence, list) or not evidence or not all(
                isinstance(item, int) for item in evidence
            ):
                errors.append(
                    f"new_candidate_facts[{index}].evidence_message_ids must be "
                    "a non-empty list of integers"
                )
                continue
            for message_id in evidence:
                if message_id not in packet_message_ids:
                    errors.append(
                        f"new_candidate_facts[{index}].evidence_message_ids contains "
                        f"id outside packet window: {message_id}"
                    )
            confidence = fact.get("confidence", 1.0)
            if not isinstance(confidence, int | float) or confidence < 0 or confidence > 1:
                errors.append(f"new_candidate_facts[{index}].confidence must be between 0 and 1")

    summary = patch.get("session_summary")
    if summary is not None:
        if not isinstance(summary, dict):
            errors.append("session_summary must be an object")
        else:
            if not str(summary.get("content") or "").strip():
                errors.append("session_summary.content is required")
            for key in ["covered_from_message_id", "covered_to_message_id"]:
                value = summary.get(key)
                if not isinstance(value, int):
                    errors.append(f"session_summary.{key} must be an integer")
                elif value not in packet_message_ids:
                    errors.append(f"session_summary.{key} must be inside packet window")

    return {"valid": not errors, "errors": errors}


def apply_reflection_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    validation = validate_reflection_patch(store, packet, patch)
    writes = {"candidate_facts_added": 0, "summaries_added": 0}
    if apply and validation["valid"]:
        observer = patch["observer_peer_id"]
        for fact in patch.get("new_candidate_facts", []):
            store.add_fact(
                subject_peer_id=fact["subject_peer_id"],
                observer_peer_id=observer,
                content=fact["content"],
                kind=fact.get("kind", "note"),
                confidence=float(fact.get("confidence", 1.0)),
                status="candidate",
                source=fact.get("source", "agent-reflection"),
                evidence_message_ids=fact["evidence_message_ids"],
            )
            writes["candidate_facts_added"] += 1
        summary = patch.get("session_summary")
        if summary:
            store.add_summary(
                scope="session",
                scope_id=patch["session_id"],
                content=summary["content"],
                covered_from_message_id=summary["covered_from_message_id"],
                covered_to_message_id=summary["covered_to_message_id"],
                model=summary.get("model"),
            )
            writes["summaries_added"] += 1

    return {
        "mode": "apply" if apply else "dry-run",
        "schema": REFLECTION_PATCH_SCHEMA,
        "validation": validation,
        "writes": writes if apply and validation["valid"] else [],
    }


def _subject_peer_ids(
    participants: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    observer_peer_id: str,
) -> list[str]:
    ids = []
    seen = {observer_peer_id}
    for item in [*participants, *messages]:
        peer_id = item.get("peer_id")
        if peer_id and peer_id not in seen:
            ids.append(peer_id)
            seen.add(peer_id)
    return ids
