from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hermes_local_memory.candidate_review import (
    apply_candidate_review_patch,
    build_candidate_review_packet,
)
from hermes_local_memory.card_review import apply_card_review_patch, build_card_review_packet
from hermes_local_memory.consolidation import (
    apply_consolidation_patch,
    build_consolidation_packet,
    build_consolidation_plan,
    build_maintenance_plan,
)
from hermes_local_memory.hermes_plugin import write_plugin_shim
from hermes_local_memory.honcho_api import HonchoApiClient, export_honcho_api
from hermes_local_memory.honcho_import import (
    apply_honcho_import_plan,
    load_identity_map,
    plan_honcho_export_import,
    plan_honcho_import,
)
from hermes_local_memory.reflection import (
    apply_reflection_patch,
    build_reflection_maintenance_plan,
    build_reflection_packet,
)
from hermes_local_memory.store import LocalMemoryStore


def default_db_path() -> Path:
    return Path.home() / ".hermes" / "memory" / "local_memory.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-local-memory")
    parser.add_argument(
        "--db",
        default=str(default_db_path()),
        help="Local Memory SQLite DB path, default: ~/.hermes/memory/local_memory.sqlite",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install-shim", help="Install the Hermes memory plugin shim")
    install.add_argument(
        "--hermes-home",
        default=str(Path.home() / ".hermes"),
        help="Hermes home directory, default: ~/.hermes",
    )
    install.add_argument(
        "--package-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Package src root to add to the shim sys.path",
    )

    _add_readonly_table_command(sub, "peers", "List peers")
    _add_readonly_table_command(sub, "aliases", "List peer aliases")
    _add_readonly_table_command(sub, "sessions", "List sessions")

    cards = _add_readonly_table_command(sub, "cards", "List peer cards")
    cards.add_argument("--peer", help="Filter by subject peer id or alias")
    cards.add_argument("--observer", help="Filter by observer peer id or alias")
    cards.add_argument("--limit", type=int, default=100, help="Maximum cards, default: 100")

    messages = _add_readonly_table_command(sub, "messages", "List raw messages")
    messages.add_argument("--session", help="Filter by session id")
    messages.add_argument("--peer", help="Filter by peer id or alias")
    messages.add_argument("--limit", type=int, default=50, help="Maximum messages, default: 50")

    facts = _add_readonly_table_command(sub, "facts", "List durable facts")
    facts.add_argument("--peer", help="Filter by peer id or alias")
    facts.add_argument("--observer", help="Filter by observer peer id or alias")
    facts.add_argument("--status", default="active", help="Filter by status, default: active")
    facts.add_argument("--limit", type=int, default=100, help="Maximum facts, default: 100")

    search = sub.add_parser("search", help="Search durable facts")
    search.add_argument("query", help="Search query")
    search.add_argument("--peer", help="Filter by peer id or alias")
    search.add_argument("--limit", type=int, default=10, help="Maximum results, default: 10")
    search.add_argument("--json", action="store_true", help="Print JSON")

    context = sub.add_parser("context", help="Render inspectable local memory context")
    context.add_argument("--peer", required=True, help="Subject peer id or alias")
    context.add_argument("--observer", required=True, help="Observer peer id or alias")
    context.add_argument("--session", help="Optional session id")
    context.add_argument("--query", help="Optional focus query")

    consolidate = sub.add_parser(
        "consolidate",
        help="Preview or apply deterministic memory consolidation",
    )
    consolidate.add_argument("--peer", required=True, help="Subject peer id or alias")
    consolidate.add_argument("--observer", required=True, help="Observer peer id or alias")
    consolidate.add_argument(
        "--promote-candidates",
        action="store_true",
        help="Promote unique candidate facts",
    )
    mode = consolidate.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only; do not write")
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply proposed promotions/supersedes/card update",
    )
    consolidate.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum facts per status to inspect",
    )
    consolidate.add_argument("--json", action="store_true", help="Print JSON")

    packet = sub.add_parser("consolidation-packet", help="Build an agent review packet")
    packet.add_argument("--peer", required=True, help="Subject peer id or alias")
    packet.add_argument("--observer", required=True, help="Observer peer id or alias")
    packet.add_argument("--max-candidates", type=int, default=100)
    packet.add_argument("--max-active", type=int, default=100)
    packet.add_argument("--json", action="store_true", help="Print JSON")

    apply_patch = sub.add_parser("apply-patch", help="Validate or apply a consolidation patch")
    apply_patch.add_argument("patch_file", help="Path to consolidation patch JSON")
    patch_mode = apply_patch.add_mutually_exclusive_group()
    patch_mode.add_argument("--dry-run", action="store_true", help="Validate only")
    patch_mode.add_argument("--apply", action="store_true", help="Apply patch")
    apply_patch.add_argument("--json", action="store_true", help="Print JSON")

    candidate_packet = sub.add_parser(
        "candidate-review-packet",
        help="Build an agent packet for safe candidate fact review",
    )
    candidate_packet.add_argument("--peer", required=True, help="Subject peer id or alias")
    candidate_packet.add_argument("--observer", required=True, help="Observer peer id or alias")
    candidate_packet.add_argument("--source", help="Optional candidate fact source filter")
    candidate_packet.add_argument("--limit", type=int, default=100)
    candidate_packet.add_argument("--json", action="store_true", help="Print JSON")

    apply_candidate = sub.add_parser(
        "apply-candidate-review-patch",
        help="Validate or apply a candidate review patch",
    )
    apply_candidate.add_argument("patch_file", help="Path to candidate review patch JSON")
    candidate_mode = apply_candidate.add_mutually_exclusive_group()
    candidate_mode.add_argument("--dry-run", action="store_true")
    candidate_mode.add_argument("--apply", action="store_true")
    apply_candidate.add_argument("--json", action="store_true", help="Print JSON")

    card_packet = sub.add_parser(
        "card-review-packet",
        help="Build an agent packet for compact peer-card cleanup during migration",
    )
    card_packet.add_argument("--peer", required=True, help="Subject peer id or alias")
    card_packet.add_argument("--observer", required=True, help="Observer peer id or alias")
    card_packet.add_argument("--max-active", type=int, default=50)
    card_packet.add_argument("--max-candidates", type=int, default=50)
    card_packet.add_argument("--json", action="store_true", help="Print JSON")

    apply_card = sub.add_parser(
        "apply-card-review-patch",
        help="Validate or apply a full-card cleanup patch",
    )
    apply_card.add_argument("patch_file", help="Path to card review patch JSON")
    card_mode = apply_card.add_mutually_exclusive_group()
    card_mode.add_argument("--dry-run", action="store_true")
    card_mode.add_argument("--apply", action="store_true")
    apply_card.add_argument("--json", action="store_true", help="Print JSON")

    maintenance = sub.add_parser("maintenance", help="Run consolidation across all pairs")
    maintenance.add_argument("--promote-candidates", action="store_true")
    maintenance.add_argument("--limit", type=int, default=500)
    maintenance_mode = maintenance.add_mutually_exclusive_group()
    maintenance_mode.add_argument("--dry-run", action="store_true")
    maintenance_mode.add_argument("--apply", action="store_true")
    maintenance.add_argument("--json", action="store_true", help="Print JSON")

    reflection_packet = sub.add_parser("reflection-packet", help="Build an agent reflection packet")
    reflection_packet.add_argument("--session", required=True, help="Session id to review")
    reflection_packet.add_argument("--observer", required=True, help="Observer peer id or alias")
    reflection_packet.add_argument(
        "--since-message-id",
        type=int,
        help="Only include messages after this id",
    )
    reflection_packet.add_argument("--max-messages", type=int, default=100)
    reflection_packet.add_argument("--json", action="store_true", help="Print JSON")

    apply_reflection = sub.add_parser(
        "apply-reflection-patch",
        help="Validate or apply a reflection patch",
    )
    apply_reflection.add_argument("patch_file", help="Path to reflection patch JSON")
    reflection_mode = apply_reflection.add_mutually_exclusive_group()
    reflection_mode.add_argument("--dry-run", action="store_true")
    reflection_mode.add_argument("--apply", action="store_true")
    apply_reflection.add_argument("--json", action="store_true", help="Print JSON")

    reflection_maintenance = sub.add_parser(
        "reflection-maintenance",
        help="Build reflection packets for stale sessions",
    )
    reflection_maintenance.add_argument(
        "--observer",
        required=True,
        help="Observer peer id or alias",
    )
    reflection_maintenance.add_argument("--min-messages", type=int, default=20)
    reflection_maintenance.add_argument("--max-messages", type=int, default=100)
    reflection_maintenance.add_argument("--json", action="store_true", help="Print JSON")

    alias = sub.add_parser("alias", help="Mutate aliases explicitly")
    alias_sub = alias.add_subparsers(dest="alias_command", required=True)
    alias_add = alias_sub.add_parser("add", help="Add or replace an alias mapping")
    alias_add.add_argument("alias")
    alias_add.add_argument("--peer", required=True, help="Target peer id or alias")
    alias_add.add_argument("--source", default="manual")
    alias_add.add_argument("--confidence", type=float, default=1.0)
    alias_add.add_argument("--verified", action="store_true")
    alias_add.add_argument("--json", action="store_true")
    alias_move = alias_sub.add_parser("move", help="Move an alias to another peer")
    alias_move.add_argument("alias")
    alias_move.add_argument("--peer", required=True, help="Target peer id or alias")
    alias_move.add_argument("--source", default="manual")
    alias_move.add_argument("--confidence", type=float, default=1.0)
    alias_move.add_argument("--verified", action="store_true")
    alias_move.add_argument("--json", action="store_true")

    fact = sub.add_parser("fact", help="Mutate durable facts explicitly")
    fact_sub = fact.add_subparsers(dest="fact_command", required=True)
    fact_add = fact_sub.add_parser("add", help="Add a durable fact")
    fact_add.add_argument("content")
    fact_add.add_argument("--peer", required=True, help="Subject peer id or alias")
    fact_add.add_argument("--observer", required=True, help="Observer peer id or alias")
    fact_add.add_argument("--kind", default="note")
    fact_add.add_argument("--source", default="manual")
    fact_add.add_argument("--json", action="store_true")
    fact_retract = fact_sub.add_parser("retract", help="Mark a fact as retracted")
    fact_retract.add_argument("fact_id")
    fact_retract.add_argument("--json", action="store_true")

    card = sub.add_parser("card", help="Mutate peer cards explicitly")
    card_sub = card.add_subparsers(dest="card_command", required=True)
    card_replace = card_sub.add_parser("replace", help="Replace a full card from a JSON list file")
    card_replace.add_argument("--peer", required=True, help="Subject peer id or alias")
    card_replace.add_argument("--observer", required=True, help="Observer peer id or alias")
    card_replace.add_argument("--from-file", required=True, help="Path to JSON list of strings")
    card_replace.add_argument("--json", action="store_true")

    import_cmd = sub.add_parser("import", help="Plan or apply imports from other memory systems")
    import_sub = import_cmd.add_subparsers(dest="import_command", required=True)
    honcho_api = import_sub.add_parser(
        "honcho-api",
        help="Plan a safe Honcho import through the public HTTP API",
    )
    honcho_api.add_argument("--base-url", required=True, help="Honcho API base URL")
    honcho_api.add_argument("--workspace", default="hermes", help="Workspace name, default: hermes")
    honcho_api.add_argument("--api-key", help="Honcho API key/token")
    honcho_api.add_argument("--page-size", type=int, default=100, help="API page size")
    honcho_api.add_argument("--identity-map", help="Optional JSON peer identity map")
    mode = honcho_api.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan only; do not write anything")
    mode.add_argument("--apply", action="store_true", help="Apply the import plan to the local DB")
    honcho_api.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not back up an existing target DB before --apply",
    )
    honcho_api.add_argument("--json", action="store_true", help="Print JSON")

    honcho = import_sub.add_parser(
        "honcho",
        help="Plan a safe Honcho import from a SQLite DB fixture/export",
    )
    honcho.add_argument(
        "--source-db",
        required=True,
        help="SQLite export or fixture with Honcho tables",
    )
    honcho.add_argument(
        "--workspace",
        default="hermes",
        help="Honcho workspace name, default: hermes",
    )
    honcho.add_argument(
        "--dry-run",
        action="store_true",
        help="Required for now; do not write anything",
    )
    honcho.add_argument("--json", action="store_true", help="Print JSON")
    return parser


