from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hermes_local_memory.hermes_plugin import write_plugin_shim
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
