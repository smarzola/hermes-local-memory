# Changelog

## Unreleased

## v0.2.1

### Added

- Added provider peer-review `peer_merges` patches so maintenance jobs can merge runtime/ephemeral duplicate peers into canonical peers through `memory_apply_peer_review_patch`, while preserving retired peer IDs as aliases.
- Added packaged maintenance-skill guidance for `peer_merges` and `keep_source_alias=true` identity reconciliation.

### Fixed

- Fixed runtime reconciliation for sanitized peer IDs such as `telegram-default`: when `telegram:default` already resolves to a canonical peer, direct message/session references are moved to the canonical peer and the retired peer ID is retained as a verified alias.
- Fixed the release workflow so tag pushes create GitHub releases from CI-built artifacts as well as publishing those same artifacts to PyPI via Trusted Publishing.
- Made artifact packaging tests use the current project version instead of a hard-coded released version.

## v0.2.0

### Changed

- Re-released the provider-first memory maintenance workflow as the `0.2.0` feature milestone.
- Included clarified packaged-skill guidance for first Honcho migration review: inspect packet state first, promote only stable high-signal imports, and retract or leave noisy numeric-id/system/artifact candidates.

## v0.1.4

### Added

- Added provider-tool names that make packet-building explicit: `memory_build_peer_review_packet`, `memory_build_reflection_packets`, `memory_build_candidate_review_packet`, and `memory_build_card_review_packet`.
- Added explicit card tools, `memory_get_card` and `memory_set_card`, replacing the ambiguous exposed `memory_profile` getter/setter shape while retaining hidden legacy compatibility.
- Added a packaged `skills/local-memory-maintenance/SKILL.md` workflow so downstream agents can load the full maintenance cycle instead of relying on ad hoc prompts.
- Added first-migration Honcho review tools (`memory_build_honcho_migration_review_packet`, `memory_apply_honcho_migration_review_patch`, and CLI equivalents) so agents can promote selected high-signal imported memories and rebuild cards without deterministic bulk promotion.

### Fixed

- Made deterministic maintenance conservative for imported Honcho candidates: `honcho-*` / `honcho-api-*` candidate facts are no longer bulk-promoted by `--promote-candidates`.
- Stopped maintenance from appending every existing active fact into compact peer cards. Cards are compact synthesized views and should be changed through `memory_set_card`, card review, or validated `card_replace` patches.
- Made provider `memory_maintenance` return compact changed-pair summaries instead of very large full pair payloads, making scheduled jobs less prompt-heavy.
- Made compact-card writes reject accidental empty cards unless `allow_empty=true` is explicit.

### Documented

- Clarified the reflection → candidate facts/summaries → conservative maintenance → explicit card synthesis model.
- Updated setup, CLI, feature, design, and agent docs with conservative maintenance guidance.
- Documented that large candidate-promotion plans, especially from imported Honcho conclusions, should be treated as policy/tooling regressions and skipped rather than applied.

### Safety

- Raw messages remain preserved.
- Imported Honcho conclusions remain searchable/reviewable as candidate facts unless explicitly promoted by review.
- Card cleanup is full-card replacement, so changes are auditable and reversible via DB backups.

## v0.1.3

- Anonymized public test fixtures and examples.

## v0.1.2

- Fixed alias-preservation behavior for migrated identities.

## v0.1.1

- Published package to PyPI via GitHub Trusted Publishing.

## v0.1.0

- Initial alpha release with SQLite store, Hermes provider, CLI, migration tools, review packets, and plugin shim.
