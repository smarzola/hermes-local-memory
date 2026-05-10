from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory import LocalMemoryProvider

EXAMPLE_USER_ID = "1001"
EXAMPLE_AGENT_IDENTITY = "bob"


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


def parse_tool_result(result: str) -> dict:
    parsed = json.loads(result)
    assert parsed["success"] is True
    return parsed


def test_provider_initializes_profile_scoped_database_and_identity_alias(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    assert provider.is_available()
    provider.shutdown()
    assert provider.db_path == tmp_path / "memory" / "local_memory.sqlite"

    peer = provider.store.resolve_peer("telegram:1001")
    assert peer is not None
    assert peer["id"] == "telegram-1001"


def test_provider_reuses_existing_verified_alias_instead_of_overwriting_it(tmp_path: Path) -> None:
    db_path = tmp_path / "memory" / "local_memory.sqlite"
    seeded = LocalMemoryProvider(db_path=db_path)
    seeded.initialize(
        "migration-session",
        hermes_home=str(tmp_path),
        platform="migration",
        user_id="seed",
        agent_identity="bob",
    )
    assert seeded.store is not None
    seeded.store.upsert_peer("alice", display_name="Alice", kind="human")
    seeded.store.set_alias(
        "telegram:1001",
        peer_id="alice",
        source="migration",
        verified=True,
    )

    provider = make_provider(tmp_path)

    assert provider.user_peer_id == "alice"
    peer = provider.store.resolve_peer("telegram:1001")
    assert peer is not None
    assert peer["id"] == "alice"
    assert provider.store.resolve_peer("telegram-1001") is None


def test_provider_adopts_existing_sanitized_runtime_peer_when_alias_now_resolves_elsewhere(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory" / "local_memory.sqlite"
    seeded = LocalMemoryProvider(db_path=db_path)
    seeded.initialize(
        "first-runtime-session",
        hermes_home=str(tmp_path),
        platform="telegram",
        user_id="default",
        agent_identity="bob",
    )
    assert seeded.store is not None
    seeded.store.upsert_peer("alice", display_name="Alice", kind="human")
    message = seeded.store.add_message(
        session_id="first-runtime-session",
        peer_id="telegram-default",
        role="user",
        content="runtime message before identity repair",
    )
    seeded.store.set_alias(
        "telegram:default",
        peer_id="alice",
        source="migration",
        verified=True,
    )

    provider = LocalMemoryProvider(db_path=db_path)
    provider.initialize(
        "second-runtime-session",
        hermes_home=str(tmp_path),
        platform="telegram",
        user_id="default",
        agent_identity="bob",
    )

    assert provider.user_peer_id == "alice"
    assert provider.store.resolve_peer("telegram:default")["id"] == "alice"
    assert provider.store.resolve_peer("telegram-default")["id"] == "alice"
    with provider.store.connect() as conn:
        retired_alias = conn.execute(
            "select * from peer_aliases where alias = ?",
            ("telegram-default",),
        ).fetchone()
        retired_peer = conn.execute(
            "select * from peers where id = ?",
            ("telegram-default",),
        ).fetchone()
        repaired_message = conn.execute(
            "select peer_id from messages where id = ?",
            (message["id"],),
        ).fetchone()
        repaired_session_peer = conn.execute(
            "select peer_id from session_peers where session_id = ? and peer_id = ?",
            ("first-runtime-session", "alice"),
        ).fetchone()
    assert retired_alias["peer_id"] == "alice"
    assert retired_alias["verified"] == 1
    assert retired_peer is None
    assert repaired_message["peer_id"] == "alice"
    assert repaired_session_peer["peer_id"] == "alice"


def test_provider_reuses_existing_agent_identity_alias_instead_of_creating_default_peer(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory" / "local_memory.sqlite"
    seeded = LocalMemoryProvider(db_path=db_path)
    seeded.initialize(
        "migration-session",
        hermes_home=str(tmp_path),
        platform="migration",
        user_id="seed",
        agent_identity="bob",
    )
    assert seeded.store is not None
    seeded.store.upsert_peer("bob", display_name="Bob", kind="ai")
    seeded.store.set_alias("default", peer_id="bob", source="profile", verified=True)

    provider = LocalMemoryProvider(db_path=db_path)
    provider.initialize(
        "session-1",
        hermes_home=str(tmp_path),
        platform="telegram",
        user_id=EXAMPLE_USER_ID,
        agent_identity="default",
    )

    assert provider.assistant_peer_id == "bob"
    peer = provider.store.resolve_peer("default")
    assert peer is not None
    assert peer["id"] == "bob"
    assert provider.store.resolve_peer("ai")["id"] == "bob"


def test_provider_exposes_memory_tools_and_can_write_profile_card(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)

    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}
    assert tool_names == {
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

    legacy_write = json.loads(
        provider.handle_tool_call(
            "memory_profile",
            {"card": ["Name: Alice", "Prefers local-first memory"]},
        )
    )
    assert legacy_write["success"] is False
    assert "action='set'" in legacy_write["error"]

    write_result = parse_tool_result(
        provider.handle_tool_call(
            "memory_profile",
            {"action": "set", "card": ["Name: Alice", "Prefers local-first memory"]},
        )
    )
    assert write_result["card"] == ["Name: Alice", "Prefers local-first memory"]
    assert write_result["diff"] == {
        "before": [],
        "after": ["Name: Alice", "Prefers local-first memory"],
        "added": ["Name: Alice", "Prefers local-first memory"],
        "removed": [],
    }

    empty_write = json.loads(
        provider.handle_tool_call("memory_profile", {"action": "set", "card": []})
    )
    assert empty_write["success"] is False
    assert "allow_empty=true" in empty_write["error"]

    read_result = parse_tool_result(provider.handle_tool_call("memory_profile", {}))
    assert read_result["card"] == ["Name: Alice", "Prefers local-first memory"]


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
                "content": "Alice prefers memory migrations that preserve existing history.",
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
            "content": "Alice wants local memory context to be inspectable.",
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
        "memory_set_card",
        {"card": ["Name: Alice"]},
    )
    store = provider.store
    assert store is not None
    candidate = store.add_fact(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        content="Alice prefers consolidation to be inspectable.",
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
    assert "Alice prefers consolidation to be inspectable." in store.get_card(
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
    )


def test_provider_exposes_peer_review_tool(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    store = provider.store
    assert store is not None
    store.upsert_peer("telegram-1002", display_name="Telegram 1002", kind="human")
    store.set_alias("telegram:1002", peer_id="telegram-1002", source="telegram")

    result = parse_tool_result(provider.handle_tool_call("memory_peer_review", {}))

    assert result["packet"]["schema"] == "hermes-local-memory.peer-review-packet.v1"
    assert any(peer["id"] == "telegram-1002" for peer in result["packet"]["unverified_peers"])


def test_provider_exposes_all_pairs_and_reflection_maintenance_tools(tmp_path: Path) -> None:
    provider = make_provider(tmp_path)
    provider.sync_turn("I prefer memory to grow from ordinary conversation.", "Understood.")
    store = provider.store
    assert store is not None
    store.add_fact(
        fact_id="candidate_from_reflection",
        subject_peer_id=provider.user_peer_id,
        observer_peer_id=provider.assistant_peer_id,
        content="Alice prefers natural memory growth.",
        kind="preference",
        status="candidate",
        source="reflection",
        confidence=0.95,
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
