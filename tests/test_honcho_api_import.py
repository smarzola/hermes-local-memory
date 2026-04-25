from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hermes_local_memory.cli import main
from hermes_local_memory.honcho_api import HonchoApiClient, export_honcho_api
from hermes_local_memory.honcho_import import (
    apply_honcho_import_plan,
    load_identity_map,
    plan_honcho_export_import,
)
from hermes_local_memory.store import LocalMemoryStore


class FakeHonchoTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object] | None, dict[str, str]]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        self.requests.append((method, url, json_body, headers or {}))
        parsed = urlparse(url)
        path = parsed.path
        query = parse_qs(parsed.query)
        page = int(query.get("page", ["1"])[0])
        size = int(query.get("size", ["50"])[0])

        if path == "/v3/workspaces/hermes/peers/list":
            return _page(
                [
                    {"id": "Bob", "metadata": {"kind": "ai"}},
                    {"id": "1001", "metadata": {"telegram_user_id": "1001"}},
                    {"id": "user-default-20260419_182008_26ad7f", "metadata": {}},
                ],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/sessions/list":
            return _page(
                [
                    {
                        "id": "agent-main-telegram-dm-1001",
                        "metadata": {"title": "Telegram DM with Alice"},
                    }
                ],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/sessions/agent-main-telegram-dm-1001/peers":
            return _page(
                [{"id": "1001"}, {"id": "Bob"}],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/sessions/agent-main-telegram-dm-1001/messages/list":
            return _page(
                [
                    {
                        "id": "msg-user-1",
                        "session_id": "agent-main-telegram-dm-1001",
                        "peer_id": "1001",
                        "content": "Remember that I prefer local-first memory.",
                        "metadata": {"source_message_id": "tg-1"},
                        "created_at": "2026-04-25T08:00:00Z",
                    },
                    {
                        "id": "msg-ai-1",
                        "session_id": "agent-main-telegram-dm-1001",
                        "peer_id": "Bob",
                        "content": "Got it.",
                        "metadata": {"source_message_id": "tg-2"},
                        "created_at": "2026-04-25T08:00:01Z",
                    },
                ],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/peers/Bob/card":
            if query.get("target") == ["1001"]:
                return {"peer_card": ["Alice prefers local-first memory."]}
            if "target" in query:
                return {"peer_card": None}
            return {"peer_card": ["Assistant name: Bob"]}
        if path == "/v3/workspaces/hermes/peers/1001/card":
            if "target" in query:
                return {"peer_card": None}
            return {"peer_card": ["Name: Alice"]}
        if path == "/v3/workspaces/hermes/peers/user-default-20260419_182008_26ad7f/card":
            return {"peer_card": None}
        if path == "/v3/workspaces/hermes/conclusions/list":
            return _page(
                [
                    {
                        "id": "conclusion-1",
                        "content": "Alice strongly prefers seamless migrations.",
                        "observer_id": "Bob",
                        "observed_id": "1001",
                        "session_id": None,
                        "created_at": "2026-04-25T08:01:00Z",
                    }
                ],
                page=page,
                size=size,
            )
        raise AssertionError(f"Unexpected request: {method} {url}")


def _page(items: list[dict[str, object]], *, page: int, size: int) -> dict[str, object]:
    start = (page - 1) * size
    end = start + size
    sliced = items[start:end]
    pages = 1 if items else 0
    return {"items": sliced, "page": page, "size": size, "pages": pages, "total": len(items)}


def test_honcho_api_export_uses_public_endpoints_and_auth_header() -> None:
    transport = FakeHonchoTransport()
    client = HonchoApiClient("https://honcho.example/v3", api_key="secret", transport=transport)

    export = export_honcho_api(client, workspace="hermes", page_size=50)

    assert export["format"] == "hermes-local-memory.honcho-export.v1"
    assert export["source"]["kind"] == "honcho-api"
    assert export["source"]["workspace"] == "hermes"
    assert len(export["peers"]) == 3
    assert len(export["sessions"]) == 1
    assert len(export["session_peers"]) == 2
    assert len(export["messages"]) == 2
    assert len(export["cards"]) == 3
    assert len(export["conclusions"]) == 1
    assert any(
        request[1] == "https://honcho.example/v3/workspaces/hermes/peers/list?page=1&size=50"
        for request in transport.requests
    )
    assert all(request[3].get("Authorization") == "Bearer secret" for request in transport.requests)


def test_plan_honcho_export_import_from_api_export_does_not_write(tmp_path: Path) -> None:
    transport = FakeHonchoTransport()
    client = HonchoApiClient("https://honcho.example/v3", transport=transport)
    export = export_honcho_api(client, workspace="hermes")
    target_db = tmp_path / "local.sqlite"

    plan = plan_honcho_export_import(export, target_db=target_db)

    assert plan["mode"] == "dry-run"
    assert plan["source"]["kind"] == "honcho-api"
    assert plan["counts"] == {
        "peers": 3,
        "aliases": 3,
        "sessions": 1,
        "session_peers": 2,
        "messages": 2,
        "cards": 3,
        "facts": 1,
    }
    assert plan["writes"] == []
    assert not target_db.exists()
    assert {peer["id"] for peer in plan["peers"]} == {
        "honcho-1001",
        "honcho-bob",
        "honcho-user-default-20260419_182008_26ad7f",
    }
    assert plan["messages"][0]["source_message_id"] == "honcho-api:msg-user-1"
    assert plan["facts"][0]["status"] == "candidate"


def test_identity_map_merges_honcho_peers_and_preserves_aliases(tmp_path: Path) -> None:
    client = HonchoApiClient("https://honcho.example/v3", transport=FakeHonchoTransport())
    export = export_honcho_api(client, workspace="hermes")
    identity_map = {
        "peers": {
            "honcho:1001": "alice",
            "honcho:Bob": "bob",
        },
        "patterns": {
            "honcho:user-default*": "alice"
        },
        "display_names": {"alice": "Alice", "bob": "Bob"},
        "kinds": {"alice": "human", "bob": "ai"},
    }

    plan = plan_honcho_export_import(
        export,
        target_db=tmp_path / "local.sqlite",
        identity_map=identity_map,
    )

    assert plan["counts"]["peers"] == 2
    assert {peer["id"] for peer in plan["peers"]} == {"alice", "bob"}
    assert {alias["alias"] for alias in plan["aliases"]} == {
        "honcho:1001",
        "honcho:Bob",
        "honcho:user-default-20260419_182008_26ad7f",
    }
    assert all(message["peer_id"] in {"alice", "bob"} for message in plan["messages"])
    assert {card["subject_peer_id"] for card in plan["cards"]} == {"alice", "bob"}
    assert plan["facts"][0]["subject_peer_id"] == "alice"


def test_identity_map_merges_duplicate_cards_in_plan(tmp_path: Path) -> None:
    export = {
        "format": "hermes-local-memory.honcho-export.v1",
        "source": {"kind": "honcho-api", "workspace": "hermes"},
        "peers": [
            {"id": "1001", "metadata": {}},
            {"id": "Alice", "metadata": {}},
            {"id": "Bob", "metadata": {"kind": "ai"}},
        ],
        "sessions": [],
        "session_peers": [],
        "messages": [],
        "cards": [
            {
                "target_id": "1001",
                "observer_id": "Bob",
                "peer_card": ["Name: Alice", "Prefers local memory"],
            },
            {
                "target_id": "Alice",
                "observer_id": "Bob",
                "peer_card": ["Name: Alice", "Lives in Example City"],
            },
        ],
        "conclusions": [],
    }
    identity_map = {
        "peers": {
            "honcho:1001": "alice",
            "honcho:Alice": "alice",
            "honcho:Bob": "bob",
        }
    }

    plan = plan_honcho_export_import(
        export,
        target_db=tmp_path / "local.sqlite",
        identity_map=identity_map,
    )

    assert plan["counts"]["cards"] == 1
    assert plan["cards"] == [
        {
            "subject_peer_id": "alice",
            "observer_peer_id": "bob",
            "scope": "global",
            "scope_id": "",
            "items": ["Name: Alice", "Prefers local memory", "Lives in Example City"],
            "source": "honcho-api-card",
        }
    ]


def test_load_identity_map_accepts_json_file(tmp_path: Path) -> None:
    path = tmp_path / "identity-map.json"
    path.write_text(
        json.dumps(
            {
                "peers": {"honcho:1001": "alice"},
                "display_names": {"alice": "Alice"},
                "kinds": {"alice": "human"},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_identity_map(path)

    assert loaded["peers"] == {"honcho:1001": "alice"}
    assert loaded["patterns"] == {}
    assert loaded["display_names"] == {"alice": "Alice"}
    assert loaded["kinds"] == {"alice": "human"}


def test_apply_honcho_api_plan_writes_data_and_is_idempotent(tmp_path: Path) -> None:
    client = HonchoApiClient("https://honcho.example/v3", transport=FakeHonchoTransport())
    export = export_honcho_api(client, workspace="hermes")
    export["messages"] = [
        {
            **export["messages"][0],
            "id": f"msg-user-{index}",
            "content": f"message {index}",
        }
        for index in range(30)
    ]
    target_db = tmp_path / "local.sqlite"
    plan = plan_honcho_export_import(export, target_db=target_db)

    assert plan["counts"]["messages"] == 30
    assert len(plan["messages"]) == 30

    first = apply_honcho_import_plan(plan, backup=True)
    second = apply_honcho_import_plan(plan, backup=True)

    assert first["mode"] == "apply"
    assert first["backup_path"] is None
    assert first["writes"] == {
        "peers_upserted": 3,
        "aliases_upserted": 3,
        "sessions_upserted": 1,
        "session_peers_upserted": 2,
        "messages_inserted": 30,
        "messages_skipped_existing": 0,
        "cards_upserted": 3,
        "facts_inserted": 1,
        "facts_skipped_existing": 0,
    }
    assert second["backup_path"] is not None
    assert Path(second["backup_path"]).exists()
    assert second["writes"]["messages_inserted"] == 0
    assert second["writes"]["messages_skipped_existing"] == 30
    assert second["writes"]["facts_inserted"] == 0
    assert second["writes"]["facts_skipped_existing"] == 1

    store = LocalMemoryStore(target_db)
    assert len(store.list_peers()) == 3
    assert len(store.list_aliases()) == 3
    assert len(store.list_sessions()) == 1
    assert len(store.list_messages(limit=100)) == 30
    assert len(store.list_cards(limit=10)) == 3
    assert len(store.list_facts(status="candidate", limit=10)) == 1


def _write_identity_map(tmp_path: Path) -> Path:
    path = tmp_path / "identity-map.json"
    path.write_text(
        json.dumps(
            {
                "peers": {
                    "honcho:1001": "alice",
                    "honcho:Bob": "bob",
                },
                "patterns": {"honcho:user-default*": "alice"},
                "display_names": {"alice": "Alice", "bob": "Bob"},
                "kinds": {"alice": "human", "bob": "ai"},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_honcho_api_import_cli_dry_run_prints_json_without_writing(
    tmp_path: Path,
    capsys,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
) -> None:
    transport = FakeHonchoTransport()

    def fake_client(base_url: str, api_key: str | None = None) -> HonchoApiClient:
        assert base_url == "https://honcho.example/v3"
        assert api_key == "secret"
        return HonchoApiClient(base_url, api_key=api_key, transport=transport)

    monkeypatch.setattr("hermes_local_memory.cli.HonchoApiClient", fake_client)
    target_db = tmp_path / "local.sqlite"

    exit_code = main(
        [
            "--db",
            str(target_db),
            "import",
            "honcho-api",
            "--base-url",
            "https://honcho.example/v3",
            "--workspace",
            "hermes",
            "--api-key",
            "secret",
            "--identity-map",
            str(_write_identity_map(tmp_path)),
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["source"]["kind"] == "honcho-api"
    assert output["counts"]["peers"] == 2
    assert output["counts"]["messages"] == 2
    assert {peer["id"] for peer in output["peers"]} == {"alice", "bob"}
    assert not target_db.exists()


def test_honcho_api_import_cli_apply_writes_with_backup(
    tmp_path: Path,
    capsys,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
) -> None:
    transport = FakeHonchoTransport()

    def fake_client(base_url: str, api_key: str | None = None) -> HonchoApiClient:
        return HonchoApiClient(base_url, api_key=api_key, transport=transport)

    monkeypatch.setattr("hermes_local_memory.cli.HonchoApiClient", fake_client)
    target_db = tmp_path / "local.sqlite"

    exit_code = main(
        [
            "--db",
            str(target_db),
            "import",
            "honcho-api",
            "--base-url",
            "https://honcho.example/v3",
            "--workspace",
            "hermes",
            "--api-key",
            "secret",
            "--apply",
            "--json",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "apply"
    assert output["backup_path"] is None
    assert output["writes"]["messages_inserted"] == 2
    assert target_db.exists()


def test_honcho_api_import_cli_rejects_missing_mode(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "hermes_local_memory.cli.HonchoApiClient",
        lambda base_url, api_key=None: HonchoApiClient(
            base_url,
            api_key=api_key,
            transport=FakeHonchoTransport(),
        ),
    )

    try:
        main(
            [
                "--db",
                str(tmp_path / "local.sqlite"),
                "import",
                "honcho-api",
                "--base-url",
                "https://honcho.example/v3",
                "--workspace",
                "hermes",
            ]
        )
    except ValueError as exc:
        assert "Specify exactly one of --dry-run or --apply" in str(exc)
    else:
        raise AssertionError("expected missing mode to fail")
