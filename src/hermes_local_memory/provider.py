from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from hermes_local_memory.candidate_review import (
    apply_candidate_review_patch,
    build_candidate_review_packet,
)
from hermes_local_memory.card_review import apply_card_review_patch, build_card_review_packet
from hermes_local_memory.consolidation import build_consolidation_plan, build_maintenance_plan
from hermes_local_memory.honcho_migration_review import (
    apply_honcho_migration_review_patch,
    build_honcho_migration_review_packet,
)
from hermes_local_memory.peer_review import apply_peer_review_patch, build_peer_review_packet
from hermes_local_memory.reflection import apply_reflection_patch, build_reflection_maintenance_plan
from hermes_local_memory.store import LocalMemoryStore

GET_CARD_SCHEMA = {
    "name": "memory_get_card",
    "description": "Retrieve the local compact peer card.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
        },
        "required": [],
    },
}

SET_CARD_SCHEMA = {
    "name": "memory_set_card",
    "description": "Explicitly replace the local compact peer card and return a diff.",
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
                "description": "New full card.",
            },
            "allow_empty": {
                "type": "boolean",
                "description": "Permit replacing the card with an empty list. Defaults to false.",
            },
        },
        "required": ["card"],
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

MAINTENANCE_SCHEMA = {
    "name": "memory_maintenance",
    "description": (
        "Preview or apply deterministic consolidation across all subject/observer pairs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
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

BUILD_PEER_REVIEW_PACKET_SCHEMA = {
    "name": "memory_build_peer_review_packet",
    "description": "Build a peer review packet for unresolved or unverified peer identities.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Maximum peers to include, default 100."},
        },
        "required": [],
    },
}

BUILD_REFLECTION_PACKETS_SCHEMA = {
    "name": "memory_build_reflection_packets",
    "description": "Build reflection packets for stale sessions before consolidation.",
    "parameters": {
        "type": "object",
        "properties": {
            "min_messages": {
                "type": "integer",
                "description": (
                    "Minimum unreflected messages before a session is included. Defaults to 20."
                ),
            },
            "max_messages": {
                "type": "integer",
                "description": "Maximum messages per reflection packet. Defaults to 100.",
            },
        },
        "required": [],
    },
}

APPLY_REFLECTION_PATCH_SCHEMA = {
    "name": "memory_apply_reflection_patch",
    "description": "Validate or apply an agent-produced reflection patch.",
    "parameters": {
        "type": "object",
        "properties": {
            "packet": {"type": "object", "description": "Reflection packet being reviewed."},
            "patch": {"type": "object", "description": "Reflection patch to validate/apply."},
            "apply": {"type": "boolean", "description": "Apply if valid. Defaults to false."},
        },
        "required": ["packet", "patch"],
    },
}

BUILD_CANDIDATE_REVIEW_PACKET_SCHEMA = {
    "name": "memory_build_candidate_review_packet",
    "description": "Build a candidate fact review packet for the current or specified peer.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
            "source": {"type": "string", "description": "Optional candidate fact source filter."},
            "limit": {"type": "integer", "description": "Maximum candidate facts, default 100."},
        },
        "required": [],
    },
}

APPLY_CANDIDATE_REVIEW_PATCH_SCHEMA = {
    "name": "memory_apply_candidate_review_patch",
    "description": "Validate or apply an agent-produced candidate review patch.",
    "parameters": {
        "type": "object",
        "properties": {
            "packet": {"type": "object", "description": "Candidate review packet."},
            "patch": {"type": "object", "description": "Candidate review patch to validate/apply."},
            "apply": {"type": "boolean", "description": "Apply if valid. Defaults to false."},
        },
        "required": ["packet", "patch"],
    },
}

BUILD_CARD_REVIEW_PACKET_SCHEMA = {
    "name": "memory_build_card_review_packet",
    "description": "Build a compact peer-card review packet for the current or specified peer.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
            "max_active": {"type": "integer", "description": "Maximum active facts, default 50."},
            "max_candidates": {
                "type": "integer",
                "description": "Maximum candidate facts, default 50.",
            },
        },
        "required": [],
    },
}

APPLY_CARD_REVIEW_PATCH_SCHEMA = {
    "name": "memory_apply_card_review_patch",
    "description": "Validate or apply an agent-produced full-card replacement patch.",
    "parameters": {
        "type": "object",
        "properties": {
            "packet": {"type": "object", "description": "Card review packet."},
            "patch": {"type": "object", "description": "Card review patch to validate/apply."},
            "apply": {"type": "boolean", "description": "Apply if valid. Defaults to false."},
        },
        "required": ["packet", "patch"],
    },
}

