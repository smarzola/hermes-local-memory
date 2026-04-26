from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory.cli import main


def run_cli(args: list[str], capsys) -> str:  # noqa: ANN001
    assert main(args) == 0
    return capsys.readouterr().out


def test_sync_skills_installs_packaged_maintenance_skill(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    hermes_home = tmp_path / "hermes"

    output = run_cli(["sync-skills", "--hermes-home", str(hermes_home), "--json"], capsys)
    result = json.loads(output)

    skill_path = hermes_home / "skills" / "local-memory-maintenance" / "SKILL.md"
    assert result["changed"] is True
    assert result["skill"] == "local-memory-maintenance"
    assert Path(result["target"]) == skill_path
    content = skill_path.read_text(encoding="utf-8")
    assert "name: local-memory-maintenance" in content
    assert "peer_merges" in content
    assert "keep_source_alias" in content

    provenance_path = skill_path.with_name(".hermes-local-memory-source.json")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["package"] == "hermes-local-memory"
    assert provenance["skill"] == "local-memory-maintenance"


def test_sync_skills_updates_stale_copy_without_skill_backup(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    hermes_home = tmp_path / "hermes"
    skills_root = hermes_home / "skills"
    skill_dir = skills_root / "local-memory-maintenance"
    skill_dir.mkdir(parents=True)
    stale = skill_dir / "SKILL.md"
    stale.write_text("---\nname: local-memory-maintenance\n---\nstale\n", encoding="utf-8")

    output = run_cli(["sync-skills", "--hermes-home", str(hermes_home), "--json"], capsys)
    result = json.loads(output)

    assert result["changed"] is True
    assert result["removed_existing"] is True
    assert "backup" not in result
    assert "peer_merges" in stale.read_text(encoding="utf-8")
    assert not list(skills_root.glob("local-memory-maintenance.backup-*"))
    assert [path.name for path in skills_root.iterdir()] == ["local-memory-maintenance"]


def test_install_shim_syncs_packaged_skill_by_default(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    hermes_home = tmp_path / "hermes"

    output = run_cli(["install-shim", "--hermes-home", str(hermes_home), "--json"], capsys)
    result = json.loads(output)

    assert Path(result["shim"]) == hermes_home / "plugins" / "local_memory" / "__init__.py"
    assert result["skill_sync"]["changed"] is True
    assert (hermes_home / "skills" / "local-memory-maintenance" / "SKILL.md").is_file()
