from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any, Protocol


class HonchoTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]: ...


class UrllibHonchoTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        body = None
        request_headers = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Honcho API request failed: {exc.code} {detail}") from exc
        return json.loads(payload) if payload else {}


class HonchoApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        transport: HonchoTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport or UrllibHonchoTransport()

    def list_peers(self, workspace: str, *, page_size: int = 100) -> list[dict[str, Any]]:
        return self._paginate(f"/workspaces/{workspace}/peers/list", page_size=page_size)

    def list_sessions(self, workspace: str, *, page_size: int = 100) -> list[dict[str, Any]]:
        return self._paginate(f"/workspaces/{workspace}/sessions/list", page_size=page_size)

    def list_session_peers(
        self,
        workspace: str,
        session_id: str,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        quoted = urllib.parse.quote(session_id, safe="")
        return self._paginate(
            f"/workspaces/{workspace}/sessions/{quoted}/peers",
            page_size=page_size,
        )

    def list_messages(
        self,
        workspace: str,
        session_id: str,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        quoted = urllib.parse.quote(session_id, safe="")
        return self._paginate(
            f"/workspaces/{workspace}/sessions/{quoted}/messages/list",
            page_size=page_size,
        )

    def list_conclusions(
        self,
        workspace: str,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        return self._paginate(f"/workspaces/{workspace}/conclusions/list", page_size=page_size)

    def get_peer_card(
        self,
        workspace: str,
        observer_peer_id: str,
        *,
        target_peer_id: str | None = None,
    ) -> list[str] | None:
        quoted_observer = urllib.parse.quote(observer_peer_id, safe="")
        path = f"/workspaces/{workspace}/peers/{quoted_observer}/card"
        params = {}
        if target_peer_id is not None:
            params["target"] = target_peer_id
        response = self._request("GET", path, params=params)
        peer_card = response.get("peer_card")
        if isinstance(peer_card, list) and all(isinstance(item, str) for item in peer_card):
            return peer_card
        return None

    def _paginate(
        self,
        path: str,
        *,
        page_size: int,
        body: dict[str, object] | None = None,
    ) -> list[dict[str, Any]]:
        page = 1
        items: list[dict[str, Any]] = []
        while True:
            response = self._request(
                "POST" if body is not None or path.endswith("/list") else "GET",
                path,
                params={"page": page, "size": page_size},
                json_body=body,
            )
            page_items = response.get("items", [])
            if not isinstance(page_items, list):
                raise RuntimeError(f"Unexpected Honcho page response for {path}: missing items")
            items.extend([dict(item) for item in page_items if isinstance(item, dict)])
            pages = int(response.get("pages") or 0)
            if page >= pages or not page_items:
                return items
            page += 1

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = self.transport.request(method, url, json_body=json_body, headers=headers)
        return dict(response)


def export_honcho_api(
    client: HonchoApiClient,
    *,
    workspace: str,
    page_size: int = 100,
) -> dict[str, Any]:
    peers = client.list_peers(workspace, page_size=page_size)
    sessions = client.list_sessions(workspace, page_size=page_size)
    session_peers: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    for session in sessions:
        session_id = _id(session)
        if not session_id:
            continue
        for peer in client.list_session_peers(workspace, session_id, page_size=page_size):
            session_peers.append({"session_id": session_id, "peer_id": _id(peer), "raw": peer})
        messages.extend(client.list_messages(workspace, session_id, page_size=page_size))

    cards: list[dict[str, Any]] = []
    peer_ids = [peer_id for peer in peers if (peer_id := _id(peer))]
    for observer in peer_ids:
        self_card = client.get_peer_card(workspace, observer)
        if self_card:
            cards.append(
                {
                    "observer_id": observer,
                    "target_id": observer,
                    "peer_card": self_card,
                    "source": "honcho-api-peer-card",
                }
            )
        for target in peer_ids:
            if target == observer:
                continue
            peer_card = client.get_peer_card(workspace, observer, target_peer_id=target)
            if peer_card:
                cards.append(
                    {
                        "observer_id": observer,
                        "target_id": target,
                        "peer_card": peer_card,
                        "source": "honcho-api-observer-card",
                    }
                )

    conclusions = client.list_conclusions(workspace, page_size=page_size)
    return {
        "format": "hermes-local-memory.honcho-export.v1",
        "source": {
            "kind": "honcho-api",
            "base_url": client.base_url,
            "workspace": workspace,
            "exported_at": datetime.now(UTC).isoformat(),
        },
        "peers": peers,
        "sessions": sessions,
        "session_peers": session_peers,
        "messages": messages,
        "cards": cards,
        "conclusions": conclusions,
        "summaries": [],
    }


def _id(row: dict[str, Any]) -> str | None:
    value = row.get("id") or row.get("name") or row.get("peer_id")
    return str(value) if value is not None else None
