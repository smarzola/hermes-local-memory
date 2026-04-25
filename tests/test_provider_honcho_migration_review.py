from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory import LocalMemoryProvider


def _provider_with_honcho_candidates(tmp_path: Path) -> LocalMemoryProvider:
    provider = LocalMemoryProvider()
    provider.initialize(
        "session-1",
        hermes_home=str(tmp_path),
        platform="telegram",
        user_id="1001",
        agent_identity="bob",
    )
    provider.store.set_card(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        items=["Name: Alice", "Old short imported card"],
    )
    provider.store.add_fact(
        fact_id="honcho_high_signal",
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        content="Alice prefers local-first, auditable memory systems.",
        kind="preference",
        source="honcho-api-conclusion",
        status="candidate",
        confidence=0.95,
    )
    provider.store.add_fact(
        fact_id="honcho_noisy",
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        content="Alice had a transient debugging task last Tuesday.",
        kind="note",
        source="honcho-api-conclusion",
        status="candidate",
        confidence=0.5,
    )
    return provider


def _parse(result: str) -> dict:
    parsed = json.loads(result)
    assert parsed["success"] is True
    return parsed


def test_provider_honcho_migration_review_uses_imported_candidates_for_card_rebuild(
    tmp_path: Path,
) -> None:
    provider = _provider_with_honcho_candidates(tmp_path)
    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert "memory_build_honcho_migration_review_packet" in tool_names
    assert "memory_apply_honcho_migration_review_patch" in tool_names

    packet_result = _parse(
        provider.handle_tool_call("memory_build_honcho_migration_review_packet", {})
    )
    packet = packet_result["packet"]
    assert packet["schema"] == "hermes-local-memory.honcho-migration-review-packet.v1"
    assert packet["rules"]["review_honcho_candidates_instead_of_ignoring_them"] is True

    patch = {
        "schema": "hermes-local-memory.honcho-migration-review-patch.v1",
        "subject_peer_id": provider.user_peer_id,
        "observer_peer_id": provider.assistant_peer_id,
        "candidate_patch": {
            "schema": "hermes-local-memory.candidate-review-patch.v1",
            "subject_peer_id": provider.user_peer_id,
            "observer_peer_id": provider.assistant_peer_id,
            "promote_fact_ids": ["honcho_high_signal"],
            "retract_fact_ids": ["honcho_noisy"],
        },
        "card_patch": {
            "schema": "hermes-local-memory.card-review-patch.v1",
            "subject_peer_id": provider.user_peer_id,
            "observer_peer_id": provider.assistant_peer_id,
            "card_replace": [
                "Name: Alice",
                "Prefers local-first, auditable memory systems",
            ],
        },
    }

    dry_run = _parse(
        provider.handle_tool_call(
            "memory_apply_honcho_migration_review_patch",
            {"packet": packet, "patch": patch, "apply": False},
        )
    )
    assert dry_run["result"]["validation"]["valid"] is True
    assert provider.store.get_fact("honcho_high_signal")["status"] == "candidate"

    applied = _parse(
        provider.handle_tool_call(
            "memory_apply_honcho_migration_review_patch",
            {"packet": packet, "patch": patch, "apply": True},
        )
    )
    assert applied["result"]["writes"] == {
        "facts_promoted": 1,
        "facts_superseded": 0,
        "facts_retracted": 1,
        "card_replaced": True,
    }
    assert provider.store.get_fact("honcho_high_signal")["status"] == "active"
    assert provider.store.get_card(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
    ) == ["Name: Alice", "Prefers local-first, auditable memory systems"]
