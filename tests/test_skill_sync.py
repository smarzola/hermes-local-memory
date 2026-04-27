from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory.cli import main


def run_cli(args: list[str], capsys) -> str:  # noqa: ANN001
    assert main(args) == 0
    return capsys.readouterr().out


def write_managed_provenance(skill_dir: Path) -> None:
    (skill_dir / ".hermes-local-memory-source.json").write_text(
        json.dumps(
            {
                "package": "hermes-local-memory",
                "skill": "local-memory-maintenance",
                "version": "0.0.0",
            }
        )
        + "\n",
        encoding="utf-8",
    )


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
    assert "daily autonomous care" in content
    assert "local_memory:maintenance" in content
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
    assert "daily autonomous care" in stale.read_text(encoding="utf-8")
    assert not list(skills_root.glob("local-memory-maintenance.backup-*"))
    assert [path.name for path in skills_root.iterdir()] == ["local-memory-maintenance"]


def test_install_shim_registers_packaged_plugin_skill_without_copying_skill(
    tmp_path: Path,
    capsys,  # noqa: ANN001
) -> None:
    hermes_home = tmp_path / "hermes"

    output = run_cli(["install-shim", "--hermes-home", str(hermes_home), "--json"], capsys)
    result = json.loads(output)

    assert Path(result["shim"]) == hermes_home / "plugins" / "local_memory" / "__init__.py"
    assert result["plugin_skill"]["name"] == "local_memory:maintenance"
    assert Path(result["plugin_skill"]["source"]).name == "SKILL.md"
    assert result["copied_skill_cleanup"] == {
        "skill": "local-memory-maintenance",
        "target": str(hermes_home / "skills" / "local-memory-maintenance" / "SKILL.md"),
        "exists": False,
        "removed": False,
        "managed": False,
        "reason": "not_present",
    }
    assert not (hermes_home / "skills" / "local-memory-maintenance" / "SKILL.md").exists()


def test_install_shim_removes_managed_legacy_copied_skill(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    hermes_home = tmp_path / "hermes"
    skill_dir = hermes_home / "skills" / "local-memory-maintenance"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("managed stale copy\n", encoding="utf-8")
    write_managed_provenance(skill_dir)

    output = run_cli(["install-shim", "--hermes-home", str(hermes_home), "--json"], capsys)
    result = json.loads(output)

    cleanup = result["copied_skill_cleanup"]
    assert cleanup["exists"] is True
    assert cleanup["managed"] is True
    assert cleanup["removed"] is True
    assert cleanup["reason"] == "managed_copy_superseded_by_plugin_skill"
    assert not skill_dir.exists()


def test_install_shim_preserves_unmanaged_copied_skill_without_force(
    tmp_path: Path,
    capsys,  # noqa: ANN001
) -> None:
    hermes_home = tmp_path / "hermes"
    skill_dir = hermes_home / "skills" / "local-memory-maintenance"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("user edited copy\n", encoding="utf-8")

    output = run_cli(["install-shim", "--hermes-home", str(hermes_home), "--json"], capsys)
    result = json.loads(output)

    cleanup = result["copied_skill_cleanup"]
    assert cleanup["exists"] is True
    assert cleanup["managed"] is False
    assert cleanup["removed"] is False
    assert cleanup["reason"] == "unmanaged_copy_preserved"
    assert "--force-remove-copied-skill" in cleanup["action"]
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == "user edited copy\n"


def test_install_shim_can_force_remove_unmanaged_copied_skill(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    hermes_home = tmp_path / "hermes"
    skill_dir = hermes_home / "skills" / "local-memory-maintenance"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("user edited copy\n", encoding="utf-8")

    output = run_cli(
        [
            "install-shim",
            "--hermes-home",
            str(hermes_home),
            "--force-remove-copied-skill",
            "--json",
        ],
        capsys,
    )
    result = json.loads(output)

    cleanup = result["copied_skill_cleanup"]
    assert cleanup["removed"] is True
    assert cleanup["reason"] == "forced"
    assert not skill_dir.exists()
