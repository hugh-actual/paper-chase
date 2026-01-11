# Documentation Update Summary

**Last Updated**: 2026-01-11

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
- Updated CLAUDE.md
- Better documentation


| File | Purpose | Status |
|------|---------|--------|
| `CLAUDE.md` | Main reference guide | Updated 2025-12-30 |
| `UV_SETUP.md` | uv installation guide | Current |
| `CHANGELOG.md` | This changelog | Updated 2025-12-30 |

---

## Refactoring Update (2026-01-04)

- More/better tests
- Add linting and formatting

---

## Refactoring Update (2026-01-11)

- Migrate scripts to github
