from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory import LocalMemoryProvider


def make_provider(tmp_path: Path) -> LocalMemoryProvider:
    provider = LocalMemoryProvider()
    provider.initialize(
        "session-1",
        hermes_home=str(tmp_path),
        platform="telegram",
        user_id="1001",
        agent_identity="bob",
        session_title="Chat With Alice",
    )
    return provider


def parse_tool_result(result: str) -> dict:
    parsed = json.loads(result)
    assert parsed["success"] is True
    return parsed


def test_provider_exposes_patch_validation_tools_for_full_agent_maintenance_cycle(
    tmp_path: Path,
) -> None:
    provider = make_provider(tmp_path)
    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert "memory_apply_reflection_patch" in tool_names
    assert "memory_apply_peer_review_patch" in tool_names
    assert "memory_build_candidate_review_packet" in tool_names
    assert "memory_apply_candidate_review_patch" in tool_names
    assert "memory_build_card_review_packet" in tool_names
    assert "memory_apply_card_review_patch" in tool_names


def test_provider_can_apply_reflection_patch_from_agent_tools(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    provider.sync_turn("I prefer memory maintenance to be auditable.", "Understood.")

    reflection = parse_tool_result(
        provider.handle_tool_call(
            "memory_build_reflection_packets",
            {"min_messages": 1, "max_messages": 20},
        )
    )
    packet = reflection["plan"]["packets"][0]
    message_id = packet["message_window"][0]["id"]
    patch = {
        "schema": "hermes-local-memory.reflection-patch.v1",
        "session_id": "session-1",
        "observer_peer_id": provider.assistant_peer_id,
        "new_candidate_facts": [
            {
                "subject_peer_id": provider.user_peer_id,
                "kind": "preference",
                "content": "Alice prefers auditable memory maintenance.",
                "confidence": 0.95,
                "evidence_message_ids": [message_id],
            }
        ],
        "session_summary": {
            "content": "Alice discussed auditable memory maintenance.",
            "covered_from_message_id": message_id,
            "covered_to_message_id": message_id,
            "model": "hermes-agent",
        },
    }

    dry_run = parse_tool_result(
        provider.handle_tool_call(
            "memory_apply_reflection_patch",
            {"packet": packet, "patch": patch, "apply": False},
        )
    )
    assert dry_run["result"]["validation"]["valid"] is True
    assert dry_run["result"]["writes"] == []

    applied = parse_tool_result(
        provider.handle_tool_call(
            "memory_apply_reflection_patch",
            {"packet": packet, "patch": patch, "apply": True},
        )
    )
    assert applied["result"]["writes"] == {"candidate_facts_added": 1, "summaries_added": 1}
    candidates = provider.store.list_facts(
        peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        status="candidate",
    )
    assert candidates[0]["content"] == "Alice prefers auditable memory maintenance."


def test_provider_can_review_candidates_and_cards_from_agent_tools(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    provider.handle_tool_call("memory_profile", {"action": "set", "card": ["Name: Alice"]})
    candidate = provider.store.add_fact(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        content="Alice prefers compact cards.",
        kind="preference",
        source="agent-reflection",
        status="candidate",
        confidence=0.95,
    )

    packet_result = parse_tool_result(
        provider.handle_tool_call("memory_build_candidate_review_packet", {"limit": 10})
    )
    assert packet_result["packet"]["schema"] == "hermes-local-memory.candidate-review-packet.v1"
    patch = {
        "schema": "hermes-local-memory.candidate-review-patch.v1",
        "subject_peer_id": provider.user_peer_id,
        "observer_peer_id": provider.assistant_peer_id,
        "promote_fact_ids": [candidate["id"]],
        "card_additions": ["Preference: compact cards"],
    }
    applied = parse_tool_result(
        provider.handle_tool_call(
            "memory_apply_candidate_review_patch",
            {"packet": packet_result["packet"], "patch": patch, "apply": True},
        )
    )
    assert applied["result"]["writes"]["facts_promoted"] == 1
    assert provider.store.get_fact(candidate["id"])["status"] == "active"

    card_packet = parse_tool_result(
        provider.handle_tool_call("memory_build_card_review_packet", {})
    )["packet"]
    card_patch = {
        "schema": "hermes-local-memory.card-review-patch.v1",
        "subject_peer_id": provider.user_peer_id,
        "observer_peer_id": provider.assistant_peer_id,
        "card_replace": ["Name: Alice", "Preference: compact cards"],
    }
    card_applied = parse_tool_result(
        provider.handle_tool_call(
            "memory_apply_card_review_patch",
            {"packet": card_packet, "patch": card_patch, "apply": True},
        )
    )
    assert card_applied["result"]["writes"]["card_replaced"] is True
    assert provider.store.get_card(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
    ) == ["Name: Alice", "Preference: compact cards"]
