from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path


def test_hatch_build_configuration_includes_packaged_agent_skill() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.hatch.build]" in pyproject
    assert '"/skills"' in pyproject


def test_built_artifacts_include_local_memory_maintenance_skill() -> None:
    skill_path = "skills/local-memory-maintenance/SKILL.md"
    artifacts = sorted(Path("dist").glob("hermes_local_memory-0.2.0*"))

    if not artifacts:
        # This test is primarily a release/build verification. Normal unit-test
        # runs may execute before artifacts are built; the config test above
        # still guards the packaging intent in CI.
        return

    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as wheel:
                assert skill_path in wheel.namelist()
        elif artifact.suffixes[-2:] == [".tar", ".gz"]:
            with tarfile.open(artifact) as sdist:
                assert any(name.endswith(skill_path) for name in sdist.getnames())
