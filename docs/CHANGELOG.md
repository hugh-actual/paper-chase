# Changelog

- **2026-07-25** — Config paths now expand `~` correctly (including interpolated derived
  vars), path-building boilerplate was deduplicated into one helper, and update scripts
  exit nonzero on genuine failures while routine "not found" outcomes stay non-fatal.
- **2026-07-24** — Collection-specific title patterns moved out of tracked source into an
  untracked local file; broken-title detection gained more generic patterns and test
  coverage.
- **2026-07-24** — Fixed byte-identical duplicates being silently ingested when dropped
  into `todo/` in the same batch; conflict detection is now explicitly hash-based rather
  than filename-based.
- **2026-07-19** — Fixed post-refactor regressions (references.md not regenerating,
  conflict detection crashing, broken config imports) and added integration test
  coverage.
- **2026-01-11** — Migrated scripts to GitHub.
- **2026-01-04** — Expanded test coverage; added linting and formatting.
- **2025-12-30** — Refactored config loading to use environment variables instead of
  hardcoded paths; added a shared utils module and unit tests.
