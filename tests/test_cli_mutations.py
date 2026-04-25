from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory.cli import main
from hermes_local_memory.store import LocalMemoryStore


def seed_store(db_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(db_path)
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("eve", display_name="Eve", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_alias("telegram:1001", peer_id="alice", source="telegram", verified=True)
    store.upsert_session("dm", platform="telegram")
    msg = store.add_message(
        session_id="dm",
        peer_id="alice",
        role="user",
        content="I want memory repair commands to be explicit.",
    )
    store.add_fact(
        fact_id="fact_existing",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice wants explicit memory repair commands.",
        kind="preference",
        evidence_message_ids=[msg["id"]],
    )
    return store


def run_cli(args: list[str], capsys) -> str:  # noqa: ANN001
    assert main(args) == 0
    return capsys.readouterr().out


def test_cli_alias_add_and_move_are_explicit_mutations(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    add_output = run_cli(
        [
            "--db",
            str(db_path),
            "alias",
            "add",
            "telegram:1002",
            "--peer",
            "eve",
            "--source",
            "telegram",
            "--verified",
            "--json",
        ],
        capsys,
    )
    added = json.loads(add_output)
    assert added["alias"] == "telegram:1002"
    assert added["peer_id"] == "eve"
    assert added["verified"] == 1

    move_output = run_cli(
        [
            "--db",
            str(db_path),
            "alias",
            "move",
            "telegram:1002",
            "--peer",
            "alice",
            "--json",
        ],
        capsys,
    )
    moved = json.loads(move_output)
    assert moved["alias"] == "telegram:1002"
    assert moved["peer_id"] == "alice"


def test_cli_fact_add_and_retract(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    add_output = run_cli(
        [
            "--db",
            str(db_path),
            "fact",
            "add",
            "Alice prefers local-first tools.",
            "--peer",
            "telegram:1001",
            "--observer",
            "bob",
            "--kind",
            "preference",
            "--json",
        ],
        capsys,
    )
    added = json.loads(add_output)
    assert added["subject_peer_id"] == "alice"
    assert added["content"] == "Alice prefers local-first tools."
    assert added["kind"] == "preference"
    assert added["status"] == "active"

    retract_output = run_cli(
        ["--db", str(db_path), "fact", "retract", "fact_existing", "--json"],
        capsys,
    )
    retracted = json.loads(retract_output)
    assert retracted["id"] == "fact_existing"
    assert retracted["status"] == "retracted"


def test_cli_card_replace_from_file(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    card_path = tmp_path / "card.json"
    seed_store(db_path)
    card_path.write_text(
        json.dumps(["Name: Alice", "Preference: explicit repair commands"]),
        encoding="utf-8",
    )

    output = run_cli(
        [
            "--db",
            str(db_path),
            "card",
            "replace",
            "--peer",
            "alice",
            "--observer",
            "bob",
            "--from-file",
            str(card_path),
            "--json",
        ],
        capsys,
    )
    card = json.loads(output)
    assert card["subject_peer_id"] == "alice"
    assert card["observer_peer_id"] == "bob"
    assert card["items"] == ["Name: Alice", "Preference: explicit repair commands"]


def test_cli_consolidate_dry_run_and_apply(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    store = seed_store(db_path)
    store.add_fact(
        fact_id="fact_candidate",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers inspectable consolidation.",
        kind="preference",
        status="candidate",
    )

    dry_run_output = run_cli(
        [
            "--db",
            str(db_path),
            "consolidate",
            "--peer",
            "telegram:1001",
            "--observer",
            "bob",
            "--promote-candidates",
            "--dry-run",
            "--json",
        ],
        capsys,
    )
    dry_run = json.loads(dry_run_output)
    assert dry_run["mode"] == "dry-run"
    assert dry_run["counts"]["candidate_promotions"] == 1
    assert store.get_fact("fact_candidate")["status"] == "candidate"

    apply_output = run_cli(
        [
            "--db",
            str(db_path),
            "consolidate",
            "--peer",
            "alice",
            "--observer",
            "bob",
            "--promote-candidates",
            "--apply",
            "--json",
        ],
        capsys,
    )
    applied = json.loads(apply_output)
    assert applied["mode"] == "apply"
    assert applied["writes"]["candidate_promotions"] == 1
    assert store.get_fact("fact_candidate")["status"] == "active"
    assert "Alice prefers inspectable consolidation." in store.get_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
    )


def test_cli_consolidation_packet_and_apply_patch(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    store = seed_store(db_path)
    store.add_fact(
        fact_id="fact_candidate_patch",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers patch-based consolidation.",
        kind="preference",
        status="candidate",
    )

    packet_output = run_cli(
        [
            "--db",
            str(db_path),
            "consolidation-packet",
            "--peer",
            "alice",
            "--observer",
            "bob",
            "--json",
        ],
        capsys,
    )
    packet = json.loads(packet_output)
    assert packet["subject_peer_id"] == "alice"
    assert any(fact["id"] == "fact_candidate_patch" for fact in packet["candidate_facts"])

    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "subject_peer_id": "alice",
                "observer_peer_id": "bob",
                "promote_fact_ids": ["fact_candidate_patch"],
                "card_replace": ["Name: Alice", "Prefers patch-based consolidation"],
            }
        ),
        encoding="utf-8",
    )

    dry_run_output = run_cli(
        ["--db", str(db_path), "apply-patch", str(patch_path), "--dry-run", "--json"],
        capsys,
    )
    dry_run = json.loads(dry_run_output)
    assert dry_run["mode"] == "dry-run"
    assert dry_run["validation"]["valid"] is True
    assert store.get_fact("fact_candidate_patch")["status"] == "candidate"

    apply_output = run_cli(
        ["--db", str(db_path), "apply-patch", str(patch_path), "--apply", "--json"],
        capsys,
    )
    applied = json.loads(apply_output)
    assert applied["mode"] == "apply"
    assert applied["writes"]["facts_promoted"] == 1
    assert store.get_fact("fact_candidate_patch")["status"] == "active"


def test_cli_maintenance_runs_all_pairs(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    store = seed_store(db_path)
    store.upsert_peer("carol", display_name="Carol", kind="human")
    store.add_fact(
        fact_id="fact_candidate_alice",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers all-pairs maintenance.",
        kind="preference",
        status="candidate",
    )
    store.add_fact(
        fact_id="fact_candidate_carol",
        subject_peer_id="carol",
        observer_peer_id="bob",
        content="Carol prefers all-pairs maintenance.",
        kind="preference",
        status="candidate",
    )

    output = run_cli(
        [
            "--db",
            str(db_path),
            "maintenance",
            "--promote-candidates",
            "--dry-run",
            "--json",
        ],
        capsys,
    )

    plan = json.loads(output)
    assert plan["counts"]["pairs"] == 2
    assert plan["counts"]["candidate_promotions"] == 2
    assert store.get_fact("fact_candidate_alice")["status"] == "candidate"


def test_cli_candidate_review_packet_and_apply_candidate_patch(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    store = seed_store(db_path)
    store.add_fact(
        fact_id="fact_candidate_review",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers safe candidate review.",
        kind="preference",
        source="honcho-import",
        status="candidate",
    )

    packet_output = run_cli(
        [
            "--db",
            str(db_path),
            "candidate-review-packet",
            "--peer",
            "alice",
            "--observer",
            "bob",
            "--source",
            "honcho-import",
            "--json",
        ],
        capsys,
    )
    packet = json.loads(packet_output)
    assert packet["schema"] == "hermes-local-memory.candidate-review-packet.v1"
    assert [fact["id"] for fact in packet["candidate_facts"]] == ["fact_candidate_review"]

    patch_path = tmp_path / "candidate-patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "schema": "hermes-local-memory.candidate-review-patch.v1",
                "subject_peer_id": "alice",
                "observer_peer_id": "bob",
                "promote_fact_ids": ["fact_candidate_review"],
                "card_additions": ["PREFERENCE: Prefers safe candidate review"],
            }
        ),
        encoding="utf-8",
    )

    dry_run_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-candidate-review-patch",
            str(patch_path),
            "--dry-run",
            "--json",
        ],
        capsys,
    )
    dry_run = json.loads(dry_run_output)
    assert dry_run["validation"]["valid"] is True
    assert store.get_fact("fact_candidate_review")["status"] == "candidate"

    apply_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-candidate-review-patch",
            str(patch_path),
            "--apply",
            "--json",
        ],
        capsys,
    )
    applied = json.loads(apply_output)
    assert applied["writes"]["facts_promoted"] == 1
    assert store.get_fact("fact_candidate_review")["status"] == "active"


