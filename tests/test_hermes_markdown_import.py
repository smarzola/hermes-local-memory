from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory.cli import main
from hermes_local_memory.hermes_markdown_import import (
    apply_hermes_markdown_import_plan,
    plan_hermes_markdown_import,
)
from hermes_local_memory.store import LocalMemoryStore


def write_markdown_memories(root: Path) -> Path:
    memories = root / "memories"
    memories.mkdir()
    (memories / "USER.md").write_text(
        "Alice prefers local-first memory systems.\n"
        "§\n"
        "Alice prefers dry-run migrations before live switches.\n",
        encoding="utf-8",
    )
    (memories / "MEMORY.md").write_text(
        "Project uses pytest and ruff.\n"
        "§\n"
        "Radarr skill lives under the media skills directory.\n",
        encoding="utf-8",
    )
    return memories


def test_plan_hermes_markdown_import_reads_user_and_memory_entries(tmp_path: Path) -> None:
    source_dir = write_markdown_memories(tmp_path)
    target_db = tmp_path / "local.sqlite"

    plan = plan_hermes_markdown_import(
        source_dir,
        target_db=target_db,
        user_peer_id="alice",
        assistant_peer_id="bob",
    )

    assert plan["mode"] == "dry-run"
    assert plan["source"]["kind"] == "hermes-markdown"
    assert plan["source"]["path"] == str(source_dir)
    assert plan["target"]["db_path"] == str(target_db)
    assert plan["counts"] == {
        "peers": 2,
        "aliases": 2,
        "sessions": 1,
        "session_peers": 2,
        "messages": 0,
        "cards": 2,
        "facts": 4,
    }
    assert plan["writes"] == []
    assert not target_db.exists()
    assert plan["cards"] == [
        {
            "subject_peer_id": "alice",
            "observer_peer_id": "bob",
            "scope": "global",
            "scope_id": "",
            "items": [
                "Alice prefers local-first memory systems.",
                "Alice prefers dry-run migrations before live switches.",
            ],
        },
        {
            "subject_peer_id": "bob",
            "observer_peer_id": "bob",
            "scope": "global",
            "scope_id": "",
            "items": [
                "Project uses pytest and ruff.",
                "Radarr skill lives under the media skills directory.",
            ],
        },
    ]
    assert {fact["kind"] for fact in plan["facts"]} == {"user_profile", "agent_memory"}
    assert {fact["status"] for fact in plan["facts"]} == {"active"}
    assert {fact["source"] for fact in plan["facts"]} == {"hermes-markdown"}


def test_apply_hermes_markdown_import_plan_is_idempotent_and_active(tmp_path: Path) -> None:
    source_dir = write_markdown_memories(tmp_path)
    target_db = tmp_path / "local.sqlite"
    plan = plan_hermes_markdown_import(
        source_dir,
        target_db=target_db,
        user_peer_id="alice",
        assistant_peer_id="bob",
    )

    first = apply_hermes_markdown_import_plan(plan, backup=True)
    second = apply_hermes_markdown_import_plan(plan, backup=True)

    assert first["mode"] == "apply"
    assert first["backup_path"] is None
    assert first["writes"] == {
        "peers_upserted": 2,
        "aliases_upserted": 2,
        "sessions_upserted": 1,
        "session_peers_upserted": 2,
        "messages_inserted": 0,
        "messages_skipped_existing": 0,
        "cards_upserted": 2,
        "facts_inserted": 4,
        "facts_skipped_existing": 0,
    }
    assert second["writes"]["facts_inserted"] == 0
    assert second["writes"]["facts_skipped_existing"] == 4
    assert second["backup_path"] is not None

    store = LocalMemoryStore(target_db)
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Alice prefers local-first memory systems.",
        "Alice prefers dry-run migrations before live switches.",
    ]
    facts = store.list_facts(peer_id="alice", observer_peer_id="bob", status="active")
    assert {fact["content"] for fact in facts} == {
        "Alice prefers dry-run migrations before live switches.",
        "Alice prefers local-first memory systems.",
    }


def test_hermes_markdown_import_cli_dry_run_and_apply(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    source_dir = write_markdown_memories(tmp_path)
    target_db = tmp_path / "local.sqlite"

    dry_exit = main(
        [
            "--db",
            str(target_db),
            "import",
            "hermes-markdown",
            "--source-dir",
            str(source_dir),
            "--user-peer",
            "alice",
            "--assistant-peer",
            "bob",
            "--dry-run",
            "--json",
        ]
    )
    assert dry_exit == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["mode"] == "dry-run"
    assert dry["counts"]["facts"] == 4
    assert not target_db.exists()

    apply_exit = main(
        [
            "--db",
            str(target_db),
            "import",
            "hermes-markdown",
            "--source-dir",
            str(source_dir),
            "--user-peer",
            "alice",
            "--assistant-peer",
            "bob",
            "--apply",
            "--json",
        ]
    )
    assert apply_exit == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["mode"] == "apply"
    assert applied["writes"]["facts_inserted"] == 4
    assert target_db.exists()
