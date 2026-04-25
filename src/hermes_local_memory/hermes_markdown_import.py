from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from hermes_local_memory.store import LocalMemoryStore

ENTRY_DELIMITER = "\n§\n"


def plan_hermes_markdown_import(
    source_dir: str | Path,
    *,
    target_db: str | Path,
    user_peer_id: str = "user",
    assistant_peer_id: str = "assistant",
    user_display_name: str | None = None,
    assistant_display_name: str | None = None,
    session_id: str = "hermes-markdown-import",
    limit_preview: int = 25,
) -> dict[str, Any]:
    """Build a read-only import plan from Hermes built-in MEMORY.md / USER.md files."""
    source = Path(source_dir).expanduser()
    if source.is_file():
        source = source.parent
    user_entries = _read_entries(source / "USER.md")
    memory_entries = _read_entries(source / "MEMORY.md")

    peers = [
        {
            "id": user_peer_id,
            "display_name": user_display_name or _display_name(user_peer_id),
            "kind": "human",
            "metadata": {"source": "hermes-markdown", "target": "user"},
        },
        {
            "id": assistant_peer_id,
            "display_name": assistant_display_name or _display_name(assistant_peer_id),
            "kind": "ai",
            "metadata": {"source": "hermes-markdown", "target": "memory"},
        },
    ]
    aliases = [
        {
            "alias": "user",
            "peer_id": user_peer_id,
            "source": "hermes-markdown-import",
            "confidence": 1.0,
            "verified": True,
        },
        {
            "alias": "ai",
            "peer_id": assistant_peer_id,
            "source": "hermes-markdown-import",
            "confidence": 1.0,
            "verified": True,
        },
    ]
    sessions = [
        {
            "id": session_id,
            "profile_id": "default",
            "platform": "hermes-markdown",
            "external_id": str(source),
            "title": "Hermes built-in markdown memory import",
            "scope": "migration",
            "metadata": {"source": "hermes-markdown", "path": str(source)},
        }
    ]
    session_peers = [
        {"session_id": session_id, "peer_id": user_peer_id, "role": "participant"},
        {"session_id": session_id, "peer_id": assistant_peer_id, "role": "observer"},
    ]
    cards = []
    if user_entries:
        cards.append(
            {
                "subject_peer_id": user_peer_id,
                "observer_peer_id": assistant_peer_id,
                "scope": "global",
                "scope_id": "",
                "items": user_entries,
            }
        )
    if memory_entries:
        cards.append(
            {
                "subject_peer_id": assistant_peer_id,
                "observer_peer_id": assistant_peer_id,
                "scope": "global",
                "scope_id": "",
                "items": memory_entries,
            }
        )
    facts = []
    facts.extend(
        _facts_from_entries(
            entries=user_entries,
            subject_peer_id=user_peer_id,
            observer_peer_id=assistant_peer_id,
            kind="user_profile",
            target="USER.md",
        )
    )
    facts.extend(
        _facts_from_entries(
            entries=memory_entries,
            subject_peer_id=assistant_peer_id,
            observer_peer_id=assistant_peer_id,
            kind="agent_memory",
            target="MEMORY.md",
        )
    )
    counts = {
        "peers": len(peers),
        "aliases": len(aliases),
        "sessions": len(sessions),
        "session_peers": len(session_peers),
        "messages": 0,
        "cards": len(cards),
        "facts": len(facts),
    }
    return {
        "mode": "dry-run",
        "source": {
            "kind": "hermes-markdown",
            "path": str(source),
            "files": {
                "USER.md": str(source / "USER.md"),
                "MEMORY.md": str(source / "MEMORY.md"),
            },
        },
        "target": {"kind": "local-memory-sqlite", "db_path": str(Path(target_db).expanduser())},
        "counts": counts,
        "warnings": _warnings(source, user_entries, memory_entries),
        "writes": [],
        "preview_limit": limit_preview,
        "preview": {
            "peers": peers[:limit_preview],
            "aliases": aliases[:limit_preview],
            "sessions": sessions[:limit_preview],
            "session_peers": session_peers[:limit_preview],
            "messages": [],
            "cards": cards[:limit_preview],
            "facts": facts[:limit_preview],
        },
        "peers": peers,
        "aliases": aliases,
        "sessions": sessions,
        "session_peers": session_peers,
        "messages": [],
        "cards": cards,
        "facts": facts,
    }


