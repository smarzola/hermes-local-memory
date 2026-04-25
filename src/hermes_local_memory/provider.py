from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from hermes_local_memory.consolidation import build_consolidation_plan
from hermes_local_memory.store import LocalMemoryStore

PROFILE_SCHEMA = {
    "name": "memory_profile",
    "description": "Retrieve or update the local compact peer card.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
            "card": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New full card. Omit to read current card.",
            },
        },
        "required": [],
    },
}

SEARCH_SCHEMA = {
    "name": "memory_search",
    "description": "Search local durable facts for the current or specified peer.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
            "limit": {"type": "integer", "description": "Maximum results, default 10."},
        },
        "required": ["query"],
    },
}

CONTEXT_SCHEMA = {
    "name": "memory_context",
    "description": "Show exactly what local memory context would be injected.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Optional focus query."},
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
        },
        "required": [],
    },
}

CONCLUDE_SCHEMA = {
    "name": "memory_conclude",
    "description": "Add a durable local memory fact about a peer.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
            "content": {"type": "string", "description": "Fact to store."},
            "kind": {"type": "string", "description": "Fact kind, e.g. preference/personal/note."},
            "source": {"type": "string", "description": "Fact source, default manual."},
        },
        "required": ["content"],
    },
}

CONSOLIDATE_SCHEMA = {
    "name": "memory_consolidate",
    "description": "Preview or apply deterministic local memory consolidation.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
            "promote_candidates": {
                "type": "boolean",
                "description": "Promote unique candidate facts. Defaults to false.",
            },
            "apply": {
                "type": "boolean",
                "description": "Apply the proposed changes. Defaults to false/dry-run.",
            },
            "limit": {"type": "integer", "description": "Maximum facts per status to inspect."},
        },
        "required": [],
    },
}


