from __future__ import annotations

import importlib.util
from pathlib import Path

from hermes_local_memory.hermes_plugin import write_plugin_shim


class Collector:
    def __init__(self) -> None:
        self.provider = None
        self.skills = {}

    def register_memory_provider(self, provider) -> None:  # noqa: ANN001
        self.provider = provider

    def register_skill(self, name: str, path) -> None:  # noqa: ANN001
        self.skills[name] = Path(path)


def import_plugin(path: Path):  # noqa: ANN201
    spec = importlib.util.spec_from_file_location("local_memory_test_plugin", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_plugin_shim_creates_hermes_discoverable_register_function(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "local_memory"

    shim_path = write_plugin_shim(plugin_dir, package_root=Path.cwd() / "src")

    assert shim_path == plugin_dir / "__init__.py"
    assert shim_path.exists()
    module = import_plugin(shim_path)
    collector = Collector()

    module.register(collector)

    assert collector.provider is not None
    assert collector.provider.name == "local"
    assert collector.skills["maintenance"].name == "SKILL.md"
    assert collector.skills["maintenance"].is_file()
    assert "name: local-memory-maintenance" in collector.skills["maintenance"].read_text(
        encoding="utf-8"
    )
    assert {schema["name"] for schema in collector.provider.get_tool_schemas()} == {
        "memory_get_card",
        "memory_set_card",
        "memory_search",
        "memory_context",
        "memory_conclude",
        "memory_consolidate",
        "memory_maintenance",
        "memory_build_peer_review_packet",
        "memory_apply_peer_review_patch",
        "memory_build_reflection_packets",
        "memory_apply_reflection_patch",
        "memory_build_candidate_review_packet",
        "memory_apply_candidate_review_patch",
        "memory_build_card_review_packet",
        "memory_apply_card_review_patch",
        "memory_build_honcho_migration_review_packet",
        "memory_apply_honcho_migration_review_patch",
    }


def test_plugin_shim_contains_absolute_package_path_for_external_hermes_loading(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "checkout" / "src"
    plugin_dir = tmp_path / "hermes-home" / "plugins" / "local_memory"

    shim_path = write_plugin_shim(plugin_dir, package_root=package_root)

    content = shim_path.read_text(encoding="utf-8")
    assert str(package_root) in content
    assert "register_memory_provider(LocalMemoryProvider())" in content
    assert "register_skill" in content
    assert "local-memory-maintenance" in content
