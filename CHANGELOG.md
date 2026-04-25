# Changelog

## Unreleased

### Fixed

- Made deterministic maintenance conservative for imported Honcho candidates: `honcho-*` / `honcho-api-*` candidate facts are no longer bulk-promoted by `--promote-candidates`.
- Stopped maintenance from appending every existing active fact into compact peer cards. Cards are compact synthesized views and should be changed through `memory_profile`, card review, or validated `card_replace` patches.
- Made provider `memory_maintenance` return compact changed-pair summaries instead of very large full pair payloads, making scheduled jobs less prompt-heavy.

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