BUILD_HONCHO_MIGRATION_REVIEW_PACKET_SCHEMA = {
    "name": "memory_build_honcho_migration_review_packet",
    "description": "Build a first-migration packet for reviewing imported Honcho memories.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer alias or id. Defaults to current user.",
            },
            "source": {
                "type": "string",
                "description": "Imported Honcho candidate source filter.",
            },
            "max_candidates": {"type": "integer", "description": "Maximum candidate facts."},
            "max_active": {"type": "integer", "description": "Maximum active facts."},
        },
        "required": [],
    },
}

APPLY_HONCHO_MIGRATION_REVIEW_PATCH_SCHEMA = {
    "name": "memory_apply_honcho_migration_review_patch",
    "description": "Validate or apply an agent-produced Honcho migration review patch.",
    "parameters": {
        "type": "object",
        "properties": {
            "packet": {"type": "object", "description": "Honcho migration review packet."},
            "patch": {"type": "object", "description": "Honcho migration review patch."},
            "apply": {"type": "boolean", "description": "Apply if valid. Defaults to false."},
        },
        "required": ["packet", "patch"],
    },
}

APPLY_PEER_REVIEW_PATCH_SCHEMA = {
    "name": "memory_apply_peer_review_patch",
    "description": "Validate or apply an agent-produced peer-review patch.",
    "parameters": {
        "type": "object",
        "properties": {
            "packet": {"type": "object", "description": "Peer review packet."},
            "patch": {"type": "object", "description": "Peer review patch to validate/apply."},
            "apply": {"type": "boolean", "description": "Apply if valid. Defaults to false."},
        },
        "required": ["packet", "patch"],
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

        user_alias = f"{self.platform}:{raw_user_id}"
        sanitized_user_peer_id = self._sanitize_peer_id(f"{self.platform}-{raw_user_id}")
        existing_user_peer = self.store.resolve_peer(user_alias)
        self.user_peer_id = (
            existing_user_peer["id"] if existing_user_peer is not None else sanitized_user_peer_id
        )
        if existing_user_peer is not None and sanitized_user_peer_id != self.user_peer_id:
            self.store.merge_peer(
                sanitized_user_peer_id,
                self.user_peer_id,
                keep_source_alias=True,
                source="provider-runtime-reconciliation",
            )
        existing_assistant_peer = self.store.resolve_peer(agent_identity)
        self.assistant_peer_id = (
            existing_assistant_peer["id"]
            if existing_assistant_peer is not None
            else self._sanitize_peer_id(agent_identity)
        )
        if existing_user_peer is None:
            self.store.upsert_peer(self.user_peer_id, display_name=raw_user_id, kind="human")
        if existing_assistant_peer is None:
            self.store.upsert_peer(self.assistant_peer_id, display_name=agent_identity, kind="ai")
        if existing_user_peer is None:
            self.store.set_alias(
                user_alias,
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
            "Active. Use memory_get_card for compact peer cards, memory_set_card for "
            "explicit full-card replacement, memory_search for facts, memory_context "
            "to inspect injected context, and memory_conclude to save durable facts."
        )

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            GET_CARD_SCHEMA,
            SET_CARD_SCHEMA,
            SEARCH_SCHEMA,
            CONTEXT_SCHEMA,
            CONCLUDE_SCHEMA,
            CONSOLIDATE_SCHEMA,
            MAINTENANCE_SCHEMA,
            BUILD_PEER_REVIEW_PACKET_SCHEMA,
            APPLY_PEER_REVIEW_PATCH_SCHEMA,
            BUILD_REFLECTION_PACKETS_SCHEMA,
            APPLY_REFLECTION_PATCH_SCHEMA,
            BUILD_CANDIDATE_REVIEW_PACKET_SCHEMA,
            APPLY_CANDIDATE_REVIEW_PATCH_SCHEMA,
            BUILD_CARD_REVIEW_PACKET_SCHEMA,
            APPLY_CARD_REVIEW_PATCH_SCHEMA,
            BUILD_HONCHO_MIGRATION_REVIEW_PACKET_SCHEMA,
            APPLY_HONCHO_MIGRATION_REVIEW_PATCH_SCHEMA,
        ]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **_: Any) -> str:
        try:
            if tool_name == "memory_get_card":
                return self._handle_get_card(args)
            if tool_name == "memory_set_card":
                return self._handle_set_card(args)
            if tool_name == "memory_profile":
                return self._handle_profile_legacy(args)
            if tool_name == "memory_search":
                return self._handle_search(args)
            if tool_name == "memory_context":
                return self._handle_context(args)
            if tool_name == "memory_conclude":
                return self._handle_conclude(args)
            if tool_name == "memory_consolidate":
                return self._handle_consolidate(args)
            if tool_name == "memory_maintenance":
                return self._handle_maintenance(args)
            if tool_name in {"memory_build_peer_review_packet", "memory_peer_review"}:
                return self._handle_peer_review(args)
            if tool_name == "memory_apply_peer_review_patch":
                return self._handle_apply_peer_review_patch(args)
            if tool_name in {"memory_build_reflection_packets", "memory_reflection_maintenance"}:
                return self._handle_reflection_maintenance(args)
            if tool_name == "memory_apply_reflection_patch":
                return self._handle_apply_reflection_patch(args)
            if tool_name in {"memory_build_candidate_review_packet", "memory_candidate_review"}:
                return self._handle_candidate_review(args)
            if tool_name == "memory_apply_candidate_review_patch":
                return self._handle_apply_candidate_review_patch(args)
            if tool_name in {"memory_build_card_review_packet", "memory_card_review"}:
                return self._handle_card_review(args)
            if tool_name == "memory_apply_card_review_patch":
                return self._handle_apply_card_review_patch(args)
            if tool_name == "memory_build_honcho_migration_review_packet":
                return self._handle_honcho_migration_review(args)
            if tool_name == "memory_apply_honcho_migration_review_patch":
                return self._handle_apply_honcho_migration_review_patch(args)
        except Exception as exc:
            return self._error(str(exc))
        return self._error(f"unknown tool: {tool_name}")

    def _handle_get_card(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        peer_id = self._resolve_peer_id(args.get("peer"))
        current = store.get_card(subject_peer_id=peer_id, observer_peer_id=self.assistant_peer_id)
        return self._ok(peer=peer_id, card=current)

    def _handle_set_card(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        peer_id = self._resolve_peer_id(args.get("peer"))
        card = args.get("card")
        current = store.get_card(subject_peer_id=peer_id, observer_peer_id=self.assistant_peer_id)
        if card is None:
            return self._error("card is required")
        if not isinstance(card, list) or not all(isinstance(item, str) for item in card):
            return self._error("card must be a list of strings")
        if not card and not bool(args.get("allow_empty", False)):
            return self._error("empty card writes require allow_empty=true")
        store.set_card(
            subject_peer_id=peer_id,
            observer_peer_id=self.assistant_peer_id,
            items=card,
        )
        return self._ok(peer=peer_id, card=card, diff=_card_diff(current, card))

    def _handle_profile_legacy(self, args: dict[str, Any]) -> str:
        action = str(args.get("action") or "get").strip().lower()
        if action in {"", "get", "read"}:
            if args.get("card") is not None:
                return self._error("card writes require memory_set_card or action='set'")
            return self._handle_get_card(args)
        if action != "set":
            return self._error("action must be 'get' or 'set'")
        return self._handle_set_card(args)

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

    def _handle_maintenance(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        plan = build_maintenance_plan(
            store,
            promote_candidates=bool(args.get("promote_candidates", False)),
            apply=bool(args.get("apply", False)),
            limit=int(args.get("limit") or 500),
        )
        return self._ok(plan=_summarize_maintenance_plan(plan))

    def _handle_peer_review(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        packet = build_peer_review_packet(store, limit=int(args.get("limit") or 100))
        return self._ok(packet=packet)

    def _handle_reflection_maintenance(self, args: dict[str, Any]) -> str:
        store = self._require_store()
        plan = build_reflection_maintenance_plan(
            store,
            observer_peer_id=self.assistant_peer_id,
            min_messages=int(args.get("min_messages") or 20),
            max_messages=int(args.get("max_messages") or 100),
        )
        return self._ok(plan=plan)

    def _handle_apply_reflection_patch(self, args: dict[str, Any]) -> str:
        packet = args.get("packet")
        patch = args.get("patch")
        if not isinstance(packet, dict):
            return self._error("packet must be an object")
        if not isinstance(patch, dict):
            return self._error("patch must be an object")
        result = apply_reflection_patch(
            self._require_store(),
            packet,
            patch,
            apply=bool(args.get("apply", False)),
        )
        return self._ok(result=result)

    def _handle_candidate_review(self, args: dict[str, Any]) -> str:
        peer_id = self._resolve_peer_id(args.get("peer"))
        packet = build_candidate_review_packet(
            self._require_store(),
            subject_peer_id=peer_id,
            observer_peer_id=self.assistant_peer_id,
            source=args.get("source"),
            limit=int(args.get("limit") or 100),
        )
        return self._ok(packet=packet)

    def _handle_apply_candidate_review_patch(self, args: dict[str, Any]) -> str:
        packet = args.get("packet")
        patch = args.get("patch")
        if not isinstance(packet, dict):
            return self._error("packet must be an object")
        if not isinstance(patch, dict):
            return self._error("patch must be an object")
        result = apply_candidate_review_patch(
            self._require_store(),
            packet,
            patch,
            apply=bool(args.get("apply", False)),
        )
        return self._ok(result=result)

    def _handle_card_review(self, args: dict[str, Any]) -> str:
        peer_id = self._resolve_peer_id(args.get("peer"))
        packet = build_card_review_packet(
            self._require_store(),
            subject_peer_id=peer_id,
            observer_peer_id=self.assistant_peer_id,
            max_active=int(args.get("max_active") or 50),
            max_candidates=int(args.get("max_candidates") or 50),
        )
        return self._ok(packet=packet)

    def _handle_apply_card_review_patch(self, args: dict[str, Any]) -> str:
        packet = args.get("packet")
        patch = args.get("patch")
        if not isinstance(packet, dict):
            return self._error("packet must be an object")
        if not isinstance(patch, dict):
            return self._error("patch must be an object")
        result = apply_card_review_patch(
            self._require_store(),
            packet,
            patch,
            apply=bool(args.get("apply", False)),
        )
        return self._ok(result=result)

    def _handle_honcho_migration_review(self, args: dict[str, Any]) -> str:
        peer_id = self._resolve_peer_id(args.get("peer"))
        packet = build_honcho_migration_review_packet(
            self._require_store(),
            subject_peer_id=peer_id,
            observer_peer_id=self.assistant_peer_id,
            source=str(args.get("source") or "honcho-api-conclusion"),
            max_candidates=int(args.get("max_candidates") or 100),
            max_active=int(args.get("max_active") or 50),
        )
        return self._ok(packet=packet)

    def _handle_apply_honcho_migration_review_patch(self, args: dict[str, Any]) -> str:
        packet = args.get("packet")
        patch = args.get("patch")
        if not isinstance(packet, dict):
            return self._error("packet must be an object")
        if not isinstance(patch, dict):
            return self._error("patch must be an object")
        result = apply_honcho_migration_review_patch(
            self._require_store(),
            packet,
            patch,
            apply=bool(args.get("apply", False)),
        )
        return self._ok(result=result)

    def _handle_apply_peer_review_patch(self, args: dict[str, Any]) -> str:
        packet = args.get("packet")
        patch = args.get("patch")
        if not isinstance(packet, dict):
            return self._error("packet must be an object")
        if not isinstance(patch, dict):
            return self._error("patch must be an object")
        result = apply_peer_review_patch(
            self._require_store(),
            packet,
            patch,
            apply=bool(args.get("apply", False)),
        )
        return self._ok(result=result)

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


def _card_diff(before: list[str], after: list[str]) -> dict[str, list[str]]:
    return {
        "before": before,
        "after": after,
        "added": [item for item in after if item not in before],
        "removed": [item for item in before if item not in after],
    }


def _summarize_maintenance_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a compact tool result suitable for prompt injection/reporting."""

    pair_summaries = []
    for pair in plan.get("pairs", []):
        counts = pair.get("counts", {})
        if any(
            counts.get(key, 0)
            for key in ("candidate_promotions", "candidate_supersedes", "card_additions")
        ):
            pair_summaries.append(
                {
                    "subject_peer_id": pair.get("subject_peer_id"),
                    "observer_peer_id": pair.get("observer_peer_id"),
                    "counts": counts,
                    "writes": pair.get("writes", []),
                }
            )
    return {
        "mode": plan.get("mode"),
        "promote_candidates": plan.get("promote_candidates"),
        "counts": plan.get("counts", {}),
        "writes": plan.get("writes", []),
        "pairs_with_changes": pair_summaries,
    }
