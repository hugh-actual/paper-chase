# paper-chase

A Python-based tool for organizing and managing your academic PDF library. Automatically extracts metadata, renames files to a consistent format, generates bibliographies, and helps identify duplicates.

## Documentation

- **[Changelog](docs/CHANGELOG.md)** - Version history and updates
- **[UV Setup Guide](docs/UV_SETUP.md)** - Package manager installation and setup

## What It Does

- **Extracts metadata** from PDF files (author, title, year, publisher)
- **Renames files** using a consistent naming scheme (e.g., `Hastie_et_al_Elements_Statistical_Learning.pdf`)
- **Generates bibliographies** in Harvard style format
- **Detects duplicates** using file hashing and similarity matching
- **Validates consistency** between your files and metadata

## Quick Start

### Prerequisites

- Python 3.11+
- `uv` package manager
- `make` (standard on macOS/Linux)

### Setup

1. **Configure your environment**:
   ```bash
   cd ~/paper-chase
   cp .env.example .env
   nano .env  # Edit paths as needed
   ```

   `.env.example` ships `~`-relative paths (`~/documents`, `~/paper-chase`); point
   them wherever you keep your library. Every `make` target reads these, so getting
   them right here is the whole of the configuration.

2. **Install dependencies**:
   ```bash
   uv sync
   ```

   Every `make` target runs through `uv run`, which bootstraps the environment on
   first use — so this step mainly gets the wait over with up front, and surfaces a
   broken Python or `uv` install immediately rather than mid-workflow.

3. **Check the install**:
   ```bash
   make test
   ```

   Note that `make verify` checks your *collection*, not your installation — on a
   fresh, empty library it prints an all-clear regardless of whether anything works.

### Essential Commands

Four simple commands handle most workflows:

```bash
make status         # Check collection status and get recommendations
make ingest         # Process new PDFs and verify
make detect-all     # Find issues (duplicates, unknown authors, broken titles, metadata mismatches)
make update-all     # Apply all fixes and verify
```

**Tip**: Run `make status` to see what needs attention and get specific recommendations.

## Common Workflows

### 1. Processing New PDFs

1. **Add PDFs** to the `todo/` directory inside your configured `DOCS_BASE_DIR`

