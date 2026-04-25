from __future__ import annotations

from pathlib import Path

import tomllib

import hermes_local_memory


def test_project_version_matches_package_version() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == hermes_local_memory.__version__


def test_console_script_points_to_cli_main() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["hermes-local-memory"] == "hermes_local_memory.cli:main"