def apply_hermes_markdown_import_plan(
    plan: dict[str, Any],
    *,
    backup: bool = True,
) -> dict[str, Any]:
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
            scope=session.get("scope") or "migration",
            metadata=session.get("metadata") or {},
        )
        writes["sessions_upserted"] += 1
    for item in plan.get("session_peers", []):
        _upsert_session_peer(store, item)
        writes["session_peers_upserted"] += 1
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
            kind=fact.get("kind") or "note",
            confidence=float(fact.get("confidence", 1.0)),
            status=fact.get("status") or "active",
            source=fact.get("source") or "hermes-markdown",
            evidence_message_ids=fact.get("evidence_message_ids") or [],
        )
        writes["facts_inserted"] += 1
    return {
        "mode": "apply",
        "source": plan.get("source", {}),
        "target": plan.get("target", {}),
        "backup_path": str(backup_path) if backup_path else None,
        "writes": writes,
        "warnings": plan.get("warnings", []),
    }


def _read_entries(path: Path) -> list[str]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return []
    entries = [entry.strip() for entry in raw.split(ENTRY_DELIMITER)]
    # Accept legacy files that used bare section signs without surrounding newlines.
    if len(entries) == 1 and "§" in raw:
        entries = [entry.strip() for entry in raw.split("§")]
    return list(dict.fromkeys(entry for entry in entries if entry))


def _facts_from_entries(
    *,
    entries: list[str],
    subject_peer_id: str,
    observer_peer_id: str,
    kind: str,
    target: str,
) -> list[dict[str, Any]]:
    facts = []
    for index, entry in enumerate(entries, start=1):
        facts.append(
            {
                "id": _fact_id(target, subject_peer_id, observer_peer_id, entry),
                "subject_peer_id": subject_peer_id,
                "observer_peer_id": observer_peer_id,
                "kind": kind,
                "content": entry,
                "confidence": 1.0,
                "status": "active",
                "source": "hermes-markdown",
                "evidence_message_ids": [],
                "metadata": {"source_file": target, "entry_index": index},
            }
        )
    return facts


def _fact_id(target: str, subject_peer_id: str, observer_peer_id: str, content: str) -> str:
    digest = hashlib.sha256(
        f"{target}\0{subject_peer_id}\0{observer_peer_id}\0{content}".encode()
    ).hexdigest()[:16]
    return f"hermes-md-{digest}"


def _display_name(peer_id: str) -> str:
    if peer_id in {"user", "assistant", "ai"}:
        return peer_id.title()
    return peer_id.replace("-", " ").replace("_", " ").title()


def _warnings(source: Path, user_entries: list[str], memory_entries: list[str]) -> list[str]:
    warnings = []
    if not source.exists():
        warnings.append(f"source directory does not exist: {source}")
    if not (source / "USER.md").exists():
        warnings.append("USER.md not found; no user profile entries imported")
    if not (source / "MEMORY.md").exists():
        warnings.append("MEMORY.md not found; no agent memory entries imported")
    if not user_entries and not memory_entries:
        warnings.append("no Hermes markdown memory entries found")
    return warnings


def _backup_db(target_db: Path) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_path = target_db.with_name(f"{target_db.name}-backup-{timestamp}.sqlite")
    shutil.copy2(target_db, backup_path)
    return backup_path


def _upsert_session_peer(store: LocalMemoryStore, item: dict[str, Any]) -> None:
    with store.connect() as conn:
        conn.execute(
            """
            insert into session_peers(session_id, peer_id, role)
            values (?, ?, ?)
            on conflict(session_id, peer_id) do update set
              role = excluded.role
            """,
            (item["session_id"], item["peer_id"], item.get("role") or "participant"),
        )