def _add_readonly_table_command(
    sub: argparse._SubParsersAction,
    name: str,
    help_text: str,
) -> argparse.ArgumentParser:
    command = sub.add_parser(name, help=help_text)
    command.add_argument("--json", action="store_true", help="Print JSON")
    return command


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "install-shim":
        plugin_dir = Path(args.hermes_home).expanduser() / "plugins" / "local_memory"
        shim = write_plugin_shim(plugin_dir, package_root=args.package_root)
        print(shim)
        return 0

    if args.command == "import" and args.import_command == "honcho-api":
        if args.dry_run == args.apply:
            raise ValueError("Specify exactly one of --dry-run or --apply")
        client = HonchoApiClient(args.base_url, api_key=args.api_key)
        export = export_honcho_api(client, workspace=args.workspace, page_size=args.page_size)
        identity_map = load_identity_map(args.identity_map)
        plan = plan_honcho_export_import(
            export,
            target_db=Path(args.db).expanduser(),
            identity_map=identity_map,
        )
        result = apply_honcho_import_plan(plan, backup=not args.no_backup) if args.apply else plan
        _print_plan(result, as_json=args.json)
        return 0

    if args.command == "import" and args.import_command == "honcho":
        if not args.dry_run:
            raise ValueError("Honcho SQLite import currently supports --dry-run only")
        plan = plan_honcho_import(
            Path(args.source_db).expanduser(),
            target_db=Path(args.db).expanduser(),
            workspace=args.workspace,
        )
        _print_plan(plan, as_json=args.json)
        return 0

    store = LocalMemoryStore(Path(args.db).expanduser())
    if args.command == "peers":
        _print_rows(store.list_peers(), as_json=args.json)
        return 0
    if args.command == "aliases":
        _print_rows(store.list_aliases(), as_json=args.json)
        return 0
    if args.command == "sessions":
        _print_rows(store.list_sessions(), as_json=args.json)
        return 0
    if args.command == "cards":
        peer_id = _resolve_optional_peer_id(store, args.peer)
        observer_id = _resolve_optional_peer_id(store, args.observer)
        _print_rows(
            store.list_cards(
                subject_peer_id=peer_id,
                observer_peer_id=observer_id,
                limit=args.limit,
            ),
            as_json=args.json,
        )
        return 0
    if args.command == "messages":
        peer_id = _resolve_optional_peer_id(store, args.peer)
        _print_rows(
            store.list_messages(session_id=args.session, peer_id=peer_id, limit=args.limit),
            as_json=args.json,
        )
        return 0
    if args.command == "facts":
        peer_id = _resolve_optional_peer_id(store, args.peer)
        observer_id = _resolve_optional_peer_id(store, args.observer)
        _print_rows(
            store.list_facts(
                peer_id=peer_id,
                observer_peer_id=observer_id,
                status=args.status or None,
                limit=args.limit,
            ),
            as_json=args.json,
        )
        return 0
    if args.command == "search":
        peer_id = _resolve_optional_peer_id(store, args.peer)
        _print_rows(store.search(args.query, peer_id=peer_id, limit=args.limit), as_json=args.json)
        return 0
    if args.command == "context":
        peer_id = _resolve_required_peer_id(store, args.peer)
        observer_id = _resolve_required_peer_id(store, args.observer)
        print(
            store.build_context(
                subject_peer_id=peer_id,
                observer_peer_id=observer_id,
                session_id=args.session,
                query=args.query,
            )
        )
        return 0
    if args.command == "consolidate":
        if args.dry_run == args.apply:
            raise ValueError("Specify exactly one of --dry-run or --apply")
        peer_id = _resolve_required_peer_id(store, args.peer)
        observer_id = _resolve_required_peer_id(store, args.observer)
        plan = build_consolidation_plan(
            store,
            subject_peer_id=peer_id,
            observer_peer_id=observer_id,
            promote_candidates=args.promote_candidates,
            apply=args.apply,
            limit=args.limit,
        )
        _print_plan(plan, as_json=args.json)
        return 0
    if args.command == "consolidation-packet":
        peer_id = _resolve_required_peer_id(store, args.peer)
        observer_id = _resolve_required_peer_id(store, args.observer)
        packet = build_consolidation_packet(
            store,
            subject_peer_id=peer_id,
            observer_peer_id=observer_id,
            max_candidates=args.max_candidates,
            max_active=args.max_active,
        )
        _print_one(packet, as_json=args.json)
        return 0
    if args.command == "apply-patch":
        if args.dry_run == args.apply:
            raise ValueError("Specify exactly one of --dry-run or --apply")
        patch = json.loads(Path(args.patch_file).expanduser().read_text(encoding="utf-8"))
        result = apply_consolidation_patch(store, patch, apply=args.apply)
        _print_one(result, as_json=args.json)
        return 0
    if args.command == "candidate-review-packet":
        peer_id = _resolve_required_peer_id(store, args.peer)
        observer_id = _resolve_required_peer_id(store, args.observer)
        packet = build_candidate_review_packet(
            store,
            subject_peer_id=peer_id,
            observer_peer_id=observer_id,
            source=args.source,
            limit=args.limit,
        )
        _print_one(packet, as_json=args.json)
        return 0
    if args.command == "apply-candidate-review-patch":
        if args.dry_run == args.apply:
            raise ValueError("Specify exactly one of --dry-run or --apply")
        patch = json.loads(Path(args.patch_file).expanduser().read_text(encoding="utf-8"))
        packet = build_candidate_review_packet(
            store,
            subject_peer_id=patch["subject_peer_id"],
            observer_peer_id=patch["observer_peer_id"],
            limit=10000,
        )
        result = apply_candidate_review_patch(store, packet, patch, apply=args.apply)
        _print_one(result, as_json=args.json)
        return 0
    if args.command == "card-review-packet":
        peer_id = _resolve_required_peer_id(store, args.peer)
        observer_id = _resolve_required_peer_id(store, args.observer)
        packet = build_card_review_packet(
            store,
            subject_peer_id=peer_id,
            observer_peer_id=observer_id,
            max_active=args.max_active,
            max_candidates=args.max_candidates,
        )
        _print_one(packet, as_json=args.json)
        return 0
    if args.command == "apply-card-review-patch":
        if args.dry_run == args.apply:
            raise ValueError("Specify exactly one of --dry-run or --apply")
        patch = json.loads(Path(args.patch_file).expanduser().read_text(encoding="utf-8"))
        packet = build_card_review_packet(
            store,
            subject_peer_id=patch["subject_peer_id"],
            observer_peer_id=patch["observer_peer_id"],
            max_active=10000,
            max_candidates=10000,
        )
        result = apply_card_review_patch(store, packet, patch, apply=args.apply)
        _print_one(result, as_json=args.json)
        return 0
    if args.command == "maintenance":
        if args.dry_run == args.apply:
            raise ValueError("Specify exactly one of --dry-run or --apply")
        result = build_maintenance_plan(
            store,
            promote_candidates=args.promote_candidates,
            apply=args.apply,
            limit=args.limit,
        )
        _print_plan(result, as_json=args.json)
        return 0
    if args.command == "reflection-packet":
        observer_id = _resolve_required_peer_id(store, args.observer)
        packet = build_reflection_packet(
            store,
            session_id=args.session,
            observer_peer_id=observer_id,
            since_message_id=args.since_message_id,
            max_messages=args.max_messages,
        )
        _print_one(packet, as_json=args.json)
        return 0
    if args.command == "apply-reflection-patch":
        if args.dry_run == args.apply:
            raise ValueError("Specify exactly one of --dry-run or --apply")
        patch_text = Path(args.patch_file).expanduser().read_text(encoding="utf-8")
        reflection_patch = json.loads(patch_text)
        observer_id = _resolve_required_peer_id(store, reflection_patch["observer_peer_id"])
        packet = build_reflection_packet(
            store,
            session_id=reflection_patch["session_id"],
            observer_peer_id=observer_id,
            since_message_id=0,
            max_messages=10000,
        )
        reflection_patch["observer_peer_id"] = observer_id
        result = apply_reflection_patch(store, packet, reflection_patch, apply=args.apply)
        _print_one(result, as_json=args.json)
        return 0
    if args.command == "reflection-maintenance":
        observer_id = _resolve_required_peer_id(store, args.observer)
        result = build_reflection_maintenance_plan(
            store,
            observer_peer_id=observer_id,
            min_messages=args.min_messages,
            max_messages=args.max_messages,
        )
        _print_one(result, as_json=args.json)
        return 0
    if args.command == "alias":
        peer_id = _resolve_required_peer_id(store, args.peer)
        row = store.set_alias(
            args.alias,
            peer_id=peer_id,
            source=args.source,
            confidence=args.confidence,
            verified=args.verified,
        )
        _print_one(row, as_json=args.json)
        return 0
    if args.command == "fact":
        if args.fact_command == "add":
            peer_id = _resolve_required_peer_id(store, args.peer)
            observer_id = _resolve_required_peer_id(store, args.observer)
            row = store.add_fact(
                subject_peer_id=peer_id,
                observer_peer_id=observer_id,
                content=args.content,
                kind=args.kind,
                source=args.source,
            )
        else:
            row = store.update_fact_status(args.fact_id, "retracted")
        _print_one(row, as_json=args.json)
        return 0
    if args.command == "card":
        peer_id = _resolve_required_peer_id(store, args.peer)
        observer_id = _resolve_required_peer_id(store, args.observer)
        items = _read_card_items(Path(args.from_file))
        row = store.set_card(subject_peer_id=peer_id, observer_peer_id=observer_id, items=items)
        _print_one(row, as_json=args.json)
        return 0
    return 1


