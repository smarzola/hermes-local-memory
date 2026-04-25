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
    return 1


def _resolve_optional_peer_id(store: LocalMemoryStore, value: str | None) -> str | None:
    if value is None:
        return None
    return _resolve_required_peer_id(store, value)


def _resolve_required_peer_id(store: LocalMemoryStore, value: str) -> str:
    resolved = store.resolve_peer(value)
    return resolved["id"] if resolved is not None else value


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
