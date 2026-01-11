.PHONY: help process generate normalize \
        find-broken find-unknown detect-dups detect-similar \
        update-broken update-unknown update-dups update-similar \
        verify validate \
        add-hashes fix-filenames fix-authors \
        test format lint extract

# Default target
help:
	@echo "Document Processor - Available Commands"
	@echo ""
	@echo "Core Processing:"
	@echo "  make process        Process new PDFs from todo/"
	@echo "  make generate       Generate references.md from references.json"
	@echo "  make normalize      Normalize spacing in references.md"
	@echo ""
	@echo "Detection (creates JSON for review):"
	@echo "  make find-broken    Find broken titles"
	@echo "  make find-unknown   Find unknown authors"
	@echo "  make detect-dups    Comprehensive duplicate detection"
	@echo "  make detect-similar Find similar pairs"
	@echo ""
	@echo "Updates (apply annotated JSON changes):"
	@echo "  make update-broken  Apply broken title fixes"
	@echo "  make update-unknown Apply unknown author fixes"
	@echo "  make update-dups    Apply exact duplicate fixes"
	@echo "  make update-similar Apply similar pair fixes"
	@echo ""
	@echo "Verification:"
	@echo "  make verify         Check files vs metadata consistency"
	@echo "  make validate       Validate references.json matches references.md"
	@echo ""
	@echo "One-time Fixes:"
	@echo "  make add-hashes     Add SHA256 hashes to all entries"
	@echo "  make fix-filenames  Fix mismatched filenames (interactive)"
	@echo "  make fix-authors    Fix duplicate authors"
	@echo ""
	@echo "Testing & QA:"
	@echo "  make test           Run pytest"
	@echo "  make format         Run black formatter"
	@echo "  make lint           Run flake8 linter"
	@echo ""
	@echo "Utility:"
	@echo "  make extract FILE=path  Extract metadata from a PDF"

# Core Processing
process:
	uv run python -m src.scripts.core.process_documents

generate:
	uv run python -m src.scripts.core.generate_references_md

normalize:
	uv run python -m src.scripts.utilities.normalize_references_spacing

# Detection
find-broken:
	uv run python -m src.scripts.detection.find_broken_titles

find-unknown:
	uv run python -m src.scripts.detection.find_unknown_authors_for_review

detect-dups:
	uv run python -m src.scripts.detection.detect_duplicates

detect-similar:
	uv run python -m src.scripts.detection.detect_similar_pairs

# Updates
update-broken:
	uv run python -m src.scripts.updates.update_broken_titles

update-unknown:
	uv run python -m src.scripts.updates.update_unknown_authors

update-dups:
	uv run python -m src.scripts.updates.update_exact_duplicates

update-similar:
	uv run python -m src.scripts.updates.update_similar_pairs

# Verification
verify:
	uv run python -m src.scripts.core.verify_files_and_metadata

validate:
	uv run python -m src.scripts.utilities.validate_references_json

# One-time Fixes
add-hashes:
	uv run python -m src.scripts.fixes.add_file_hashes

fix-filenames:
	uv run python -m src.scripts.fixes.fix_mismatched_filenames

fix-authors:
	uv run python -m src.scripts.fixes.fix_duplicate_authors

# Testing & QA
test:
	uv run pytest tests/ -v

format:
	uv run black src/ tests/

lint:
	uv run flake8 src/ tests/ --max-line-length=100

# Utility
extract:
ifndef FILE
	@echo "Usage: make extract FILE=/path/to/file.pdf"
else
	uv run python -m src.scripts.utilities.extract_metadata $(FILE)
endif
