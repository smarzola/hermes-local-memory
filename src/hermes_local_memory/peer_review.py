from __future__ import annotations

import json
from typing import Any

from hermes_local_memory.store import LocalMemoryStore

PEER_REVIEW_PACKET_SCHEMA = "hermes-local-memory.peer-review-packet.v1"
PEER_REVIEW_PATCH_SCHEMA = "hermes-local-memory.peer-review-patch.v1"


def build_peer_review_packet(
    store: LocalMemoryStore,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    peers = store.list_peers()
    aliases_by_peer = _aliases_by_peer(store)
    unverified = [
        _peer_with_aliases(peer, aliases_by_peer.get(peer["id"], []))
        for peer in peers
        if _needs_peer_review(peer, aliases_by_peer.get(peer["id"], []))
    ][:limit]
    canonical = [
        _peer_with_aliases(peer, aliases_by_peer.get(peer["id"], []))
        for peer in peers
        if not _looks_ephemeral_peer(peer) and peer["id"] not in {item["id"] for item in unverified}
    ][:limit]
    return {
        "schema": PEER_REVIEW_PACKET_SCHEMA,
        "unverified_peers": unverified,
        "candidate_canonical_peers": canonical,
        "rules": {
            "patch_schema": PEER_REVIEW_PATCH_SCHEMA,
            "agent_controls_peer_mapping": True,
            "ask_human_when_ambiguous": True,
            "prefer_alias_moves_over_raw_history_rewrites": True,
            "preserve_raw_history": True,
            "human_prompts_are_reported_not_written": True,
        },
    }


def validate_peer_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if patch.get("schema") not in (None, PEER_REVIEW_PATCH_SCHEMA):
        errors.append(f"schema must be {PEER_REVIEW_PATCH_SCHEMA}")

    packet_peer_ids = {peer["id"] for peer in packet.get("unverified_peers", [])}
    packet_aliases = {
        alias
        for peer in packet.get("unverified_peers", [])
        for alias in peer.get("aliases", [])
    }
    seen_aliases: set[str] = set()
    for item in patch.get("alias_moves", []):
        if not isinstance(item, dict):
            errors.append("alias_moves items must be objects")
            continue
        alias = item.get("alias")
        target = item.get("to_peer_id")
        if not isinstance(alias, str) or not alias.strip():
            errors.append("alias_moves items require alias")
            continue
        if alias in seen_aliases:
            errors.append(f"alias can only appear in one peer review action: {alias}")
        seen_aliases.add(alias)
        if alias not in packet_aliases:
            errors.append(f"alias not present in peer review packet: {alias}")
        if not isinstance(target, str) or not target.strip():
            errors.append(f"alias move target is required for alias: {alias}")
        elif store.resolve_peer(target) is None:
            errors.append(f"unknown target peer id: {target}")
        confidence = item.get("confidence", 1.0)
        if not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
            errors.append(f"confidence must be between 0 and 1 for alias: {alias}")

    seen_peer_merges: set[str] = set()
    for item in patch.get("peer_merges", []):
        if not isinstance(item, dict):
            errors.append("peer_merges items must be objects")
            continue
        from_peer_id = item.get("from_peer_id")
        to_peer_id = item.get("to_peer_id")
        if not isinstance(from_peer_id, str) or not from_peer_id.strip():
            errors.append("peer_merges items require from_peer_id")
            continue
        if from_peer_id in seen_peer_merges:
            errors.append(f"peer can only appear in one peer merge action: {from_peer_id}")
        seen_peer_merges.add(from_peer_id)
        if from_peer_id not in packet_peer_ids:
            errors.append(f"merge source peer not present in peer review packet: {from_peer_id}")
        if not isinstance(to_peer_id, str) or not to_peer_id.strip():
            errors.append(f"peer merge target is required for peer: {from_peer_id}")
        elif store.resolve_peer(to_peer_id) is None:
            errors.append(f"unknown target peer id: {to_peer_id}")
        elif to_peer_id == from_peer_id:
            errors.append(f"peer merge target must differ from source: {from_peer_id}")
        if not isinstance(item.get("keep_source_alias", True), bool):
            errors.append(f"keep_source_alias must be boolean for peer: {from_peer_id}")
        if not isinstance(item.get("verified", True), bool):
            errors.append(f"verified must be boolean for peer: {from_peer_id}")

    for item in patch.get("human_prompts", []):
        if not isinstance(item, dict):
            errors.append("human_prompts items must be objects")
            continue
        peer_id = item.get("peer_id")
        question = item.get("question")
        if not isinstance(peer_id, str) or not peer_id.strip():
            errors.append("human_prompts items require peer_id")
            continue
        if peer_id not in packet_peer_ids:
            errors.append(f"human prompt peer not present in peer review packet: {peer_id}")
        if not isinstance(question, str) or not question.strip():
            errors.append(f"human prompt question is required for peer: {peer_id}")
        aliases = item.get("suggested_aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
            errors.append(f"suggested_aliases must be a list of strings for peer: {peer_id}")

    return {"valid": not errors, "errors": errors}


def apply_peer_review_patch(
    store: LocalMemoryStore,
    packet: dict[str, Any],
    patch: dict[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    validation = validate_peer_review_patch(store, packet, patch)
    prompts = _normalized_human_prompts(patch.get("human_prompts", []))
    peer_merges = patch.get("peer_merges", [])
    writes = {"aliases_moved": 0, "human_prompts_recorded": len(prompts)}
    if peer_merges:
        writes["peers_merged"] = 0
        writes["peer_merge_results"] = []
    if apply and validation["valid"]:
        for item in patch.get("alias_moves", []):
            store.set_alias(
                item["alias"],
                peer_id=item["to_peer_id"],
                source=item.get("source") or "agent-peer-review",
                confidence=float(item.get("confidence", 1.0)),
                verified=bool(item.get("verified", False)),
            )
            writes["aliases_moved"] += 1
        for item in patch.get("peer_merges", []):
            result = store.merge_peer(
                item["from_peer_id"],
                item["to_peer_id"],
                keep_source_alias=bool(item.get("keep_source_alias", True)),
                source=item.get("source") or "agent-peer-review",
            )
            writes["peers_merged"] += 1 if result.get("deleted") else 0
            writes["peer_merge_results"].append(result)

    return {
        "mode": "apply" if apply else "dry-run",
        "schema": PEER_REVIEW_PATCH_SCHEMA,
        "validation": validation,
        "writes": writes if apply and validation["valid"] else [],
        "human_prompts": prompts,
    }


def _aliases_by_peer(store: LocalMemoryStore) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for alias in store.list_aliases():
        result.setdefault(alias["peer_id"], []).append(alias)
    for aliases in result.values():
        aliases.sort(key=lambda item: item["alias"])
    return result


def _peer_with_aliases(peer: dict[str, Any], aliases: list[dict[str, Any]]) -> dict[str, Any]:
    row = dict(peer)
    row["aliases"] = [alias["alias"] for alias in aliases]
    row["verified_aliases"] = [alias["alias"] for alias in aliases if alias.get("verified")]
    row["unverified_aliases"] = [alias["alias"] for alias in aliases if not alias.get("verified")]
    row["metadata"] = _decode_metadata(row.pop("metadata_json", None))
    return row


def _needs_peer_review(peer: dict[str, Any], aliases: list[dict[str, Any]]) -> bool:
    return _looks_ephemeral_peer(peer) or any(not alias.get("verified") for alias in aliases)


def _looks_ephemeral_peer(peer: dict[str, Any]) -> bool:
    peer_id = str(peer.get("id") or "")
    metadata = _decode_metadata(peer.get("metadata_json"))
    return (
        peer_id.startswith("telegram-")
        or peer_id.startswith("honcho-")
        or bool(metadata.get("external_id"))
    )


def _decode_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _normalized_human_prompts(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    prompts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompts.append(
            {
                "peer_id": item.get("peer_id"),
                "question": item.get("question"),
                "suggested_aliases": item.get("suggested_aliases", []),
            }
        )
    return prompts
