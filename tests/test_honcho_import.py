from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from hermes_local_memory.cli import main
from hermes_local_memory.honcho_import import plan_honcho_import


def create_honcho_fixture(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            create table peers (
              name text not null,
              workspace_name text not null,
              metadata text not null default '{}',
              internal_metadata text not null default '{}'
            );
            create table sessions (
              name text not null,
              workspace_name text not null,
              metadata text not null default '{}'
            );
            create table session_peers (
              session_name text not null,
              peer_name text not null,
              workspace_name text not null,
              left_at text
            );
            create table messages (
              id integer primary key,
              session_name text not null,
              peer_name text not null,
              workspace_name text not null,
              content text not null,
              created_at text not null,
              metadata text not null default '{}'
            );
            create table documents (
              id text primary key,
              workspace_name text not null,
              content text not null,
              metadata text not null default '{}'
            );
            """
        )
        conn.execute(
            """
            insert into peers(name, workspace_name, metadata, internal_metadata)
            values (?, ?, ?, ?)
            """,
            (
                "Ambrogio",
                "hermes",
                json.dumps({"kind": "ai"}),
                json.dumps({"151011988_peer_card": ["Simone prefers local-first memory."]}),
            ),
        )
        conn.execute(
            """
            insert into peers(name, workspace_name, metadata, internal_metadata)
            values (?, ?, ?, ?)
            """,
            (
                "151011988",
                "hermes",
                json.dumps({"telegram_user_id": "151011988"}),
                json.dumps({"peer_card": ["Name: Simone"]}),
            ),
        )
        conn.execute(
            "insert into sessions(name, workspace_name, metadata) values (?, ?, ?)",
            (
                "agent-main-telegram-dm-151011988",
                "hermes",
                json.dumps({"title": "Telegram DM with Simone"}),
            ),
        )
        conn.execute(
            """
            insert into session_peers(session_name, peer_name, workspace_name, left_at)
            values (?, ?, ?, null)
            """,
            ("agent-main-telegram-dm-151011988", "151011988", "hermes"),
        )
        conn.execute(
            """
            insert into session_peers(session_name, peer_name, workspace_name, left_at)
            values (?, ?, ?, null)
            """,
            ("agent-main-telegram-dm-151011988", "Ambrogio", "hermes"),
        )
        conn.execute(
            """
            insert into messages(
              id, session_name, peer_name, workspace_name, content, created_at, metadata
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "agent-main-telegram-dm-151011988",
                "151011988",
                "hermes",
                "Remember that I prefer local-first memory.",
                "2026-04-25T08:00:00Z",
                json.dumps({"source_message_id": "tg-1"}),
            ),
        )
        conn.execute(
            """
            insert into messages(
              id, session_name, peer_name, workspace_name, content, created_at, metadata
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                2,
                "agent-main-telegram-dm-151011988",
                "Ambrogio",
                "hermes",
                "Got it.",
                "2026-04-25T08:00:01Z",
                json.dumps({"source_message_id": "tg-2"}),
            ),
        )
        conn.execute(
            "insert into documents(id, workspace_name, content, metadata) values (?, ?, ?, ?)",
            (
                "doc-1",
                "hermes",
                "Simone strongly prefers seamless migrations.",
                json.dumps({
                    "observer": "Ambrogio",
                    "observed": "151011988",
                    "type": "observation",
                }),
            ),
        )


def test_plan_honcho_import_dry_run_counts_and_mappings(tmp_path: Path) -> None:
    honcho_db = tmp_path / "honcho.sqlite"
    target_db = tmp_path / "local.sqlite"
    create_honcho_fixture(honcho_db)

    plan = plan_honcho_import(honcho_db, target_db=target_db, workspace="hermes")

    assert plan["mode"] == "dry-run"
    assert plan["source"]["workspace"] == "hermes"
    assert plan["counts"] == {
        "peers": 2,
        "aliases": 2,
        "sessions": 1,
        "session_peers": 2,
        "messages": 2,
        "cards": 2,
        "facts": 1,
    }
    assert plan["writes"] == []
    assert not target_db.exists()
    assert {peer["id"] for peer in plan["peers"]} == {"honcho-151011988", "honcho-ambrogio"}
    assert {alias["alias"] for alias in plan["aliases"]} == {"honcho:151011988", "honcho:Ambrogio"}
    assert plan["sessions"][0]["id"] == "honcho-agent-main-telegram-dm-151011988"
    assert plan["messages"][0]["source_message_id"] == "honcho:1"
    assert plan["facts"][0]["status"] == "candidate"


def test_honcho_import_cli_dry_run_prints_json_without_writing(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    honcho_db = tmp_path / "honcho.sqlite"
    target_db = tmp_path / "local.sqlite"
    create_honcho_fixture(honcho_db)

    exit_code = main(
        [
            "--db",
            str(target_db),
            "import",
            "honcho",
            "--source-db",
            str(honcho_db),
            "--workspace",
            "hermes",
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "dry-run"
    assert output["counts"]["messages"] == 2
    assert output["target"]["db_path"] == str(target_db)
    assert not target_db.exists()
