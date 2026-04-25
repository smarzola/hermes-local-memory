from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from hermes_local_memory.store import LocalMemoryStore


def plan_honcho_import(
    source_db: str | Path,
    *,
    target_db: str | Path,
    workspace: str = "hermes",
    limit_preview: int = 25,
) -> dict[str, Any]:
    """Build a read-only import plan from a Honcho-like SQLite export."""

    source_path = Path(source_db).expanduser()
    with sqlite3.connect(source_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = _table_names(conn)
        peers = _read_peers(conn, tables, workspace)
        sessions = _read_sessions(conn, tables, workspace)
        session_peers = _read_session_peers(conn, tables, workspace)
        messages = _read_messages(conn, tables, workspace)
        cards = _read_cards(peers)
        facts = _read_documents_as_candidate_facts(conn, tables, workspace)

    return _build_plan(
        source={"kind": "honcho-sqlite", "db_path": str(source_path), "workspace": workspace},
        target_db=target_db,
        peers=peers,
        sessions=sessions,
        session_peers=session_peers,
        messages=messages,
        cards=cards,
        facts=facts,
        warnings=_build_warnings(tables),
        limit_preview=limit_preview,
    )


def plan_honcho_export_import(
    export: dict[str, Any],
    *,
    target_db: str | Path,
    limit_preview: int = 25,
) -> dict[str, Any]:
    """Build a read-only import plan from the stable Honcho API export format."""

    source = dict(export.get("source", {}))
    workspace = str(source.get("workspace") or "")
    peers = [_peer_from_export(row, workspace) for row in export.get("peers", [])]
    sessions = [_session_from_export(row, workspace) for row in export.get("sessions", [])]
    session_peers = [
        _session_peer_from_export(row) for row in export.get("session_peers", [])
    ]
    messages = [_message_from_export(row, workspace) for row in export.get("messages", [])]
    cards = [_card_from_export(row) for row in export.get("cards", [])]
    facts = [_conclusion_from_export(row, workspace) for row in export.get("conclusions", [])]
    warnings = []
    if export.get("format") != "hermes-local-memory.honcho-export.v1":
        warnings.append("unrecognized Honcho export format")
    return _build_plan(
        source=source,
        target_db=target_db,
        peers=peers,
        sessions=sessions,
        session_peers=session_peers,
        messages=messages,
        cards=cards,
        facts=facts,
        warnings=warnings,
        limit_preview=limit_preview,
    )


def _build_plan(
    *,
    source: dict[str, Any],
    target_db: str | Path,
    peers: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    session_peers: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    warnings: list[str],
    limit_preview: int,
) -> dict[str, Any]:
    target_path = Path(target_db).expanduser()
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
        "source": source,
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


def apply_honcho_import_plan(plan: dict[str, Any], *, backup: bool = True) -> dict[str, Any]:
    """Apply a previously generated Honcho import plan to the local SQLite store.

    The operation is intentionally additive/idempotent: raw messages and facts are
    skipped when their source IDs already exist, while peers, aliases, sessions,
    session peers, and cards are upserted.
    """

    target_db = Path(plan["target"]["db_path"]).expanduser()
    backup_path = _backup_db(target_db) if backup and target_db.exists() else None
    store = LocalMemoryStore(target_db)
    store.initialize()
    writes = {
        "peers_upserted": 0,
        "aliases_upserted": 0,
        "sessions_upserted": 0,
        "session_peers_upserted": 0,
        "messages_inserted": 0,
        "messages_skipped_existing": 0,
        "cards_upserted": 0,
        "facts_inserted": 0,
        "facts_skipped_existing": 0,
    }

    for peer in plan.get("peers", []):
        store.upsert_peer(
            peer["id"],
            display_name=peer.get("display_name") or peer["id"],
            kind=peer.get("kind") or "human",
            metadata=peer.get("metadata") or {},
        )
        writes["peers_upserted"] += 1

    for alias in plan.get("aliases", []):
        store.set_alias(
            alias["alias"],
            peer_id=alias["peer_id"],
            source=alias.get("source"),
            confidence=float(alias.get("confidence", 1.0)),
            verified=bool(alias.get("verified", False)),
        )
        writes["aliases_upserted"] += 1

    for session in plan.get("sessions", []):
        store.upsert_session(
            session["id"],
            profile_id=session.get("profile_id") or "default",
            platform=session.get("platform"),
            external_id=session.get("external_id"),
            title=session.get("title"),
            scope=session.get("scope") or "private",
            metadata=session.get("metadata") or {},
        )
        writes["sessions_upserted"] += 1

    for item in plan.get("session_peers", []):
        _upsert_session_peer(store, item)
        writes["session_peers_upserted"] += 1

    for message in plan.get("messages", []):
        source_message_id = message.get("source_message_id")
        if source_message_id and store.message_exists_by_source_id(source_message_id):
            writes["messages_skipped_existing"] += 1
            continue
        store.add_message(
            session_id=message["session_id"],
            peer_id=message["peer_id"],
            role=message.get("role") or "user",
            content=message.get("content") or "",
            source_message_id=source_message_id,
            metadata=message.get("metadata") or {},
        )
        writes["messages_inserted"] += 1

    for card in plan.get("cards", []):
        store.set_card(
            subject_peer_id=card["subject_peer_id"],
            observer_peer_id=card["observer_peer_id"],
            items=card.get("items") or [],
            scope=card.get("scope") or "global",
            scope_id=card.get("scope_id") or "",
        )
        writes["cards_upserted"] += 1

    for fact in plan.get("facts", []):
        if store.fact_exists(fact["id"]):
            writes["facts_skipped_existing"] += 1
            continue
        store.add_fact(
            fact_id=fact["id"],
            subject_peer_id=fact["subject_peer_id"],
            observer_peer_id=fact["observer_peer_id"],
            content=fact.get("content") or "",
            kind=fact.get("kind") or "conclusion",
            confidence=float(fact.get("confidence", 0.7)),
            status=fact.get("status") or "candidate",
            source=fact.get("source") or "honcho-import",
            evidence_message_ids=fact.get("evidence_message_ids") or [],
        )
        writes["facts_inserted"] += 1

    return {
        "mode": "apply",
        "source": plan["source"],
        "target": plan["target"],
        "backup_path": str(backup_path) if backup_path is not None else None,
        "writes": writes,
        "warnings": plan.get("warnings", []),
    }


def _backup_db(target_db: Path) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_path = target_db.with_name(f"{target_db.name}.{timestamp}.bak")
    shutil.copy2(target_db, backup_path)
    return backup_path


def _upsert_session_peer(store: LocalMemoryStore, item: dict[str, Any]) -> None:
    with store.connect() as conn:
        conn.execute(
            """
            insert into session_peers(session_id, peer_id, role, left_at)
            values (?, ?, ?, ?)
            on conflict(session_id, peer_id) do update set
              role = excluded.role,
              left_at = excluded.left_at
            """,
            (
                item["session_id"],
                item["peer_id"],
                item.get("role") or "participant",
                item.get("left_at"),
            ),
        )


def _peer_from_export(row: dict[str, Any], workspace: str) -> dict[str, Any]:
    source_name = _source_id(row)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "id": _local_peer_id(source_name),
        "source_name": source_name,
        "display_name": source_name,
        "kind": _peer_kind(source_name, metadata),
        "metadata": {
            "source": "honcho-api",
            "honcho_workspace": workspace,
            "honcho_peer_name": source_name,
            "honcho_metadata": metadata,
        },
    }


