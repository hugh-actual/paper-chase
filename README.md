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
make detect-all     # Find issues (duplicates, unknown authors, broken titles)
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
   This processes new files and verifies your collection in one step.

3. **Check status**:
   ```bash
   make status
   ```
   Shows you what happened and what to do next.

### 2. Cleaning Up Your Collection

1. **Find all issues at once**:
   ```bash
   make detect-all
   ```
   This finds duplicates, unknown authors, and broken titles in one go.

2. **Check what was found**:
   ```bash
   make status
   ```
   Shows you how many issues were detected and which files need review.

3. **Review and annotate** the JSON files in `json-output/`:
   - Mark duplicates with `"quarantine": true`
   - Fill in `suggested_author`, `suggested_title`, `suggested_year` for fixes

4. **Apply all fixes**:
   ```bash
   make update-all
   ```
   Applies all your annotations and verifies the collection.

   Each `update-*` step exits nonzero on a genuine failure — a file that could not
   be renamed or moved — which halts the chain instead of running to the end and
   reporting success. Entries it simply had nothing to do for (already applied on an
   earlier run, or annotated in two files at once) are reported as **Skipped**, not
   failures, so reruns are harmless. The last line of each step says which you got.

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
├── reference/        # Your organized PDF library
├── quarantine/       # Duplicates and removed files
├── todo/             # New PDFs to process
├── references.json   # Metadata database (source of truth)
└── references.md     # Human-readable bibliography (generated from `.json`)
```

## Naming Convention

Files are renamed based on their authors:

- **1 author**: `Surname_Title.pdf`
- **2 authors**: `Surname1_Surname2_Title.pdf`
- **3+ authors**: `Surname1_et_al_Title.pdf`

Titles are sanitized by removing common words (a, an, the, of, etc.) while keeping technical terms (neural, statistical, quantum, etc.).

## Data Files

All metadata is stored in `references.json` (the source of truth). Other files are generated from it:

- `references.md` - Human-readable bibliography
- `json-output/*.json` - Working files for detection and fixes

## Important Notes

### DO:
- ✅ Always run scripts through `make` targets (or `uv run python -m src.scripts...`)
- ✅ Run `make verify` after making changes
- ✅ Review conflict reports before manually fixing files
- ✅ Set `suggested_*` fields to `null` (not empty strings) when no change needed

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

171 tests covering all core utilities plus integration tests for the processing and update pipelines.

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
| **Detection** | `find-broken`, `find-unknown`, `detect-dups` |
| **Updates** | `update-broken`, `update-unknown`, `update-dups`, `update-similar` |
| **Verification** | `verify`, `validate` |
| **Testing & QA** | `test`, `format`, `lint` |
| **Utility** | `extract FILE=path` |

## Troubleshooting

**Q: What should I do first?**
A: Run `make status` - it will tell you exactly what needs attention and recommend next steps.

**Q: Files remain in `todo/` after running `make ingest`**
A: Check `json-output/ingestion_conflicts.json` - these files likely have hash conflicts or filename collisions with existing entries. Conflict detection is hash-based, not filename-based: a byte-identical duplicate is always held in `todo/`, even if it arrived in the same batch as its first copy, while a distinct file that merely shares a generated name is ingested and suffixed (`_2`, `_3`, ...). There is no automatic resolution step for a held duplicate - once you've confirmed it's really unwanted, delete it from `todo/` (or move it elsewhere) yourself.

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
