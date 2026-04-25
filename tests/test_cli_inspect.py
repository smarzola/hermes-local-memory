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
    msg = store.add_message(
        session_id="telegram-dm-1001",
        peer_id="alice",
        role="user",
        content="I prefer inspectable local memory.",
    )
    store.add_fact(
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers inspectable local memory.",
        kind="preference",
        evidence_message_ids=[msg["id"]],
    )
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=["Name: Alice"],
    )
    return store


def run_cli(args: list[str], capsys) -> str:  # noqa: ANN001
    assert main(args) == 0
    return capsys.readouterr().out


def test_cli_lists_peers_as_json(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    output = run_cli(["--db", str(db_path), "peers", "--json"], capsys)
    rows = json.loads(output)

    assert {row["id"] for row in rows} == {"alice", "bob"}
    display_names_by_id = {row["id"]: row["display_name"] for row in rows}
    assert display_names_by_id == {"alice": "Alice", "bob": "Bob"}


def test_cli_lists_aliases_and_sessions(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    aliases = json.loads(run_cli(["--db", str(db_path), "aliases", "--json"], capsys))
    sessions = json.loads(run_cli(["--db", str(db_path), "sessions", "--json"], capsys))

    assert aliases == [
        {
            "alias": "telegram:1001",
            "peer_id": "alice",
            "source": "telegram",
            "confidence": 1.0,
            "verified": 1,
            "created_at": aliases[0]["created_at"],
        }
    ]
    assert sessions[0]["id"] == "telegram-dm-1001"
    assert sessions[0]["title"] == "Telegram DM with Alice"


def test_cli_lists_facts_for_peer_alias(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    output = run_cli(
        ["--db", str(db_path), "facts", "--peer", "telegram:1001", "--json"],
        capsys,
    )
    rows = json.loads(output)

    assert len(rows) == 1
    assert rows[0]["subject_peer_id"] == "alice"
    assert rows[0]["evidence_message_ids"] == [1]


def test_cli_searches_and_builds_context(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    search_output = run_cli(
        ["--db", str(db_path), "search", "inspectable memory", "--peer", "alice"],
        capsys,
    )
    context_output = run_cli(
        [
            "--db",
            str(db_path),
            "context",
            "--peer",
            "alice",
            "--observer",
            "bob",
            "--query",
            "inspectable memory",
        ],
        capsys,
    )

    assert "Alice prefers inspectable local memory." in search_output
    assert "# Local Memory" in context_output
    assert "## Compact peer card" in context_output
    assert "Name: Alice" in context_output
    assert "source=manual" in context_output