2. **Run the ingest pipeline**:
   ```bash
   make ingest
   ```
   This processes new files, then verifies your collection. A genuine failure (a file that
   couldn't be moved, or `references.json`/`references.md` failing to write) exits nonzero
   and `make ingest` stops *before* running `verify`; a clean run — including one with only
   routine conflicts or skipped files — exits 0 and proceeds to `verify` as usual.

3. **Check status**:
   ```bash
   make status
   ```
   Shows you what happened, including any files still held in `todo/`, and what to do next.

4. **Resolve held duplicates**, if any:
   ```bash
   make quarantine-held         # dry run: lists what would move
   make quarantine-held APPLY=1 # moves them
   ```
   Files ingest held back as exact duplicates of an existing entry go here — never delete
   them from `todo/` by hand. Each one is re-checked at move time (the existing copy must
   still be present in `reference/` and hash identically) before being quarantined; a
   same-named file already in `quarantine/` is never overwritten.

### 2. Cleaning Up Your Collection

1. **Find all issues at once**:
   ```bash
   make detect-all
   ```
   This finds duplicates, unknown authors, broken titles, and metadata mismatches
   (`find-broken`, `find-unknown`, `detect-dups`, `find-mismatches`) in one go.

2. **Check what was found**:
   ```bash
   make status
   ```
   Shows you how many issues were detected and which files need review.

3. **Review and annotate** the JSON files in `json-output/`:
   - Mark duplicates with `"quarantine": true`
   - Fill in `suggested_author`, `suggested_title`, `suggested_year`, `suggested_publisher`
     for fixes
   - Every `suggested_*` field is independent: `null` keeps the current value, any string
     sets it. `suggested_publisher` is the one field where `""` is meaningful (it clears a
     bogus publisher) — everywhere else use `null`, not `""`, for "no change".

4. **Apply all fixes**:
   ```bash
   make update-all
   ```
   Applies all your annotations (`update-broken`, `update-unknown`, `update-dups`,
   `update-similar`, `update-mismatches`) and verifies the collection. A publisher-only
   update changes only the publisher — it doesn't rename the file.

   Each `update-*` step exits nonzero on a genuine failure — a file that could not
   be renamed or moved — which halts the chain instead of running to the end and
   reporting success. Entries it simply had nothing to do for (already applied on an
   earlier run, its detection JSON not generated yet, or annotated in two files at once)
   are reported as **Skipped**, not failures, so reruns are harmless. The last line of
   each step says which you got.

### 3. Check Collection Health

```bash
make status
```

Shows you:
- Collection size and last modified date
- Detection results and how many entries need review
- Specific recommendations for next steps

Example output:
```
📚 Collection: 250 entries
   Last modified: yesterday

📊 Detection Results:
   Similar Pairs (2 days ago): 3 pairs, 1 file annotated
   Unknown Authors: not generated

💡 Recommendations:
   1. Annotate 5 files in similar_pairs.json, then run 'make update-similar'
```

### 4. Individual Operations (Advanced)

Need fine-grained control? All individual commands are still available:

```bash
make find-unknown      # Find just unknown authors
make update-similar    # Apply just similar pair fixes
make verify            # Just verify consistency
```

Run `make help` to see all available commands.

## File Organization

```
<DOCS_BASE_DIR>/          # whatever you set in .env
├── reference/         # Your organized PDF library
├── quarantine/        # Duplicates and removed files (moves here never overwrite)
├── todo/              # New PDFs to process
├── history.jsonl       # Append-only journal of every move/rename/quarantine
├── references.json    # Metadata database (source of truth)
├── references.json.bak # Pre-run backup, copied before the first save of each run
└── references.md      # Human-readable bibliography (generated from `.json`)
```

## Metadata Extraction

When a filename matches a recognized pattern (`[Author]Title`, `YYYY-Author-Title`,
`YYYY_Book_Title`, `Author et al - Title`), that pattern wins field-by-field over embedded
PDF metadata, which is often generic junk (`/Title` "Microsoft Word - draft3.doc", `/Author`
"Administrator") — metadata only fills a field the filename left blank. An unstructured
filename instead lets non-junk PDF metadata win, falling back to the filename otherwise.
Publication year always comes from the filename (or "n.d." if none is found), never from
`/CreationDate`/`/ModDate` (those record when a file was scanned or saved, not published).
Publisher is likewise never taken from `/Producer` (the PDF-generating software); it starts
blank and is set later via `suggested_publisher`.

## Naming Convention

Files are renamed based on their authors:

- **1 author**: `Surname_Title.pdf`
- **2 authors**: `Surname1_Surname2_Title.pdf`
- **3+ authors**: `Surname1_et_al_Title.pdf`

Titles are sanitized by removing common words (a, an, the, of, etc.) while keeping technical terms (neural, statistical, quantum, etc.).

## Data Files

All metadata is stored in `references.json` (the source of truth), written atomically and
saved after every file during `make ingest` (not once at the end) so an interrupted run
can't lose a file's original name. `references.json.bak` holds the state from before the
run started. Other files are generated or journalled alongside it:

- `references.md` - Human-readable bibliography
- `history.jsonl` - Append-only journal: one JSON line per `ingest`/`relink`/`rename`/
  `quarantine`/`quarantine_held` event (plus a matching `_failed` event if a move is
  interrupted), written *before* the move it describes. `make recover` (dry run by
  default; `APPLY=1` writes) rebuilds orphaned or mispointed `references.json` entries
  from it, and `make verify` / `make status` use it to explain discrepancies.
- `json-output/*.json` - Working files for detection and fixes, including
  `metadata_mismatches.json` (publisher/filename mismatches from `find-mismatches`)

## Important Notes

### DO:
- ✅ Always run scripts through `make` targets (or `uv run python -m src.scripts...`)
- ✅ Run `make verify` after making changes
- ✅ Review conflict reports before manually fixing files
- ✅ Set `suggested_*` fields to `null` (not empty strings) when no change needed —
  except `suggested_publisher`, where `""` is a deliberate request to clear it

### DON'T:
- ❌ Edit `references.json` or `references.md` manually (use the scripts)
- ❌ Move files in `reference/` directory manually
- ❌ Delete `file_hash` fields from metadata

## Running Tests

```bash
# Run all tests
make test

# Format code
make format

# Check linting
make lint
```

338 tests covering all core utilities plus integration tests for the processing and update pipelines.

## All Available Commands

### Quick Start (Most Users)
- `make status` - Check collection status and get recommendations
- `make ingest` - Process new PDFs and verify
- `make detect-all` - Find all issues (duplicates, unknown authors, broken titles)
- `make update-all` - Apply all fixes and verify

### Individual Commands (Advanced)

Need fine-grained control? Run `make help` to see all commands:

| Category | Example Commands |
|----------|------------------|
| **Core Processing** | `process`, `generate` |
| **Detection** | `find-broken`, `find-unknown`, `detect-dups`, `find-mismatches` |
| **Updates** | `update-broken`, `update-unknown`, `update-dups`, `update-similar`, `update-mismatches` |
| **Verification** | `verify`, `validate` |
| **Recovery** | `recover`, `quarantine-held` — dry run by default, `APPLY=1` writes/moves |
| **Testing & QA** | `test`, `format`, `lint` |
| **Utility** | `extract FILE=path` |

## Troubleshooting

**Q: What should I do first?**
A: Run `make status` - it will tell you exactly what needs attention and recommend next steps.

**Q: Files remain in `todo/` after running `make ingest`**
A: Check `json-output/ingestion_conflicts.json` — it's written on every run (an empty
`conflicts` list when clean), so it always reflects the last ingest. Conflict detection is
hash-based, not filename-based: a distinct file that merely shares a generated filename with
an existing entry is ingested and suffixed (`_2`, `_3`, ...) and never held. A hash match is
held as one of:
- `hash_duplicate` — the matching entry's file is still present in `reference/`
  (`existing_file_present: true`). Resolve with `make quarantine-held` (dry run by default;
  `APPLY=1` moves) — it re-verifies the duplicate at move time and quarantines it, never
  deleting or overwriting.
- a silent relink (not a conflict) — if the matching entry's file is *missing* from
  `reference/`, the incoming file is treated as that file's return and moved into place
  under the entry's name.
- `hash_matches_missing_file` — the matching entry's file is missing, but another file now
  occupies its name, so restoring would overwrite that file; held for manual review.
- `previously_quarantined` — the hash matches something quarantined earlier that's still in
  `quarantine/`; re-ingesting would silently undo that removal, so it's held instead.

**Q: How do I find and fix duplicates?**
A: Run `make detect-all` to find all duplicates, then `make status` to see how many were found. Review the JSON files in `json-output/`, then run `make update-all` to apply your decisions.

**Q: What if metadata extraction fails?**
A: The tool will use "Unknown" as author and continue. Run `make detect-all` to find these entries, then fix them by annotating `json-output/unknown_authors.json`.

**Q: Can I change the similarity threshold for duplicates?**
A: Yes, edit the threshold in `src/scripts/detection/detect_duplicates.py` (default is 70%).

## Getting Help

- **Script Documentation**: Each script has help text at the top of the file

---

**Pro Tip**: Use `make status` whenever you're not sure what to do next. It shows you what's been done and recommends the next step. The typical workflow is: `make detect-all` → annotate JSON files → `make update-all`.