def _session_from_export(row: dict[str, Any], workspace: str) -> dict[str, Any]:
    source_name = _source_id(row)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "id": _local_session_id(source_name),
        "source_name": source_name,
        "profile_id": workspace,
        "platform": _infer_platform(source_name, metadata),
        "external_id": _infer_external_id(source_name, metadata),
        "title": metadata.get("title") if isinstance(metadata, dict) else None,
        "scope": "private",
        "metadata": {
            "source": "honcho-api",
            "honcho_workspace": workspace,
            "honcho_session_name": source_name,
            "honcho_metadata": metadata,
        },
    }


def _session_peer_from_export(row: dict[str, Any]) -> dict[str, Any]:
    peer_name = str(row.get("peer_id") or row.get("id") or "unknown")
    return {
        "session_id": _local_session_id(str(row.get("session_id") or "unknown")),
        "peer_id": _local_peer_id(peer_name),
        "role": "assistant" if _looks_like_assistant(peer_name) else "participant",
        "left_at": row.get("left_at"),
    }


def _message_from_export(row: dict[str, Any], workspace: str) -> dict[str, Any]:
    message_id = _source_id(row)
    peer_name = str(row.get("peer_id") or row.get("peer_name") or "unknown")
    session_name = str(row.get("session_id") or row.get("session_name") or "unknown")
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "session_id": _local_session_id(session_name),
        "peer_id": _local_peer_id(peer_name),
        "role": "assistant" if _looks_like_assistant(peer_name) else "user",
        "content": str(row.get("content") or ""),
        "source_message_id": f"honcho-api:{message_id}",
        "created_at": row.get("created_at"),
        "metadata": {
            "source": "honcho-api",
            "honcho_workspace": workspace,
            "honcho_message_id": message_id,
            "honcho_session_name": session_name,
            "honcho_peer_name": peer_name,
            "honcho_metadata": metadata,
        },
    }


def _card_from_export(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject_peer_id": _local_peer_id(str(row.get("target_id") or "unknown")),
        "observer_peer_id": _local_peer_id(str(row.get("observer_id") or "unknown")),
        "scope": "global",
        "scope_id": "",
        "items": row.get("peer_card") if isinstance(row.get("peer_card"), list) else [],
        "source": str(row.get("source") or "honcho-api-card"),
    }


def _conclusion_from_export(row: dict[str, Any], workspace: str) -> dict[str, Any]:
    conclusion_id = _source_id(row)
    observed = str(row.get("observed_id") or row.get("observed") or "unknown")
    observer = str(row.get("observer_id") or row.get("observer") or "unknown")
    return {
        "id": f"honcho-api-conclusion-{conclusion_id}",
        "subject_peer_id": _local_peer_id(observed),
        "observer_peer_id": _local_peer_id(observer),
        "kind": "conclusion",
        "content": str(row.get("content") or ""),
        "confidence": 0.7,
        "status": "candidate",
        "source": "honcho-api-conclusion",
        "evidence_message_ids": [],
        "metadata": {
            "source": "honcho-api",
            "honcho_workspace": workspace,
            "honcho_conclusion_id": conclusion_id,
            "honcho_metadata": row,
        },
    }


def _source_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("name") or "unknown")


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
