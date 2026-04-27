from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path("skills/local-memory-maintenance/SKILL.md")


def test_local_memory_maintenance_skill_is_packaged_for_agents() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert "name: local-memory-maintenance" in content
    assert "Policy-driven Hermes Local Memory maintenance runbook" in content
    assert "local_memory:maintenance" in content
    assert "Recipe: quiet-deterministic" in content
    assert "Apply policy: safe-deterministic" in content
    assert "Reporting: on-error" in content
    assert "memory_build_peer_review_packet" in content
    assert "memory_build_reflection_packets" in content
    assert "memory_maintenance" in content
    assert "memory_build_candidate_review_packet" in content
    assert "memory_build_card_review_packet" in content
    assert "memory_build_honcho_migration_review_packet" in content
    assert "memory_apply_honcho_migration_review_patch" in content
    assert "one-time Honcho migration review" in content
    assert "migration material" in content
    assert "peer_merges" in content
    assert "keep_source_alias" in content
    assert "memory_get_card" in content
    assert "memory_set_card" in content
    assert "Preserve raw messages" in content
    assert "Do not force the default full-audit recipe" in content
    assert "silent" in content


def test_local_memory_maintenance_skill_uses_canonical_names_not_legacy_names() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert "memory_reflection_maintenance" not in content
    assert "memory_peer_review" not in content
    assert "memory_candidate_review" not in content
    assert "memory_card_review" not in content
    assert "memory_profile" not in content
