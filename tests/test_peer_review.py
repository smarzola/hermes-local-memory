from __future__ import annotations

from pathlib import Path

from hermes_local_memory.peer_review import (
    apply_peer_review_patch,
    build_peer_review_packet,
    validate_peer_review_patch,
)
from hermes_local_memory.store import LocalMemoryStore


def _peer_store(tmp_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(tmp_path / "memory.sqlite")
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.upsert_peer(
        "telegram-1001",
        display_name="Telegram 1001",
        kind="human",
        metadata={"source": "telegram", "external_id": "1001"},
    )
    store.set_alias("telegram:1001", peer_id="telegram-1001", source="telegram")
    store.set_alias("Alice", peer_id="alice", source="manual", verified=True)
    return store


def test_peer_review_packet_flags_unverified_peers_and_includes_candidates(tmp_path: Path) -> None:
    store = _peer_store(tmp_path)

    packet = build_peer_review_packet(store, limit=20)

    assert packet["schema"] == "hermes-local-memory.peer-review-packet.v1"
    assert packet["rules"]["patch_schema"] == "hermes-local-memory.peer-review-patch.v1"
    assert packet["rules"]["agent_controls_peer_mapping"] is True
    assert packet["rules"]["ask_human_when_ambiguous"] is True
    assert [peer["id"] for peer in packet["unverified_peers"]] == ["telegram-1001"]
    assert packet["unverified_peers"][0]["aliases"] == ["telegram:1001"]
    assert [peer["id"] for peer in packet["candidate_canonical_peers"]] == ["alice", "bob"]


def test_peer_review_patch_rejects_unknown_target_and_duplicate_alias_actions(
    tmp_path: Path,
) -> None:
    store = _peer_store(tmp_path)
    packet = build_peer_review_packet(store)
    patch = {
        "schema": "hermes-local-memory.peer-review-patch.v1",
        "alias_moves": [
            {"alias": "telegram:1001", "to_peer_id": "missing", "confidence": 0.9},
            {"alias": "telegram:1001", "to_peer_id": "alice", "confidence": 0.9},
        ],
    }

    result = validate_peer_review_patch(store, packet, patch)

    assert result["valid"] is False
    assert "unknown target peer id: missing" in result["errors"]
    assert "alias can only appear in one peer review action: telegram:1001" in result["errors"]


def test_peer_review_patch_dry_run_and_apply_alias_mapping(tmp_path: Path) -> None:
    store = _peer_store(tmp_path)
    packet = build_peer_review_packet(store)
    patch = {
        "schema": "hermes-local-memory.peer-review-patch.v1",
        "alias_moves": [
            {
                "alias": "telegram:1001",
                "to_peer_id": "alice",
                "source": "agent-peer-review",
                "confidence": 0.92,
                "verified": False,
                "reason": "Display name and conversation context suggest Alice.",
            }
        ],
        "human_prompts": [],
    }

    dry_run = apply_peer_review_patch(store, packet, patch, apply=False)

    assert dry_run["mode"] == "dry-run"
    assert dry_run["validation"]["valid"] is True
    assert dry_run["writes"] == []
    assert store.resolve_peer("telegram:1001")["id"] == "telegram-1001"

    applied = apply_peer_review_patch(store, packet, patch, apply=True)

    assert applied["mode"] == "apply"
    assert applied["writes"] == {"aliases_moved": 1, "human_prompts_recorded": 0}
    assert store.resolve_peer("telegram:1001")["id"] == "alice"
    alias = next(item for item in store.list_aliases() if item["alias"] == "telegram:1001")
    assert alias["source"] == "agent-peer-review"
    assert alias["confidence"] == 0.92
    assert alias["verified"] == 0


def test_peer_review_patch_accepts_human_prompt_for_ambiguous_peer(tmp_path: Path) -> None:
    store = _peer_store(tmp_path)
    packet = build_peer_review_packet(store)
    patch = {
        "schema": "hermes-local-memory.peer-review-patch.v1",
        "human_prompts": [
            {
                "peer_id": "telegram-1001",
                "question": "Who is Telegram user 1001?",
                "suggested_aliases": ["telegram:1001"],
            }
        ],
    }

    result = apply_peer_review_patch(store, packet, patch, apply=True)

    assert result["validation"]["valid"] is True
    assert result["writes"] == {"aliases_moved": 0, "human_prompts_recorded": 1}
    assert result["human_prompts"] == [
        {
            "peer_id": "telegram-1001",
            "question": "Who is Telegram user 1001?",
            "suggested_aliases": ["telegram:1001"],
        }
    ]
    assert store.resolve_peer("telegram:1001")["id"] == "telegram-1001"
