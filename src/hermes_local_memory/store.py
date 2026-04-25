from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from hermes_local_memory.schema import SCHEMA_SQL


class LocalMemoryStore:
    """SQLite-backed local memory store.

    The store is intentionally small and explicit: raw messages are immutable-ish
    history, facts/cards/summaries are inspectable derived layers, and aliases
    are first-class identity data.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from profiles where id = ?", (profile_id,)).fetchone()
            return self._row_to_dict(row)

    def upsert_peer(
        self,
        peer_id: str,
        *,
        display_name: str,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                insert into peers(id, display_name, kind, metadata_json)
                values (?, ?, ?, ?)
                on conflict(id) do update set
                  display_name = excluded.display_name,
                  kind = excluded.kind,
                  metadata_json = excluded.metadata_json
                """,
                (peer_id, display_name, kind, self._json(metadata or {})),
            )
            row = conn.execute("select * from peers where id = ?", (peer_id,)).fetchone()
            assert row is not None
            return dict(row)

    def set_alias(
        self,
        alias: str,
        *,
        peer_id: str,
        source: str | None = None,
        confidence: float = 1.0,
        verified: bool = False,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                insert into peer_aliases(alias, peer_id, source, confidence, verified)
                values (?, ?, ?, ?, ?)
                on conflict(alias) do update set
                  peer_id = excluded.peer_id,
                  source = excluded.source,
                  confidence = excluded.confidence,
                  verified = excluded.verified
                """,
                (alias, peer_id, source, confidence, int(verified)),
            )
            row = conn.execute("select * from peer_aliases where alias = ?", (alias,)).fetchone()
            assert row is not None
            return dict(row)

    def resolve_peer(self, peer_or_alias: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from peers where id = ?", (peer_or_alias,)).fetchone()
            if row is not None:
                return dict(row)
            row = conn.execute(
                """
                select p.*
                from peer_aliases a
                join peers p on p.id = a.peer_id
                where a.alias = ?
                """,
                (peer_or_alias,),
            ).fetchone()
            return self._row_to_dict(row)

    def upsert_session(
        self,
        session_id: str,
        *,
        profile_id: str = "default",
        platform: str | None = None,
        external_id: str | None = None,
        title: str | None = None,
        scope: str = "private",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "insert or ignore into profiles(id, display_name) values (?, ?)",
                (profile_id, profile_id.title()),
            )
            conn.execute(
                """
                insert into sessions(
                  id, profile_id, platform, external_id, title, scope, metadata_json
                ) values (?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  profile_id = excluded.profile_id,
                  platform = excluded.platform,
                  external_id = excluded.external_id,
                  title = excluded.title,
                  scope = excluded.scope,
                  metadata_json = excluded.metadata_json,
                  updated_at = datetime('now')
                """,
                (
                    session_id,
                    profile_id,
                    platform,
                    external_id,
                    title,
                    scope,
                    self._json(metadata or {}),
                ),
            )
            row = conn.execute("select * from sessions where id = ?", (session_id,)).fetchone()
            assert row is not None
            return dict(row)

    def add_message(
        self,
        *,
        session_id: str,
        peer_id: str,
        role: str,
        content: str,
        source_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                insert or ignore into session_peers(session_id, peer_id, role)
                values (?, ?, ?)
                """,
                (session_id, peer_id, "assistant" if role == "assistant" else "participant"),
            )
            cur = conn.execute(
                """
                insert into messages(
                  session_id, peer_id, role, content, source_message_id, metadata_json
                ) values (?, ?, ?, ?, ?, ?)
                """,
                (session_id, peer_id, role, content, source_message_id, self._json(metadata or {})),
            )
            row = conn.execute("select * from messages where id = ?", (cur.lastrowid,)).fetchone()
            assert row is not None
            return dict(row)

    def add_fact(
        self,
        *,
        subject_peer_id: str,
        observer_peer_id: str,
        content: str,
        scope: str = "global",
        scope_id: str | None = None,
        kind: str = "note",
        confidence: float = 1.0,
        status: str = "active",
        source: str = "manual",
        evidence_message_ids: list[int] | None = None,
        fact_id: str | None = None,
    ) -> dict[str, Any]:
        fact_id = fact_id or self._new_id("fact")
        evidence = evidence_message_ids or []
        with self.connect() as conn:
            conn.execute(
                """
                insert into facts(
                  id, subject_peer_id, observer_peer_id, scope, scope_id, kind, content,
                  confidence, status, source, evidence_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    subject_peer_id,
                    observer_peer_id,
                    scope,
                    scope_id,
                    kind,
                    content,
                    confidence,
                    status,
                    source,
                    self._json(evidence),
                ),
            )
            row = conn.execute("select * from facts where id = ?", (fact_id,)).fetchone()
            assert row is not None
            return self._hydrate_fact(row)

    def _hydrate_fact(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["evidence_message_ids"] = json.loads(data.pop("evidence_json") or "[]")
        return data

    def list_peers(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from peers order by display_name collate nocase, id"
            ).fetchall()
            return [dict(row) for row in rows]

    def list_aliases(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("select * from peer_aliases order by alias").fetchall()
            return [dict(row) for row in rows]

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("select * from sessions order by updated_at desc, id").fetchall()
            return [dict(row) for row in rows]

    def list_cards(
        self,
        *,
        subject_peer_id: str | None = None,
        observer_peer_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if subject_peer_id:
            clauses.append("subject_peer_id = ?")
            params.append(subject_peer_id)
        if observer_peer_id:
            clauses.append("observer_peer_id = ?")
            params.append(observer_peer_id)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from cards
                {where}
                order by updated_at desc, subject_peer_id, observer_peer_id
                limit ?
                """,
                params,
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["items"] = json.loads(data.pop("content_json") or "[]")
            result.append(data)
        return result

    def list_messages(
        self,
        *,
        session_id: str | None = None,
        peer_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if peer_id:
            clauses.append("peer_id = ?")
            params.append(peer_id)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from messages
                {where}
                order by id asc
                limit ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def list_facts(
        self,
        *,
        peer_id: str | None = None,
        observer_peer_id: str | None = None,
        status: str | None = "active",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if peer_id:
            clauses.append("subject_peer_id = ?")
            params.append(peer_id)
        if observer_peer_id:
            clauses.append("observer_peer_id = ?")
            params.append(observer_peer_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from facts
                {where}
                order by updated_at desc, created_at desc, id
                limit ?
                """,
                params,
            ).fetchall()
            return [self._hydrate_fact(row) for row in rows]

    def search(
        self,
        query: str,
        *,
        peer_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        # FTS5 syntax is not user-friendly; quote terms and join with OR for MVP robustness.
        terms = [term.replace('"', '""') for term in query.split() if term.strip()]
        fts_query = " OR ".join(f'"{term}"' for term in terms) if terms else '""'
        with self.connect() as conn:
            params: list[Any] = [fts_query]
            where_peer = ""
            if peer_id:
                where_peer = "and f.subject_peer_id = ?"
                params.append(peer_id)
            params.append(limit)
            rows = conn.execute(
                f"""
                select f.*
                from facts_fts x
                join facts f on f.rowid = x.rowid
                where facts_fts match ?
                  and f.status = 'active'
                  {where_peer}
                order by bm25(facts_fts)
                limit ?
                """,
                params,
            ).fetchall()
            return [self._hydrate_fact(row) for row in rows]

    def set_card(
        self,
        *,
        subject_peer_id: str,
        observer_peer_id: str,
        items: list[str],
        scope: str = "global",
        scope_id: str = "",
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                insert into cards(subject_peer_id, observer_peer_id, scope, scope_id, content_json)
                values (?, ?, ?, ?, ?)
                on conflict(subject_peer_id, observer_peer_id, scope, scope_id) do update set
                  content_json = excluded.content_json,
                  updated_at = datetime('now')
                """,
                (subject_peer_id, observer_peer_id, scope, scope_id, self._json(items)),
            )
            row = conn.execute(
                """
                select * from cards
                where subject_peer_id = ? and observer_peer_id = ? and scope = ? and scope_id = ?
                """,
                (subject_peer_id, observer_peer_id, scope, scope_id),
            ).fetchone()
            assert row is not None
            data = dict(row)
            data["items"] = json.loads(data.pop("content_json") or "[]")
            return data

    def get_card(
        self,
        *,
        subject_peer_id: str,
        observer_peer_id: str,
        scope: str = "global",
        scope_id: str = "",
    ) -> list[str]:
        with self.connect() as conn:
            row = conn.execute(
                """
                select content_json from cards
                where subject_peer_id = ? and observer_peer_id = ? and scope = ? and scope_id = ?
                """,
                (subject_peer_id, observer_peer_id, scope, scope_id),
            ).fetchone()
            if row is None:
                return []
            return list(json.loads(row["content_json"] or "[]"))

    def build_context(
        self,
        *,
        subject_peer_id: str,
        observer_peer_id: str,
        session_id: str | None = None,
        query: str | None = None,
        max_facts: int = 8,
    ) -> str:
        card = self.get_card(subject_peer_id=subject_peer_id, observer_peer_id=observer_peer_id)
        facts = self.search(query or subject_peer_id, peer_id=subject_peer_id, limit=max_facts)
        if not facts:
            with self.connect() as conn:
                rows = conn.execute(
                    """
                    select * from facts
                    where subject_peer_id = ? and observer_peer_id = ? and status = 'active'
                    order by updated_at desc, created_at desc
                    limit ?
                    """,
                    (subject_peer_id, observer_peer_id, max_facts),
                ).fetchall()
                facts = [self._hydrate_fact(row) for row in rows]

        lines = ["# Local Memory", ""]
        lines.append(f"Subject peer: `{subject_peer_id}`")
        lines.append(f"Observer peer: `{observer_peer_id}`")
        if session_id:
            lines.append(f"Session: `{session_id}`")
        lines.append("")

        if card:
            lines.extend(["## Peer card", *[f"- {item}" for item in card], ""])

        if facts:
            lines.append("## Durable facts")
            for fact in facts:
                evidence = fact.get("evidence_message_ids") or []
                evidence_label = f", evidence={evidence}" if evidence else ""
                lines.append(
                    f"- {fact['content']} "
                    f"(kind={fact['kind']}, source={fact['source']}{evidence_label})"
                )
            lines.append("")

        return "\n".join(lines).strip()