def test_cli_card_review_packet_and_apply_card_patch(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    store = seed_store(db_path)
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=[
            "Name: Alice",
            "PREFERENCE: Prefers explicit repair commands",
            "PREFERENCE: Is willing to try suggested changes",
        ],
    )

    packet_output = run_cli(
        [
            "--db",
            str(db_path),
            "card-review-packet",
            "--peer",
            "alice",
            "--observer",
            "bob",
            "--json",
        ],
        capsys,
    )
    packet = json.loads(packet_output)
    assert packet["schema"] == "hermes-local-memory.card-review-packet.v1"
    assert packet["current_card"] == [
        "Name: Alice",
        "PREFERENCE: Prefers explicit repair commands",
        "PREFERENCE: Is willing to try suggested changes",
    ]

    patch_path = tmp_path / "card-patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "schema": "hermes-local-memory.card-review-patch.v1",
                "subject_peer_id": "alice",
                "observer_peer_id": "bob",
                "card_replace": ["Name: Alice", "PREFERENCE: Prefers explicit repair commands"],
            }
        ),
        encoding="utf-8",
    )

    dry_run_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-card-review-patch",
            str(patch_path),
            "--dry-run",
            "--json",
        ],
        capsys,
    )
    dry_run = json.loads(dry_run_output)
    assert dry_run["validation"]["valid"] is True
    assert len(store.get_card(subject_peer_id="alice", observer_peer_id="bob")) == 3

    apply_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-card-review-patch",
            str(patch_path),
            "--apply",
            "--json",
        ],
        capsys,
    )
    applied = json.loads(apply_output)
    assert applied["writes"] == {"card_replaced": True, "before_count": 3, "after_count": 2}
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "PREFERENCE: Prefers explicit repair commands",
    ]


