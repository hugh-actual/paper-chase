# Documentation Update Summary

**Last Updated**: 2026-07-24

---

## Broken-Title Patterns Made Generic (2026-07-24)

- Moved collection-specific title patterns out of `find_broken_titles.py` and into
  the untracked `local_title_patterns.json`, where the module docstring already
  said they belonged. Tracked source now holds only generic checks: authoring-tool
  signatures and structural damage, never subject matter
- Added the generic patterns that were missing, notably `Microsoft Word - ` (a very
  common broken PDF title that previously passed through and was filed as a real
  entry), plus PowerPoint/InDesign artifacts, `Slide N`/`Chapter N`, and `.docx`/
  `.pptx` extensions. Placeholder and short-title matching is now case-insensitive
- Added unit tests for the built-in patterns, which had none, including a guard that
  fails if topic-based literals are reintroduced to tracked source. Its fixtures are
  invented rather than real titles, so the guard cannot itself leak what it protects
  against (131 → 153 tests)

---

## Ingest Conflict Detection Fix (2026-07-24)

- Fixed byte-identical duplicates being silently ingested when they arrived in
  the same `todo/` batch. `DocumentProcessor` loaded the existing references
  once and never updated them mid-run, so `check_hash_conflict` only ever saw
  pre-run state and the second copy entered the library under a `_2` suffix.
  Duplicates in a *later* batch were already caught correctly
- Conflict detection is now explicitly hash-based, not filename-based: a
  byte-identical file is always held in `todo/` (same batch or not), while a
  distinct file that merely generates the same name is ingested and suffixed
- Target filenames are now reserved against `references.json` as well as the
  current batch and `reference/`, so an orphaned entry (in JSON, missing on
  disk) can no longer have its filename reused
- `DocumentProcessor` now loads references once, mutates in memory, and saves
  once per run — matching the pattern `UpdateStep` already used, and removing a
  full JSON rewrite per ingested file
- `todo/` is scanned in sorted order, so when two files collide on name the
  alphabetically-first one deterministically keeps the unsuffixed name
- Added `build_reference_entry()` to `utils.py`, shared by
  `add_entry_to_references_json` and the in-memory path so both produce
  identically-shaped entries
- Added multi-file `DocumentProcessor` integration tests, which did not exist
  before: within-batch duplicate (asserting a rejected file does not consume a
  suffix slot), name collision with distinct content, deterministic ordering,
  and orphaned-entry filename reservation (131 tests total)

---

## Bug Fixes and Simplification (2026-07-19)

- Fixed workflow-breaking bugs left by the `src/` refactor: references.md was
  never regenerated after process/update runs; conflict detection crashed
  `process_documents.py` before writing `ingestion_conflicts.json`; broken
  config imports made every `update-*`, `detect-*`, and `status` target fail
- Added integration tests for `UpdateStep` and `DocumentProcessor` (tmp-dir
  sandboxes; 122 tests total)
- Removed one-time fix scripts (`fixes/`), `normalize_references_spacing.py`,
  `detect_similar_pairs.py` (merged into `detect_duplicates.py`), and unused
  references.md-editing helpers
- references.md is now sorted by author surname, then title
- `UpdateStep` loads/saves references.json once per run; files are renamed
  before metadata is updated
- Documentation brought in line with the actual repo layout and Python 3.11

---

## Refactoring Update (2026-01-11)

- Migrate scripts to github

---

## Refactoring Update (2026-01-04)

- More/better tests
- Add linting and formatting

---

## Environment Configuration Update (2025-12-30)

- Git-Ready Refactoring
- Scripts Updated
- All Python scripts now import from `config.py` instead of hardcoded paths

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `DOCS_BASE_DIR` | Base docs directory |
| `PROCESSOR_DIR` | paper-chase directory |
| `REFERENCE_DIR` | Renamed PDFs location |
| `QUARANTINE_DIR` | Off-topic files location |
| `TODO_DIR` | Inbox for new PDFs |
| `MARKDOWN_DIR` | Logs and reports |
| `REFERENCES_FILE` | Bibliography file path |
| `JSON_OUTPUT_DIR` | JSON data files location |

### Setup for New Users

```bash
cp .env.example .env
nano .env  # Edit paths
uv pip install python-dotenv
```

---

## Testing Update (2025-12-30)

- Added Unit Tests
- Running Tests

```bash
uv run pytest tests/ -v
```

---

## Refactoring Update (2025-12-30)

- Shared utils module
- Deleted some obsolete scripts
- Better documentation


| File | Purpose | Status |
|------|---------|--------|
| `UV_SETUP.md` | uv installation guide | Current |
| `CHANGELOG.md` | This changelog | Updated 2025-12-30 |
