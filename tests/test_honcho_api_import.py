from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hermes_local_memory.cli import main
from hermes_local_memory.honcho_api import HonchoApiClient, export_honcho_api
from hermes_local_memory.honcho_import import apply_honcho_import_plan, plan_honcho_export_import
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
                    {"id": "Ambrogio", "metadata": {"kind": "ai"}},
                    {"id": "151011988", "metadata": {"telegram_user_id": "151011988"}},
                ],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/sessions/list":
            return _page(
                [
                    {
                        "id": "agent-main-telegram-dm-151011988",
                        "metadata": {"title": "Telegram DM with Simone"},
                    }
                ],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/sessions/agent-main-telegram-dm-151011988/peers":
            return _page(
                [{"id": "151011988"}, {"id": "Ambrogio"}],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/sessions/agent-main-telegram-dm-151011988/messages/list":
            return _page(
                [
                    {
                        "id": "msg-user-1",
                        "session_id": "agent-main-telegram-dm-151011988",
                        "peer_id": "151011988",
                        "content": "Remember that I prefer local-first memory.",
                        "metadata": {"source_message_id": "tg-1"},
                        "created_at": "2026-04-25T08:00:00Z",
                    },
                    {
                        "id": "msg-ai-1",
                        "session_id": "agent-main-telegram-dm-151011988",
                        "peer_id": "Ambrogio",
                        "content": "Got it.",
                        "metadata": {"source_message_id": "tg-2"},
                        "created_at": "2026-04-25T08:00:01Z",
                    },
                ],
                page=page,
                size=size,
            )
        if path == "/v3/workspaces/hermes/peers/Ambrogio/card":
            if query.get("target") == ["151011988"]:
                return {"peer_card": ["Simone prefers local-first memory."]}
            return {"peer_card": ["Assistant name: Ambrogio"]}
        if path == "/v3/workspaces/hermes/peers/151011988/card":
            if "target" in query:
                return {"peer_card": None}
            return {"peer_card": ["Name: Simone"]}
        if path == "/v3/workspaces/hermes/conclusions/list":
            return _page(
                [
                    {
                        "id": "conclusion-1",
                        "content": "Simone strongly prefers seamless migrations.",
                        "observer_id": "Ambrogio",
                        "observed_id": "151011988",
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
    assert len(export["peers"]) == 2
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
        "peers": 2,
        "aliases": 2,
        "sessions": 1,
        "session_peers": 2,
        "messages": 2,
        "cards": 3,
        "facts": 1,
    }
    assert plan["writes"] == []
    assert not target_db.exists()
    assert {peer["id"] for peer in plan["peers"]} == {"honcho-151011988", "honcho-ambrogio"}
    assert plan["messages"][0]["source_message_id"] == "honcho-api:msg-user-1"
    assert plan["facts"][0]["status"] == "candidate"


def test_apply_honcho_api_plan_writes_data_and_is_idempotent(tmp_path: Path) -> None:
    client = HonchoApiClient("https://honcho.example/v3", transport=FakeHonchoTransport())
    export = export_honcho_api(client, workspace="hermes")
    target_db = tmp_path / "local.sqlite"
    plan = plan_honcho_export_import(export, target_db=target_db)

    first = apply_honcho_import_plan(plan, backup=True)
    second = apply_honcho_import_plan(plan, backup=True)

    assert first["mode"] == "apply"
    assert first["backup_path"] is None
    assert first["writes"] == {
        "peers_upserted": 2,
        "aliases_upserted": 2,
        "sessions_upserted": 1,
        "session_peers_upserted": 2,
        "messages_inserted": 2,
        "messages_skipped_existing": 0,
        "cards_upserted": 3,
        "facts_inserted": 1,
        "facts_skipped_existing": 0,
    }
    assert second["backup_path"] is not None
    assert Path(second["backup_path"]).exists()
    assert second["writes"]["messages_inserted"] == 0
    assert second["writes"]["messages_skipped_existing"] == 2
    assert second["writes"]["facts_inserted"] == 0
    assert second["writes"]["facts_skipped_existing"] == 1

    store = LocalMemoryStore(target_db)
    assert len(store.list_peers()) == 2
    assert len(store.list_aliases()) == 2
    assert len(store.list_sessions()) == 1
    assert len(store.list_messages(limit=10)) == 2
    assert len(store.list_cards(limit=10)) == 3
    assert len(store.list_facts(status="candidate", limit=10)) == 1


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
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["source"]["kind"] == "honcho-api"
    assert output["counts"]["messages"] == 2
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