def test_cli_peer_review_packet_and_apply_peer_patch(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    store = seed_store(db_path)
    store.upsert_peer("telegram-1002", display_name="Telegram 1002", kind="human")
    store.set_alias("telegram:1002", peer_id="telegram-1002", source="telegram")

    packet_output = run_cli(
        ["--db", str(db_path), "peer-review-packet", "--json"],
        capsys,
    )
    packet = json.loads(packet_output)
    assert packet["schema"] == "hermes-local-memory.peer-review-packet.v1"
    assert any(peer["id"] == "telegram-1002" for peer in packet["unverified_peers"])

    patch_path = tmp_path / "peer-patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "schema": "hermes-local-memory.peer-review-patch.v1",
                "alias_moves": [
                    {
                        "alias": "telegram:1002",
                        "to_peer_id": "alice",
                        "source": "agent-peer-review",
                        "confidence": 0.9,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    dry_run_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-peer-review-patch",
            str(patch_path),
            "--dry-run",
            "--json",
        ],
        capsys,
    )
    dry_run = json.loads(dry_run_output)
    assert dry_run["validation"]["valid"] is True
    assert store.resolve_peer("telegram:1002")["id"] == "telegram-1002"

    apply_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-peer-review-patch",
            str(patch_path),
            "--apply",
            "--json",
        ],
        capsys,
    )
    applied = json.loads(apply_output)
    assert applied["writes"] == {"aliases_moved": 1, "human_prompts_recorded": 0}
    assert store.resolve_peer("telegram:1002")["id"] == "alice"


def test_cli_reflection_maintenance_and_apply_reflection_patch(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    db_path = tmp_path / "memory.sqlite"
    seed_store(db_path)

    plan_output = run_cli(
        [
            "--db",
            str(db_path),
            "reflection-maintenance",
            "--observer",
            "bob",
            "--min-messages",
            "1",
            "--json",
        ],
        capsys,
    )
    plan = json.loads(plan_output)
    assert plan["schema"] == "hermes-local-memory.reflection-maintenance-plan.v1"
    assert plan["counts"]["packets"] == 1
    message_id = plan["packets"][0]["message_window"][0]["id"]

    packet_output = run_cli(
        [
            "--db",
            str(db_path),
            "reflection-packet",
            "--session",
            "dm",
            "--observer",
            "bob",
            "--since-message-id",
            "0",
            "--json",
        ],
        capsys,
    )
    packet = json.loads(packet_output)
    assert packet["schema"] == "hermes-local-memory.reflection-packet.v1"
    assert packet["message_window"][0]["id"] == message_id

    patch_path = tmp_path / "reflection-patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "schema": "hermes-local-memory.reflection-patch.v1",
                "session_id": "dm",
                "observer_peer_id": "bob",
                "new_candidate_facts": [
                    {
                        "subject_peer_id": "alice",
                        "kind": "preference",
                        "content": "Alice prefers explicit memory repair commands.",
                        "confidence": 0.9,
                        "evidence_message_ids": [message_id],
                    }
                ],
                "session_summary": {
                    "content": "Alice discussed explicit memory repair commands.",
                    "covered_from_message_id": message_id,
                    "covered_to_message_id": message_id,
                    "model": "hermes-agent",
                },
            }
        ),
        encoding="utf-8",
    )

    dry_run_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-reflection-patch",
            str(patch_path),
            "--dry-run",
            "--json",
        ],
        capsys,
    )
    dry_run = json.loads(dry_run_output)
    assert dry_run["mode"] == "dry-run"
    assert dry_run["validation"]["valid"] is True

    apply_output = run_cli(
        [
            "--db",
            str(db_path),
            "apply-reflection-patch",
            str(patch_path),
            "--apply",
            "--json",
        ],
        capsys,
    )
    applied = json.loads(apply_output)
    assert applied["writes"] == {"candidate_facts_added": 1, "summaries_added": 1}
