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

    def merge_peer(
        self,
        source_peer_id: str,
        target_peer_id: str,
        *,
        keep_source_alias: bool = False,
        source: str = "peer-merge",
    ) -> dict[str, Any]:
        if source_peer_id == target_peer_id:
            return {
                "source_peer_id": source_peer_id,
                "target_peer_id": target_peer_id,
                "deleted": False,
            }
        with self.connect() as conn:
            source_peer = conn.execute(
                "select * from peers where id = ?",
                (source_peer_id,),
            ).fetchone()
            target = conn.execute("select * from peers where id = ?", (target_peer_id,)).fetchone()
            if source_peer is None:
                return {
                    "source_peer_id": source_peer_id,
                    "target_peer_id": target_peer_id,
                    "deleted": False,
                }
            if target is None:
                raise ValueError(f"unknown target peer id: {target_peer_id}")
            counts = {
                "aliases": conn.execute(
                    "select count(*) from peer_aliases where peer_id = ?",
                    (source_peer_id,),
                ).fetchone()[0],
                "messages": conn.execute(
                    "select count(*) from messages where peer_id = ?",
                    (source_peer_id,),
                ).fetchone()[0],
                "session_peers": conn.execute(
                    "select count(*) from session_peers where peer_id = ?",
                    (source_peer_id,),
                ).fetchone()[0],
                "subject_facts": conn.execute(
                    "select count(*) from facts where subject_peer_id = ?",
                    (source_peer_id,),
                ).fetchone()[0],
                "observer_facts": conn.execute(
                    "select count(*) from facts where observer_peer_id = ?",
                    (source_peer_id,),
                ).fetchone()[0],
                "subject_cards": conn.execute(
                    "select count(*) from cards where subject_peer_id = ?",
                    (source_peer_id,),
                ).fetchone()[0],
                "observer_cards": conn.execute(
                    "select count(*) from cards where observer_peer_id = ?",
                    (source_peer_id,),
                ).fetchone()[0],
            }
            conn.execute(
                "update peer_aliases set peer_id = ? where peer_id = ?",
                (target_peer_id, source_peer_id),
            )
            conn.execute(
                "update messages set peer_id = ? where peer_id = ?",
                (target_peer_id, source_peer_id),
            )
            for row in conn.execute(
                "select session_id, role from session_peers where peer_id = ?",
                (source_peer_id,),
            ).fetchall():
                conn.execute(
                    """
                    insert or ignore into session_peers(session_id, peer_id, role)
                    values (?, ?, ?)
                    """,
                    (row["session_id"], target_peer_id, row["role"]),
                )
            conn.execute("delete from session_peers where peer_id = ?", (source_peer_id,))
            conn.execute(
                "update facts set subject_peer_id = ? where subject_peer_id = ?",
                (target_peer_id, source_peer_id),
            )
            conn.execute(
                "update facts set observer_peer_id = ? where observer_peer_id = ?",
                (target_peer_id, source_peer_id),
            )
            conn.execute(
                "delete from cards where subject_peer_id = ? or observer_peer_id = ?",
                (source_peer_id, source_peer_id),
            )
            conn.execute("delete from peers where id = ?", (source_peer_id,))
            if keep_source_alias:
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
                    (source_peer_id, target_peer_id, source, 1.0, 1),
                )
            return {
                "source_peer_id": source_peer_id,
                "target_peer_id": target_peer_id,
                "deleted": True,
                "source_alias_added": keep_source_alias,
                "moved": counts,
            }

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

    def get_fact(self, fact_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from facts where id = ?", (fact_id,)).fetchone()
            return self._hydrate_fact(row) if row is not None else None

    def update_fact_status(self, fact_id: str, status: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                update facts
                set status = ?, updated_at = datetime('now')
                where id = ?
                """,
                (status, fact_id),
            )
            row = conn.execute("select * from facts where id = ?", (fact_id,)).fetchone()
            if row is None:
                raise KeyError(f"fact not found: {fact_id}")
            return self._hydrate_fact(row)

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

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from sessions where id = ?", (session_id,)).fetchone()
            return self._row_to_dict(row)

    def list_session_participants(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select sp.session_id, sp.peer_id, sp.role, p.display_name, p.kind
                from session_peers sp
                join peers p on p.id = sp.peer_id
                where sp.session_id = ? and sp.left_at is null
                order by sp.role, p.display_name collate nocase, p.id
                """,
                (session_id,),
            ).fetchall()
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

    def list_messages_after(
        self,
        *,
        session_id: str,
        after_message_id: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from messages
                where session_id = ? and id > ?
                order by id asc
                limit ?
                """,
                (session_id, after_message_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def count_messages_after(self, *, session_id: str, after_message_id: int = 0) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                select count(*) as count
                from messages
                where session_id = ? and id > ?
                """,
                (session_id, after_message_id),
            ).fetchone()
            return int(row["count"] if row is not None else 0)

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

    def message_exists_by_source_id(self, source_message_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "select 1 from messages where source_message_id = ? limit 1",
                (source_message_id,),
            ).fetchone()
            return row is not None

    def fact_exists(self, fact_id: str) -> bool:
        return self.get_fact(fact_id) is not None

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

    def add_summary(
        self,
        *,
        scope: str,
        scope_id: str,
        content: str,
        covered_from_message_id: int | None = None,
        covered_to_message_id: int | None = None,
        model: str | None = None,
        summary_id: str | None = None,
    ) -> dict[str, Any]:
        summary_id = summary_id or self._new_id("summary")
        with self.connect() as conn:
            conn.execute(
                """
                insert into summaries(
                  id, scope, scope_id, content, covered_from_message_id,
                  covered_to_message_id, model
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    scope,
                    scope_id,
                    content,
                    covered_from_message_id,
                    covered_to_message_id,
                    model,
                ),
            )
            row = conn.execute("select * from summaries where id = ?", (summary_id,)).fetchone()
            assert row is not None
            return dict(row)

    def list_summaries(
        self,
        *,
        scope: str | None = None,
        scope_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if scope_id:
            clauses.append("scope_id = ?")
            params.append(scope_id)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from summaries
                {where}
                order by updated_at desc, created_at desc, id
                limit ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def last_summary_to_message_id(self, *, scope: str, scope_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select max(covered_to_message_id) as last_id
                from summaries
                where scope = ? and scope_id = ? and covered_to_message_id is not null
                """,
                (scope, scope_id),
            ).fetchone()
            if row is None or row["last_id"] is None:
                return None
            return int(row["last_id"])

    def build_context(
        self,
        *,
        subject_peer_id: str,
        observer_peer_id: str,
        session_id: str | None = None,
        query: str | None = None,
        max_facts: int = 8,
    ) -> str:
        subject = self.resolve_peer(subject_peer_id)
        observer = self.resolve_peer(observer_peer_id)
        session = self.get_session(session_id) if session_id else None
        aliases = self._aliases_for_peer(subject_peer_id)
        card = self.get_card(subject_peer_id=subject_peer_id, observer_peer_id=observer_peer_id)
        durable_facts = self._recent_active_facts(
            subject_peer_id=subject_peer_id,
            observer_peer_id=observer_peer_id,
            limit=max_facts,
        )
        retrieved = self.search(query, peer_id=subject_peer_id, limit=max_facts) if query else []
        retrieved = [
            fact
            for fact in retrieved
            if fact["observer_peer_id"] == observer_peer_id
            and fact["id"] not in {item["id"] for item in durable_facts}
        ]
        summary = self._latest_session_summary(session_id) if session_id else None

        subject_name = subject["display_name"] if subject else subject_peer_id
        observer_name = observer["display_name"] if observer else observer_peer_id
        lines = ["# Local Memory", ""]
        lines.extend(
            [
                "## Identity",
                f"Subject peer: `{subject_peer_id}`",
                f"Subject display name: {subject_name}",
                f"Observer peer: `{observer_peer_id}`",
                f"Observer display name: {observer_name}",
            ]
        )
        if aliases:
            lines.append("Aliases: " + ", ".join(f"`{alias}`" for alias in aliases[:8]))
        if session_id:
            lines.append(f"Session: `{session_id}`")
            if session and session.get("title"):
                lines.append(f"Session title: {session['title']}")
        lines.append("")

        lines.append("## Compact peer card")
        lines.extend([f"- {item}" for item in card] if card else ["(no card)"])
        lines.append("")

        lines.append("## Durable facts")
        if durable_facts:
            for fact in durable_facts:
                lines.append(self._format_fact_line(fact))
        else:
            lines.append("(no active facts)")
        lines.append("")

        if summary:
            lines.append("## Current session summary")
            covered = _format_covered_range(summary)
            model = f", model={summary['model']}" if summary.get("model") else ""
            lines.append(f"- {summary['content']} (covered={covered}{model})")
            lines.append("")

        if retrieved:
            lines.append("## Relevant retrieved memories")
            for fact in retrieved:
                lines.append(self._format_fact_line(fact))
            lines.append("")

        return "\n".join(lines).strip()

    def _aliases_for_peer(self, peer_id: str) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select alias
                from peer_aliases
                where peer_id = ?
                order by verified desc, alias
                """,
                (peer_id,),
            ).fetchall()
            return [str(row["alias"]) for row in rows]

    def _recent_active_facts(
        self,
        *,
        subject_peer_id: str,
        observer_peer_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from facts
                where subject_peer_id = ? and observer_peer_id = ? and status = 'active'
                order by updated_at desc, created_at desc, id
                limit ?
                """,
                (subject_peer_id, observer_peer_id, limit),
            ).fetchall()
            return [self._hydrate_fact(row) for row in rows]

    def _latest_session_summary(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select * from summaries
                where scope = 'session' and scope_id = ?
                order by covered_to_message_id desc, updated_at desc, created_at desc
                limit 1
                """,
                (session_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    @staticmethod
    def _format_fact_line(fact: dict[str, Any]) -> str:
        evidence = fact.get("evidence_message_ids") or []
        evidence_label = f", evidence={evidence}" if evidence else ""
        return (
            f"- {fact['content']} "
            f"(kind={fact['kind']}, source={fact['source']}{evidence_label})"
        )


def _format_covered_range(summary: dict[str, Any]) -> str:
    start = summary.get("covered_from_message_id")
    end = summary.get("covered_to_message_id")
    if start is None and end is None:
        return "unknown"
    if start is None:
        return f"through {end}"
    if end is None:
        return f"from {start}"
    return f"{start}-{end}"
