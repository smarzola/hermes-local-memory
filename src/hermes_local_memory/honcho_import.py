from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


def plan_honcho_import(
    source_db: str | Path,
    *,
    target_db: str | Path,
    workspace: str = "hermes",
    limit_preview: int = 25,
) -> dict[str, Any]:
    """Build a read-only import plan from a Honcho-like SQLite export.

    This intentionally does not write to the target DB. It is the safety-first
    precursor to a future --apply command and is designed to work against
    deterministic fixtures as well as SQLite exports of Honcho tables.
    """

    source_path = Path(source_db).expanduser()
    target_path = Path(target_db).expanduser()
    with sqlite3.connect(source_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = _table_names(conn)
        peers = _read_peers(conn, tables, workspace)
        sessions = _read_sessions(conn, tables, workspace)
        session_peers = _read_session_peers(conn, tables, workspace)
        messages = _read_messages(conn, tables, workspace)
        cards = _read_cards(peers)
        facts = _read_documents_as_candidate_facts(conn, tables, workspace)

    aliases = [
        {
            "alias": f"honcho:{peer['source_name']}",
            "peer_id": peer["id"],
            "source": "honcho-import",
            "confidence": 1.0,
            "verified": False,
        }
        for peer in peers
    ]
    warnings = _build_warnings(tables)
    counts = {
        "peers": len(peers),
        "aliases": len(aliases),
        "sessions": len(sessions),
        "session_peers": len(session_peers),
        "messages": len(messages),
        "cards": len(cards),
        "facts": len(facts),
    }
    return {
        "mode": "dry-run",
        "source": {"kind": "honcho-sqlite", "db_path": str(source_path), "workspace": workspace},
        "target": {"kind": "local-memory-sqlite", "db_path": str(target_path)},
        "counts": counts,
        "warnings": warnings,
        "writes": [],
        "peers": peers[:limit_preview],
        "aliases": aliases[:limit_preview],
        "sessions": sessions[:limit_preview],
        "session_peers": session_peers[:limit_preview],
        "messages": messages[:limit_preview],
        "cards": cards[:limit_preview],
        "facts": facts[:limit_preview],
    }


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("select name from sqlite_master where type = 'table'").fetchall()
    return {row["name"] for row in rows}


def _read_peers(conn: sqlite3.Connection, tables: set[str], workspace: str) -> list[dict[str, Any]]:
    if "peers" not in tables:
        return []
    rows = conn.execute(
        "select * from peers where workspace_name = ? order by name collate nocase",
        (workspace,),
    ).fetchall()
    peers = []
    for row in rows:
        source_name = row["name"]
        metadata = _loads(row, "metadata", {})
        internal_metadata = _loads(row, "internal_metadata", {})
        peers.append(
            {
                "id": _local_peer_id(source_name),
                "source_name": source_name,
                "display_name": source_name,
                "kind": _peer_kind(source_name, metadata),
                "metadata": {
                    "source": "honcho",
                    "honcho_workspace": workspace,
                    "honcho_peer_name": source_name,
                    "honcho_metadata": metadata,
                    "honcho_internal_metadata": internal_metadata,
                },
            }
        )
    return peers


def _read_sessions(
    conn: sqlite3.Connection,
    tables: set[str],
    workspace: str,
) -> list[dict[str, Any]]:
    if "sessions" not in tables:
        return []
    rows = conn.execute(
        "select * from sessions where workspace_name = ? order by name collate nocase",
        (workspace,),
    ).fetchall()
    result = []
    for row in rows:
        source_name = row["name"]
        metadata = _loads(row, "metadata", {})
        result.append(
            {
                "id": _local_session_id(source_name),
                "source_name": source_name,
                "profile_id": workspace,
                "platform": _infer_platform(source_name, metadata),
                "external_id": _infer_external_id(source_name, metadata),
                "title": metadata.get("title") if isinstance(metadata, dict) else None,
                "scope": "private",
                "metadata": {
                    "source": "honcho",
                    "honcho_workspace": workspace,
                    "honcho_session_name": source_name,
                    "honcho_metadata": metadata,
                },
            }
        )
    return result


def _read_session_peers(
    conn: sqlite3.Connection,
    tables: set[str],
    workspace: str,
) -> list[dict[str, Any]]:
    if "session_peers" not in tables:
        return []
    rows = conn.execute(
        """
        select * from session_peers
        where workspace_name = ?
        order by session_name collate nocase, peer_name collate nocase
        """,
        (workspace,),
    ).fetchall()
    return [
        {
            "session_id": _local_session_id(row["session_name"]),
            "peer_id": _local_peer_id(row["peer_name"]),
            "role": "assistant" if _looks_like_assistant(row["peer_name"]) else "participant",
            "left_at": _value(row, "left_at"),
        }
        for row in rows
    ]


def _read_messages(
    conn: sqlite3.Connection,
    tables: set[str],
    workspace: str,
) -> list[dict[str, Any]]:
    if "messages" not in tables:
        return []
    rows = conn.execute(
        """
        select * from messages
        where workspace_name = ?
        order by id asc
        """,
        (workspace,),
    ).fetchall()
    result = []
    for row in rows:
        source_id = str(row["id"])
        metadata = _loads(row, "metadata", {})
        result.append(
            {
                "session_id": _local_session_id(row["session_name"]),
                "peer_id": _local_peer_id(row["peer_name"]),
                "role": "assistant" if _looks_like_assistant(row["peer_name"]) else "user",
                "content": row["content"],
                "source_message_id": f"honcho:{source_id}",
                "created_at": _value(row, "created_at"),
                "metadata": {
                    "source": "honcho",
                    "honcho_workspace": workspace,
                    "honcho_message_id": source_id,
                    "honcho_session_name": row["session_name"],
                    "honcho_peer_name": row["peer_name"],
                    "honcho_metadata": metadata,
                },
            }
        )
    return result


def _read_cards(peers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Cards require internal_metadata from source peers; read_peers intentionally
    # keeps public peer plan compact, so parse them in a second pass from metadata.
    cards = []
    for peer in peers:
        internal = peer["metadata"].get("honcho_internal_metadata", {})
        if not isinstance(internal, dict):
            continue
        self_card = internal.get("peer_card")
        if _is_string_list(self_card):
            cards.append(
                {
                    "subject_peer_id": peer["id"],
                    "observer_peer_id": peer["id"],
                    "scope": "global",
                    "scope_id": "",
                    "items": self_card,
                    "source": "honcho-peer-card",
                }
            )
        for key, value in internal.items():
            if key == "peer_card" or not key.endswith("_peer_card") or not _is_string_list(value):
                continue
            target_name = key[: -len("_peer_card")]
            cards.append(
                {
                    "subject_peer_id": _local_peer_id(target_name),
                    "observer_peer_id": peer["id"],
                    "scope": "global",
                    "scope_id": "",
                    "items": value,
                    "source": "honcho-observer-card",
                }
            )
    return cards


def _read_documents_as_candidate_facts(
    conn: sqlite3.Connection,
    tables: set[str],
    workspace: str,
) -> list[dict[str, Any]]:
    if "documents" not in tables:
        return []
    rows = conn.execute(
        "select * from documents where workspace_name = ? order by id",
        (workspace,),
    ).fetchall()
    result = []
    for row in rows:
        metadata = _loads(row, "metadata", {})
        observed = metadata.get("observed") if isinstance(metadata, dict) else None
        observer = metadata.get("observer") if isinstance(metadata, dict) else None
        kind = metadata.get("type", "observation") if isinstance(metadata, dict) else "observation"
        result.append(
            {
                "id": f"honcho-doc-{row['id']}",
                "subject_peer_id": _local_peer_id(observed or "unknown"),
                "observer_peer_id": _local_peer_id(observer or "unknown"),
                "kind": kind,
                "content": row["content"],
                "confidence": 0.7,
                "status": "candidate",
                "source": "honcho-document",
                "evidence_message_ids": [],
                "metadata": {
                    "source": "honcho",
                    "honcho_workspace": workspace,
                    "honcho_document_id": row["id"],
                    "honcho_metadata": metadata,
                },
            }
        )
    return result


def _build_warnings(tables: set[str]) -> list[str]:
    warnings = []
    for table in ["peers", "sessions", "session_peers", "messages"]:
        if table not in tables:
            warnings.append(f"source table missing: {table}")
    if "documents" not in tables:
        warnings.append("source table missing: documents; no candidate facts will be planned")
    return warnings


def _local_peer_id(source_name: str) -> str:
    return f"honcho-{_slug(source_name)}"


def _local_session_id(source_name: str) -> str:
    return f"honcho-{_slug(source_name)}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return slug or "unknown"


def _peer_kind(source_name: str, metadata: dict[str, Any]) -> str:
    kind = metadata.get("kind") if isinstance(metadata, dict) else None
    if kind in {"human", "ai", "group", "system"}:
        return kind
    return "ai" if _looks_like_assistant(source_name) else "human"


def _looks_like_assistant(source_name: str) -> bool:
    return source_name.lower() in {"ai", "assistant", "ambrogio", "hermes"}


def _infer_platform(source_name: str, metadata: dict[str, Any]) -> str | None:
    platform = metadata.get("platform") if isinstance(metadata, dict) else None
    if platform:
        return str(platform)
    if "telegram" in source_name:
        return "telegram"
    return None


def _infer_external_id(source_name: str, metadata: dict[str, Any]) -> str | None:
    external_id = metadata.get("external_id") if isinstance(metadata, dict) else None
    if external_id:
        return str(external_id)
    match = re.search(r"telegram-(?:dm|group)-(-?\d+)", source_name)
    return match.group(1) if match else None


def _loads(row: sqlite3.Row, key: str, default: Any) -> Any:
    data = dict(row)
    if key not in data or data[key] in (None, ""):
        return default
    try:
        return json.loads(data[key])
    except (TypeError, json.JSONDecodeError):
        return default


def _value(row: sqlite3.Row, key: str) -> Any:
    return dict(row).get(key)


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