def _resolve_optional_peer_id(store: LocalMemoryStore, value: str | None) -> str | None:
    if value is None:
        return None
    return _resolve_required_peer_id(store, value)


def _resolve_required_peer_id(store: LocalMemoryStore, value: str) -> str:
    resolved = store.resolve_peer(value)
    return resolved["id"] if resolved is not None else value


def _read_card_items(path: Path) -> list[str]:
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("card file must contain a JSON list of strings")
    return data


def _print_plan(plan: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    print(
        f"mode={plan['mode']} | "
        f"source={plan['source']['db_path']} | "
        f"target={plan['target']['db_path']}"
    )
    print("counts:")
    for key, value in plan["counts"].items():
        print(f"  {key}: {value}")
    if plan["warnings"]:
        print("warnings:")
        for warning in plan["warnings"]:
            print(f"  - {warning}")


def _print_one(row: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    else:
        print(_format_row(row))


def _print_rows(rows: list[dict[str, Any]], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("(no rows)")
        return
    for row in rows:
        print(_format_row(row))


def _format_row(row: dict[str, Any]) -> str:
    preferred = [
        "id",
        "alias",
        "peer_id",
        "subject_peer_id",
        "observer_peer_id",
        "session_id",
        "role",
        "display_name",
        "kind",
        "content",
        "items",
        "title",
        "source",
    ]
    parts = []
    for key in preferred:
        if key in row and row[key] is not None:
            parts.append(f"{key}={row[key]}")
    if not parts:
        parts = [f"{key}={value}" for key, value in row.items() if value is not None]
    return " | ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
