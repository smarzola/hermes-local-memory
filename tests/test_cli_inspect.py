from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory.cli import main
from hermes_local_memory.store import LocalMemoryStore


def seed_store(db_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(db_path)
    store.initialize()
    store.upsert_peer("simone", display_name="Simone", kind="human")
    store.upsert_peer("ambrogio", display_name="Ambrogio", kind="ai")
    store.set_alias("telegram:151011988", peer_id="simone", source="telegram", verified=True)
    store.upsert_session(
        "telegram-dm-151011988",
        profile_id="default",
        platform="telegram",
        external_id="151011988",
        title="Telegram DM with Simone",
    )
    msg = store.add_message(
        session_id="telegram-dm-151011988",
        peer_id="simone",
        role="user",
        content="I prefer inspectable local memory.",
    )
    store.add_fact(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        content="Simone prefers inspectable local memory.",
        kind="preference",
        evidence_message_ids=[msg["id"]],
    )
    store.set_card(
        subject_peer_id="simone",
        observer_peer_id="ambrogio",
        items=["Name: Simone"],
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

    assert {row["id"] for row in rows} == {"simone", "ambrogio"}
    assert rows[0]["display_name"] == "Ambrogio"


def test_cli_lists_aliases_and_sessions(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    aliases = json.loads(run_cli(["--db", str(db_path), "aliases", "--json"], capsys))
    sessions = json.loads(run_cli(["--db", str(db_path), "sessions", "--json"], capsys))

    assert aliases == [
        {
            "alias": "telegram:151011988",
            "peer_id": "simone",
            "source": "telegram",
            "confidence": 1.0,
            "verified": 1,
            "created_at": aliases[0]["created_at"],
        }
    ]
    assert sessions[0]["id"] == "telegram-dm-151011988"
    assert sessions[0]["title"] == "Telegram DM with Simone"


def test_cli_lists_facts_for_peer_alias(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    output = run_cli(
        ["--db", str(db_path), "facts", "--peer", "telegram:151011988", "--json"],
        capsys,
    )
    rows = json.loads(output)

    assert len(rows) == 1
    assert rows[0]["subject_peer_id"] == "simone"
    assert rows[0]["evidence_message_ids"] == [1]


def test_cli_searches_and_builds_context(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    search_output = run_cli(
        ["--db", str(db_path), "search", "inspectable memory", "--peer", "simone"],
        capsys,
    )
    context_output = run_cli(
        [
            "--db",
            str(db_path),
            "context",
            "--peer",
            "simone",
            "--observer",
            "ambrogio",
            "--query",
            "inspectable memory",
        ],
        capsys,
    )

    assert "Simone prefers inspectable local memory." in search_output
    assert "# Local Memory" in context_output
    assert "## Peer card" in context_output
    assert "Name: Simone" in context_output
    assert "source=manual" in context_output
