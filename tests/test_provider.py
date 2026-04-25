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
        "memory_consolidate",
        "memory_maintenance",
        "memory_reflection_maintenance",
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


def test_provider_consolidate_previews_and_applies_candidate_promotion(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    provider.handle_tool_call(
        "memory_profile",
        {"card": ["Name: Simone"]},
    )
    store = provider.store
    assert store is not None
    candidate = store.add_fact(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        content="Simone prefers consolidation to be inspectable.",
        kind="preference",
        status="candidate",
    )

    preview = parse_tool_result(
        provider.handle_tool_call(
            "memory_consolidate",
            {"promote_candidates": True},
        )
    )
    assert preview["plan"]["mode"] == "dry-run"
    assert preview["plan"]["counts"]["candidate_promotions"] == 1
    assert store.get_fact(candidate["id"])["status"] == "candidate"

    applied = parse_tool_result(
        provider.handle_tool_call(
            "memory_consolidate",
            {"promote_candidates": True, "apply": True},
        )
    )
    assert applied["plan"]["mode"] == "apply"
    assert store.get_fact(candidate["id"])["status"] == "active"
    assert "Simone prefers consolidation to be inspectable." in store.get_card(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
    )


def test_provider_exposes_all_pairs_and_reflection_maintenance_tools(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    provider.sync_turn("I prefer memory to grow from ordinary conversation.", "Understood.")
    store = provider.store
    assert store is not None
    store.add_fact(
        fact_id="candidate_from_reflection",
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        content="Simone prefers natural memory growth.",
        kind="preference",
        status="candidate",
    )

    reflection = parse_tool_result(
        provider.handle_tool_call(
            "memory_reflection_maintenance",
            {"min_messages": 1, "max_messages": 20},
        )
    )
    assert reflection["plan"]["schema"] == "hermes-local-memory.reflection-maintenance-plan.v1"
    assert reflection["plan"]["counts"]["packets"] == 1

    maintenance = parse_tool_result(
        provider.handle_tool_call(
            "memory_maintenance",
            {"promote_candidates": True},
        )
    )
    assert maintenance["plan"]["mode"] == "dry-run"
    assert maintenance["plan"]["counts"]["pairs"] == 1
    assert maintenance["plan"]["counts"]["candidate_promotions"] == 1
