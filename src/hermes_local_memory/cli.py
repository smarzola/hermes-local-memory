from __future__ import annotations

import argparse
from pathlib import Path

from hermes_local_memory.hermes_plugin import write_plugin_shim


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-local-memory")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "install-shim":
        plugin_dir = Path(args.hermes_home).expanduser() / "plugins" / "local_memory"
        shim = write_plugin_shim(plugin_dir, package_root=args.package_root)
        print(shim)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
