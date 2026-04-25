from __future__ import annotations

import tomllib
from pathlib import Path

import hermes_local_memory


def test_project_version_matches_package_version() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == hermes_local_memory.__version__


def test_console_script_points_to_cli_main() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["hermes-local-memory"] == "hermes_local_memory.cli:main"


def test_project_requires_python_311_or_newer() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.11"
    assert "Programming Language :: Python :: 3.10" not in pyproject["project"]["classifiers"]
    assert "Programming Language :: Python :: 3.11" in pyproject["project"]["classifiers"]
    assert "Programming Language :: Python :: 3.12" in pyproject["project"]["classifiers"]
    assert "Programming Language :: Python :: 3.13" in pyproject["project"]["classifiers"]
    assert "Programming Language :: Python :: 3.14" in pyproject["project"]["classifiers"]


def test_dev_dependencies_do_not_include_python_310_tomli_fallback() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]
    assert all(not dependency.startswith("tomli") for dependency in dev_dependencies)
