# Changelog

## Unreleased

## v0.3.0

### Changed

- Changed `install-shim` to prefer the package-provided plugin skill `local_memory:maintenance` instead of copying `local-memory-maintenance` into `~/.hermes/skills` by default.
- Made `install-shim` remove managed legacy copied maintenance skills when provenance confirms they were installed by `hermes-local-memory`, preventing stale copied runbooks from shadowing the packaged skill.
- Kept `sync-skills` as an explicit legacy compatibility path for older Hermes installations that cannot load plugin-provided skills.
- Updated Local Memory maintenance docs and agent guidance to treat copied `local-memory-maintenance` as legacy fallback only.

## v0.2.3

### Changed

- Clarified packaged Local Memory maintenance guidance so first Honcho migration review is treated as a one-time adoption step, not recurring nightly report noise.
- Updated maintenance reports to omit routine skipped imported-Honcho bulk-promotion/migration status after first migration has completed unless a fresh import or actionable issue requires review.

## v0.2.2

### Added

- Added `hermes-local-memory sync-skills` to install/update the packaged `local-memory-maintenance` skill into a Hermes home directory without modifying Hermes Agent.
- Made `install-shim` register the package-provided maintenance skill and remove managed legacy copied skills by default; `sync-skills` remains an explicit compatibility fallback.
- Added provenance metadata when replacing an existing installed maintenance skill. Existing skill directories are removed before sync so stale copies/backups are not picked up as extra Hermes skills.

### Changed

- Shortened the recommended cron prompt so deployment-specific cron jobs load the packaged skill and avoid duplicating the full maintenance flow.

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
