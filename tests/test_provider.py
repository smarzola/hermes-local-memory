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
        user_id="151011988",
        agent_identity="Ambrogio",
        session_title="Chat With Simone",
    )
    return provider


def parse_tool_result(result: str) -> dict:
    parsed = json.loads(result)
    assert parsed["success"] is True
    return parsed


def test_provider_initializes_profile_scoped_database_and_identity_alias(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    assert provider.is_available()
    assert provider.db_path == tmp_path / "memory" / "local_memory.sqlite"

    peer = provider.store.resolve_peer("telegram:151011988")
    assert peer is not None
    assert peer["id"] == "telegram-151011988"


def test_provider_exposes_memory_tools_and_can_write_profile_card(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}
    assert tool_names == {
        "memory_profile",
        "memory_search",
        "memory_context",
        "memory_conclude",
    }

    write_result = parse_tool_result(
        provider.handle_tool_call(
            "memory_profile",
            {"card": ["Name: Simone", "Lives in Kungsholmen, Stockholm"]},
        )
    )
    assert write_result["card"] == ["Name: Simone", "Lives in Kungsholmen, Stockholm"]

    read_result = parse_tool_result(provider.handle_tool_call("memory_profile", {}))
    assert read_result["card"] == ["Name: Simone", "Lives in Kungsholmen, Stockholm"]


def test_provider_syncs_turn_and_concludes_searchable_fact(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    provider.sync_turn(
        "Remember that I prefer memory migrations that preserve history.",
        "Got it.",
    )
    conclude_result = parse_tool_result(
        provider.handle_tool_call(
            "memory_conclude",
            {
                "content": "Simone prefers memory migrations that preserve existing history.",
                "kind": "preference",
            },
        )
    )
    assert conclude_result["fact"]["content"].endswith("existing history.")

    search_result = parse_tool_result(
        provider.handle_tool_call("memory_search", {"query": "migration preserve history"})
    )

    assert search_result["results"]
    assert search_result["results"][0]["content"] == conclude_result["fact"]["content"]


def test_provider_context_injection_is_source_labeled(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    provider.handle_tool_call(
        "memory_conclude",
        {
            "content": "Simone wants local memory context to be inspectable.",
            "kind": "preference",
        },
    )

    injected = provider.prefetch("inspectable memory", session_id="session-1")
    context_result = parse_tool_result(
        provider.handle_tool_call("memory_context", {"query": "inspectable memory"})
    )

    assert "# Local Memory" in injected
    assert "inspectable" in injected
    assert "source=manual" in injected
    assert context_result["context"] == injected
