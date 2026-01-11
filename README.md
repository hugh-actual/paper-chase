# paper-chase

A Python-based tool for organizing and managing your academic PDF library. Automatically extracts metadata, renames files to a consistent format, generates bibliographies, and helps identify duplicates.

## Documentation

- **[Changelog](docs/CHANGELOG.md)** - Version history and updates
- **[UV Setup Guide](docs/UV_SETUP.md)** - Package manager installation and setup
- **[Claude Reference Guide](claude.md)** - Comprehensive technical documentation

## What It Does

- **Extracts metadata** from PDF files (author, title, year, publisher)
- **Renames files** using a consistent naming scheme (e.g., `Hastie_et_al_Elements_Statistical_Learning.pdf`)
- **Generates bibliographies** in Harvard style format
- **Detects duplicates** using file hashing and similarity matching
- **Validates consistency** between your files and metadata

## Quick Start

### Prerequisites

- Python 3.9+
- `uv` package manager (installed at `~/.local/bin/uv`)
- `make` (standard on macOS/Linux)

### Setup

1. **Configure your environment**:
   ```bash
   cd ~/{git_folder}/paper-chase
   cp .env.example .env
   nano .env  # Edit paths as needed
   ```

2. **Verify installation**:
   ```bash
   make verify
   ```

### Using the Makefile

All scripts can be run using simple `make` commands. To see all available commands:

```bash
make          # or: make help
```

This displays all available targets organized by category (Core Processing, Detection, Updates, Verification, Testing, etc.).

### Processing New PDFs

1. **Add PDFs** to `~/{docs_folder}/todo/`

2. **Run the processor**:
   ```bash
   make process
   ```

3. **Review the results**:
   - Successfully processed files → moved to `~/{docs_folder}/reference/`
   - Files with conflicts → remain in `todo/` for manual review
   - Check `json-output/ingestion_conflicts.json` for conflict details

## Common Tasks

### Check Your Library Status

```bash
make verify
```

Shows you:
- Files not in the bibliography
- Bibliography entries without files
- Suspicious filenames

### Find and Remove Duplicates

```bash
# 1. Detect similar files
make detect-similar

# 2. Review json-output/similar_pairs.json
#    Mark files to quarantine with "quarantine": true

# 3. Apply your decisions
make update-similar
```

### Fix Unknown Authors

```bash
# 1. Find entries with unknown authors
make find-unknown

# 2. Edit json-output/unknown_authors.json
#    Add suggested_author, suggested_title, suggested_year

# 3. Apply changes
make update-unknown
```

### Inspect a Single PDF

```bash
make extract FILE=/path/to/file.pdf
```

## File Organization

```
~/{docs_folder}/
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
- ✅ Always run scripts through `uv run python script_name.py`
- ✅ Use `verify_files_and_metadata.py` after making changes
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

118 tests covering all core utilities.

## All Available Commands

Run `make` or `make help` to see the complete list of available commands:

| Category | Commands |
|----------|----------|
| **Core Processing** | `process`, `generate`, `normalize` |
| **Detection** | `find-broken`, `find-unknown`, `detect-dups`, `detect-similar` |
| **Updates** | `update-broken`, `update-unknown`, `update-dups`, `update-similar` |
| **Verification** | `verify`, `validate` |
| **One-time Fixes** | `add-hashes`, `fix-filenames`, `fix-authors` |
| **Testing & QA** | `test`, `format`, `lint` |
| **Utility** | `extract FILE=path` |

**Note**: You can also run scripts directly using `uv run python script_name.py` if preferred.

## Troubleshooting

**Q: Files remain in `todo/` after processing**
A: Check `json-output/ingestion_conflicts.json` - these files likely have hash conflicts or filename collisions with existing entries.

**Q: How do I know if I have duplicates?**
A: Run `detect_similar_pairs.py` - it will find files with the same author and similar titles (70%+ match).

**Q: Can I change the similarity threshold?**
A: The threshold is hardcoded to 70% in the scripts. You can edit it in `detect_similar_pairs.py` if needed.

**Q: What if metadata extraction fails?**
A: The script will use "Unknown" as author and continue. You can fix these later using `find_unknown_authors_for_review.py`.

## Getting Help

- **Reference Guide**: See `claude.md` for detailed technical documentation
- **Script Documentation**: Each script has help text at the top of the file

---

**Pro Tip**: The workflow is detect → annotate → apply. Detection scripts generate JSON files, you edit them to mark your decisions, then update scripts apply those changes.
