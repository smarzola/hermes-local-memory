from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory.cli import main
from hermes_local_memory.store import LocalMemoryStore


def seed_store(db_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(db_path)
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_alias("telegram:1001", peer_id="alice", source="telegram", verified=True)
    store.upsert_session(
        "telegram-dm-1001",
        profile_id="default",
        platform="telegram",
        external_id="1001",
        title="Telegram DM with Alice",
    )
    store.add_message(
        session_id="telegram-dm-1001",
        peer_id="alice",
        role="user",
        content="Please remember that context must be inspectable.",
    )
    store.add_message(
        session_id="telegram-dm-1001",
        peer_id="bob",
        role="assistant",
        content="Recorded.",
    )
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=["Name: Alice", "PREFERENCE: wants inspectable context"],
    )
    return store


def run_cli(args: list[str], capsys) -> str:  # noqa: ANN001
    assert main(args) == 0
    return capsys.readouterr().out


def test_cli_lists_cards_as_json(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    output = run_cli(
        ["--db", str(db_path), "cards", "--peer", "telegram:1001", "--json"],
        capsys,
    )
    rows = json.loads(output)

    assert len(rows) == 1
    assert rows[0]["subject_peer_id"] == "alice"
    assert rows[0]["observer_peer_id"] == "bob"
    assert rows[0]["items"] == ["Name: Alice", "PREFERENCE: wants inspectable context"]


def test_cli_lists_recent_messages_for_session(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    output = run_cli(
        [
            "--db",
            str(db_path),
            "messages",
            "--session",
            "telegram-dm-1001",
            "--json",
        ],
        capsys,
    )
    rows = json.loads(output)

    assert [row["role"] for row in rows] == ["user", "assistant"]
    assert rows[0]["peer_id"] == "alice"
    assert rows[0]["content"] == "Please remember that context must be inspectable."


def test_cli_message_text_output_is_human_readable(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    output = run_cli(["--db", str(db_path), "messages", "--peer", "alice"], capsys)

    assert "role=user" in output
    assert "peer_id=alice" in output
    assert "context must be inspectable" in output