class LocalMemoryProvider:
    """Hermes-compatible local memory provider.

    This class intentionally mirrors the subset of Hermes' MemoryProvider lifecycle
    we need without importing Hermes. That keeps the package independently testable
    while making it straightforward to wrap or subclass inside Hermes.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path is not None else None
        self.store: LocalMemoryStore | None = None
        self.session_id = ""
        self.user_peer_id = "user-default"
        self.assistant_peer_id = "assistant-default"
        self.platform = "cli"
        self._last_user_message_ids: list[int] = []

    @property
    def name(self) -> str:
        return "local"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        hermes_home = Path(kwargs.get("hermes_home") or Path.home() / ".hermes")
        self.db_path = self.db_path or hermes_home / "memory" / "local_memory.sqlite"
        self.store = LocalMemoryStore(self.db_path)
        self.store.initialize()

        self.session_id = session_id
        self.platform = str(kwargs.get("platform") or "cli")
        raw_user_id = str(kwargs.get("user_id") or "default")
        agent_identity = str(kwargs.get("agent_identity") or "assistant")
        session_title = kwargs.get("session_title")

        self.user_peer_id = self._sanitize_peer_id(f"{self.platform}-{raw_user_id}")
        self.assistant_peer_id = self._sanitize_peer_id(agent_identity)
        self.store.upsert_peer(self.user_peer_id, display_name=raw_user_id, kind="human")
        self.store.upsert_peer(self.assistant_peer_id, display_name=agent_identity, kind="ai")
        self.store.set_alias(
            f"{self.platform}:{raw_user_id}",
            peer_id=self.user_peer_id,
            source=self.platform,
            verified=True,
        )
        self.store.set_alias("user", peer_id=self.user_peer_id, source="builtin", verified=True)
        self.store.set_alias("ai", peer_id=self.assistant_peer_id, source="builtin", verified=True)
        self.store.upsert_session(
            session_id,
            profile_id="default",
            platform=self.platform,
            external_id=raw_user_id,
            title=str(session_title) if session_title else None,
        )

    @staticmethod
    def _sanitize_peer_id(value: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
        return sanitized or "peer-default"

    def _require_store(self) -> LocalMemoryStore:
        if self.store is None:
            raise RuntimeError("LocalMemoryProvider.initialize() must be called before use")
        return self.store

    def _resolve_peer_id(self, peer: str | None) -> str:
        store = self._require_store()
        candidate = peer or "user"
        if candidate == "user":
            return self.user_peer_id
        if candidate == "ai":
            return self.assistant_peer_id
        resolved = store.resolve_peer(candidate)
        return resolved["id"] if resolved else self._sanitize_peer_id(candidate)

    @staticmethod
    def _ok(**payload: Any) -> str:
        return json.dumps({"success": True, **payload}, ensure_ascii=False)

    @staticmethod
    def _error(message: str) -> str:
        return json.dumps({"success": False, "error": message}, ensure_ascii=False)

    def system_prompt_block(self) -> str:
        return (
            "# Local Memory\n"
            "Active. Use memory_profile for compact profile cards, memory_search for facts, "
            "memory_context to inspect injected context, and memory_conclude to save durable facts."
        )

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            PROFILE_SCHEMA,
            SEARCH_SCHEMA,
            CONTEXT_SCHEMA,
            CONCLUDE_SCHEMA,
            CONSOLIDATE_SCHEMA,
        ]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **_: Any) -> str:
        try:
            if tool_name == "memory_profile":
                return self._handle_profile(args)
            if tool_name == "memory_search":
                return self._handle_search(args)
            if tool_name == "memory_context":
                return self._handle_context(args)
            if tool_name == "memory_conclude":
                return self._handle_conclude(args)
            if tool_name == "memory_consolidate":
                return self._handle_consolidate(args)
        except Exception as exc:
            return self._error(str(exc))
        return self._error(f"unknown tool: {tool_name}")

    def _handle_profile(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        peer_id = self._resolve_peer_id(args.get("peer"))
        card = args.get("card")
        if card is not None:
            if not isinstance(card, list) or not all(isinstance(item, str) for item in card):
                return self._error("card must be a list of strings")
            store.set_card(
                subject_peer_id=peer_id,
                observer_peer_id=self.assistant_peer_id,
                items=card,
            )
            return self._ok(peer=peer_id, card=card)
        return self._ok(
            peer=peer_id,
            card=store.get_card(subject_peer_id=peer_id, observer_peer_id=self.assistant_peer_id),
        )

    def _handle_search(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        query = str(args.get("query") or "").strip()
        if not query:
            return self._error("query is required")
        peer_id = self._resolve_peer_id(args.get("peer"))
        limit = int(args.get("limit") or 10)
        return self._ok(results=store.search(query, peer_id=peer_id, limit=limit))

    def _handle_context(self, args: dict[str, Any]) -> str:
        query = str(args.get("query") or "").strip() or None
        peer_id = self._resolve_peer_id(args.get("peer"))
        return self._ok(context=self._build_context(peer_id=peer_id, query=query))

    def _handle_conclude(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        content = str(args.get("content") or "").strip()
        if not content:
            return self._error("content is required")
        peer_id = self._resolve_peer_id(args.get("peer"))
        fact = store.add_fact(
            subject_peer_id=peer_id,
            observer_peer_id=self.assistant_peer_id,
            content=content,
            kind=str(args.get("kind") or "note"),
            source=str(args.get("source") or "manual"),
            evidence_message_ids=self._last_user_message_ids,
        )
        return self._ok(fact=fact)

    def _handle_consolidate(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        peer_id = self._resolve_peer_id(args.get("peer"))
        plan = build_consolidation_plan(
            store,
            subject_peer_id=peer_id,
            observer_peer_id=self.assistant_peer_id,
            promote_candidates=bool(args.get("promote_candidates", False)),
            apply=bool(args.get("apply", False)),
            limit=int(args.get("limit") or 500),
        )
        return self._ok(plan=plan)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        store = self._require_store()
        sid = session_id or self.session_id
        user_msg = store.add_message(
            session_id=sid,
            peer_id=self.user_peer_id,
            role="user",
            content=user_content,
        )
        store.add_message(
            session_id=sid,
            peer_id=self.assistant_peer_id,
            role="assistant",
            content=assistant_content,
        )
        self._last_user_message_ids = [int(user_msg["id"])]

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._is_trivial_prompt(query):
            return ""
        return self._build_context(
            peer_id=self.user_peer_id,
            query=query,
            session_id=session_id or self.session_id,
        )

    def _build_context(
        self,
        *,
        peer_id: str,
        query: str | None,
        session_id: str | None = None,
    ) -> str:
        store = self._require_store()
        return store.build_context(
            subject_peer_id=peer_id,
            observer_peer_id=self.assistant_peer_id,
            session_id=session_id or self.session_id,
            query=query,
        )

    @staticmethod
    def _is_trivial_prompt(text: str) -> bool:
        stripped = (text or "").strip().lower()
        return stripped in {"", "ok", "okay", "yes", "no", "thanks", "thank you", "continue"}
