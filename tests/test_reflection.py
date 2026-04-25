from __future__ import annotations

from pathlib import Path

from hermes_local_memory.reflection import (
    apply_reflection_patch,
    build_reflection_maintenance_plan,
    build_reflection_packet,
    validate_reflection_patch,
)
from hermes_local_memory.store import LocalMemoryStore


def _reflection_store(tmp_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.upsert_peer("carol", display_name="Carol", kind="human")
    store.set_card(subject_peer_id="alice", observer_peer_id="bob", items=["Name: Alice"])
    store.upsert_session(
        "dm-alice",
        platform="chat",
        external_id="1001",
        title="DM with Alice",
    )
    store.add_message(
        session_id="dm-alice",
        peer_id="alice",
        role="user",
        content="I prefer local-first memory.",
    )
    store.add_message(
        session_id="dm-alice",
        peer_id="bob",
        role="assistant",
        content="Got it.",
    )
    store.add_message(
        session_id="dm-alice",
        peer_id="alice",
        role="user",
        content="Please preserve raw history during migrations.",
    )
    store.add_fact(
        fact_id="fact_existing",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers inspectable systems.",
        kind="preference",
        status="active",
    )
    return store


def test_build_reflection_packet_contains_unreflected_message_window(tmp_path: Path) -> None:
    store = _reflection_store(tmp_path)

    packet = build_reflection_packet(
        store,
        session_id="dm-alice",
        observer_peer_id="bob",
        since_message_id=0,
        max_messages=10,
    )

    assert packet["schema"] == "hermes-local-memory.reflection-packet.v1"
    assert packet["session"]["id"] == "dm-alice"
    assert [message["content"] for message in packet["message_window"]] == [
        "I prefer local-first memory.",
        "Got it.",
        "Please preserve raw history during migrations.",
    ]
    assert {peer["peer_id"] for peer in packet["participants"]} == {"alice", "bob"}
    assert packet["current_cards"] == {"alice": ["Name: Alice"]}
    assert packet["existing_facts"]["alice"][0]["id"] == "fact_existing"
    assert packet["rules"]["patch_schema"] == "hermes-local-memory.reflection-patch.v1"
    assert packet["rules"]["create_candidates_not_active_facts"] is True


def test_validate_reflection_patch_rejects_evidence_outside_packet_window(tmp_path: Path) -> None:
    store = _reflection_store(tmp_path)
    packet = build_reflection_packet(
        store,
        session_id="dm-alice",
        observer_peer_id="bob",
        since_message_id=0,
        max_messages=2,
    )
    patch = {
        "schema": "hermes-local-memory.reflection-patch.v1",
        "session_id": "dm-alice",
        "observer_peer_id": "bob",
        "new_candidate_facts": [
            {
                "subject_peer_id": "alice",
                "kind": "preference",
                "content": "Alice prefers local-first memory.",
                "confidence": 0.9,
                "evidence_message_ids": [9999],
            }
        ],
    }

    result = validate_reflection_patch(store, packet, patch)

    assert result["valid"] is False
    expected = (
        "new_candidate_facts[0].evidence_message_ids contains "
        "id outside packet window: 9999"
    )
    assert expected in result["errors"]


def test_apply_reflection_patch_dry_run_and_apply(tmp_path: Path) -> None:
    store = _reflection_store(tmp_path)
    packet = build_reflection_packet(
        store,
        session_id="dm-alice",
        observer_peer_id="bob",
        since_message_id=0,
        max_messages=10,
    )
    first_id = packet["message_window"][0]["id"]
    last_id = packet["message_window"][-1]["id"]
    candidate_content = (
        "Alice prefers local-first memory and raw-history-preserving migrations."
    )
    summary_content = (
        "Alice discussed local-first memory and preserving raw history during migrations."
    )
    patch = {
        "schema": "hermes-local-memory.reflection-patch.v1",
        "session_id": "dm-alice",
        "observer_peer_id": "bob",
        "new_candidate_facts": [
            {
                "subject_peer_id": "alice",
                "kind": "preference",
                "content": candidate_content,
                "confidence": 0.92,
                "evidence_message_ids": [first_id, last_id],
            }
        ],
        "session_summary": {
            "content": summary_content,
            "covered_from_message_id": first_id,
            "covered_to_message_id": last_id,
            "model": "hermes-agent",
        },
    }

    dry_run = apply_reflection_patch(store, packet, patch, apply=False)

    assert dry_run["mode"] == "dry-run"
    assert dry_run["validation"]["valid"] is True
    assert dry_run["writes"] == []
    assert store.list_facts(peer_id="alice", observer_peer_id="bob", status="candidate") == []
    assert store.list_summaries(scope="session", scope_id="dm-alice") == []

    applied = apply_reflection_patch(store, packet, patch, apply=True)

    assert applied["mode"] == "apply"
    assert applied["writes"] == {"candidate_facts_added": 1, "summaries_added": 1}
    candidates = store.list_facts(peer_id="alice", observer_peer_id="bob", status="candidate")
    assert candidates[0]["content"] == candidate_content
    assert candidates[0]["source"] == "agent-reflection"
    summaries = store.list_summaries(scope="session", scope_id="dm-alice")
    assert summaries[0]["covered_to_message_id"] == last_id


def test_reflection_maintenance_discovers_stale_sessions(tmp_path: Path) -> None:
    store = _reflection_store(tmp_path)

    plan = build_reflection_maintenance_plan(
        store,
        observer_peer_id="bob",
        min_messages=2,
        max_messages=10,
    )

    assert plan["schema"] == "hermes-local-memory.reflection-maintenance-plan.v1"
    assert plan["counts"] == {"sessions": 1, "packets": 1, "unreflected_messages": 3}
    assert plan["packets"][0]["session"]["id"] == "dm-alice"

    last_id = plan["packets"][0]["message_window"][-1]["id"]
    store.add_summary(
        scope="session",
        scope_id="dm-alice",
        content="Already reflected.",
        covered_from_message_id=1,
        covered_to_message_id=last_id,
        model="test",
    )

    after_summary = build_reflection_maintenance_plan(
        store,
        observer_peer_id="bob",
        min_messages=2,
        max_messages=10,
    )
    assert after_summary["counts"] == {"sessions": 1, "packets": 0, "unreflected_messages": 0}
