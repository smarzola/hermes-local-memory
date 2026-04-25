from __future__ import annotations

import json
from pathlib import Path

from hermes_local_memory.cli import main
from hermes_local_memory.store import LocalMemoryStore


def _seed_honcho_review_store(db_path: Path) -> LocalMemoryStore:
    store = LocalMemoryStore(db_path)
    store.initialize()
    store.upsert_peer("alice", display_name="Alice", kind="human")
    store.upsert_peer("bob", display_name="Bob", kind="ai")
    store.set_card(
        subject_peer_id="alice",
        observer_peer_id="bob",
        items=["Name: Alice", "Old short imported card"],
    )
    store.add_fact(
        fact_id="honcho_high_signal",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice prefers local-first, auditable memory systems.",
        kind="preference",
        source="honcho-api-conclusion",
        status="candidate",
        confidence=0.95,
    )
    store.add_fact(
        fact_id="honcho_noisy",
        subject_peer_id="alice",
        observer_peer_id="bob",
        content="Alice was working on a transient debugging task last Tuesday.",
        kind="note",
        source="honcho-api-conclusion",
        status="candidate",
        confidence=0.5,
    )
    return store


def _run_cli(args: list[str], capsys) -> str:  # noqa: ANN001
    assert main(args) == 0
    return capsys.readouterr().out


def test_honcho_candidate_adoption_flow_promotes_selected_facts_and_rebuilds_card(
    tmp_path: Path,
    capsys,  # noqa: ANN001
) -> None:
    db_path = tmp_path / "memory.sqlite"
    store = _seed_honcho_review_store(db_path)

    packet_output = _run_cli(
        [
            "--db",
            str(db_path),
            "honcho-migration-review-packet",
            "--peer",
            "alice",
            "--observer",
            "bob",
            "--json",
        ],
        capsys,
    )
    packet = json.loads(packet_output)

    assert packet["schema"] == "hermes-local-memory.honcho-migration-review-packet.v1"
    assert packet["source_filter"] == "honcho-api-conclusion"
    assert packet["candidate_review_packet"]["rules"]["review_high_signal_imports"] is True
    assert (
        packet["card_review_packet"]["rules"]["use_honcho_candidates_for_first_migration"]
        is True
    )
    assert {fact["id"] for fact in packet["candidate_review_packet"]["candidate_facts"]} == {
        "honcho_high_signal",
        "honcho_noisy",
    }

    patch_path = tmp_path / "honcho-review-patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "schema": "hermes-local-memory.honcho-migration-review-patch.v1",
                "subject_peer_id": "alice",
                "observer_peer_id": "bob",
                "candidate_patch": {
                    "schema": "hermes-local-memory.candidate-review-patch.v1",
                    "subject_peer_id": "alice",
                    "observer_peer_id": "bob",
                    "promote_fact_ids": ["honcho_high_signal"],
                    "retract_fact_ids": ["honcho_noisy"],
                },
                "card_patch": {
                    "schema": "hermes-local-memory.card-review-patch.v1",
                    "subject_peer_id": "alice",
                    "observer_peer_id": "bob",
                    "card_replace": [
                        "Name: Alice",
                        "Prefers local-first, auditable memory systems",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    dry_run = json.loads(
        _run_cli(
            [
                "--db",
                str(db_path),
                "apply-honcho-migration-review-patch",
                str(patch_path),
                "--dry-run",
                "--json",
            ],
            capsys,
        )
    )
    assert dry_run["validation"]["valid"] is True
    assert store.get_fact("honcho_high_signal")["status"] == "candidate"

    applied = json.loads(
        _run_cli(
            [
                "--db",
                str(db_path),
                "apply-honcho-migration-review-patch",
                str(patch_path),
                "--apply",
                "--json",
            ],
            capsys,
        )
    )

    assert applied["writes"] == {
        "facts_promoted": 1,
        "facts_superseded": 0,
        "facts_retracted": 1,
        "card_replaced": True,
    }
    assert store.get_fact("honcho_high_signal")["status"] == "active"
    assert store.get_fact("honcho_noisy")["status"] == "retracted"
    assert store.get_card(subject_peer_id="alice", observer_peer_id="bob") == [
        "Name: Alice",
        "Prefers local-first, auditable memory systems",
    ]
