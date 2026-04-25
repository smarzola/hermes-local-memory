from __future__ import annotations

from pathlib import Path

from hermes_local_memory import LocalMemoryProvider

EXAMPLE_USER_ID = "1001"
EXAMPLE_AGENT_IDENTITY = "bob"


CANONICAL_TOOL_NAMES = {
    "memory_get_card",
    "memory_set_card",
    "memory_search",
    "memory_context",
    "memory_conclude",
    "memory_consolidate",
    "memory_maintenance",
    "memory_build_peer_review_packet",
    "memory_apply_peer_review_patch",
    "memory_build_reflection_packets",
    "memory_apply_reflection_patch",
    "memory_build_candidate_review_packet",
    "memory_apply_candidate_review_patch",
    "memory_build_card_review_packet",
    "memory_apply_card_review_patch",
    "memory_build_honcho_migration_review_packet",
    "memory_apply_honcho_migration_review_patch",
}


LEGACY_TOOL_ALIASES = {
    "memory_profile",
    "memory_peer_review",
    "memory_reflection_maintenance",
    "memory_candidate_review",
    "memory_card_review",
}


def make_provider(tmp_path: Path) -> LocalMemoryProvider:
    provider = LocalMemoryProvider()
    provider.initialize(
        "session-1",
        hermes_home=str(tmp_path),
        platform="telegram",
        user_id=EXAMPLE_USER_ID,
        agent_identity=EXAMPLE_AGENT_IDENTITY,
        session_title="Chat With Alice",
    )
    return provider


def test_provider_exposes_canonical_maintenance_tool_names(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert tool_names >= CANONICAL_TOOL_NAMES


def test_legacy_maintenance_tool_names_are_not_exposed_by_default(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert tool_names.isdisjoint(LEGACY_TOOL_ALIASES)


def test_legacy_tool_names_continue_to_work_as_hidden_compatibility_aliases(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    provider.handle_tool_call("memory_set_card", {"card": ["Name: Alice"]})
    legacy_card = provider.handle_tool_call("memory_profile", {})
    canonical_card = provider.handle_tool_call("memory_get_card", {})

    assert legacy_card == canonical_card

    assert provider.handle_tool_call("memory_peer_review", {}) == provider.handle_tool_call(
        "memory_build_peer_review_packet", {}
    )
    assert provider.handle_tool_call("memory_candidate_review", {}) == provider.handle_tool_call(
        "memory_build_candidate_review_packet", {}
    )
    assert provider.handle_tool_call("memory_card_review", {}) == provider.handle_tool_call(
        "memory_build_card_review_packet", {}
    )

    provider.sync_turn("I prefer durable memories with evidence.", "Noted.")
    assert provider.handle_tool_call(
        "memory_reflection_maintenance", {"min_messages": 1}
    ) == provider.handle_tool_call("memory_build_reflection_packets", {"min_messages": 1})
