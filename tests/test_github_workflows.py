from __future__ import annotations

from pathlib import Path


def test_ci_workflow_targets_supported_python_versions() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "'3.10'" not in workflow
    assert "'3.11'" in workflow
    assert "'3.12'" in workflow
    assert "'3.13'" in workflow
    assert "'3.14'" in workflow


def test_pypi_publish_workflow_is_tag_only_and_uses_trusted_publishing() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "tags:" in workflow
    assert "'v*'" in workflow or '"v*"' in workflow
    assert "branches:" not in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish" in workflow
    assert "ruff check ." in workflow
    assert "pytest" in workflow
    assert "password:" not in workflow


def test_publish_workflow_builds_artifacts_before_publishing() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "python -m build" in workflow
    assert "python -m twine check dist/*" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow


def test_publish_workflow_creates_github_release_from_ci() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "contents: write" in workflow
    assert "softprops/action-gh-release" in workflow
    assert "files: dist/*" in workflow


def test_publish_workflow_uses_pypi_environment_for_trusted_publishing() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "environment:" in workflow
    assert "name: pypi" in workflow
    assert "id-token: write" in workflow
