# Changelog

- **2026-09-19** — Ingest and updates now journal every move to `history.jsonl` before it
  happens and save `references.json` per-file (atomically, with a `.bak`), so an
  interrupted run no longer loses a file's original name; `make recover` rebuilds
  orphaned or mispointed entries from the journal. Hash conflicts that pointed at a
  missing file now relink or are held precisely, instead of telling you to delete the
  only surviving copy; `make quarantine-held` resolves held duplicates without manual
  deletion, and quarantine never overwrites a same-named file. `make ingest` now exits
  nonzero on genuine failures, matching the update scripts.
- **2026-09-19** — Embedded PDF metadata no longer beats a well-formed filename (a
  curated name now wins field-by-field over scanner/software junk); year is always taken
  from the filename, never `/CreationDate`; publisher is never taken from `/Producer`.
  Added `find-mismatches`/`update-mismatches` to audit and fix metadata minted before
  this change. NFD-decomposed (macOS) filenames no longer lose accented characters.
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
