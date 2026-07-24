#!/usr/bin/env python3
"""
Document Organization Script
Processes academic PDFs: extracts metadata, renames files, moves to reference folder,
and generates Harvard-style bibliography.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict
from pypdf import PdfReader

# Configuration is accessed as config.<NAME> so tests can redirect
# paths by patching src.lib.config alone
from src.lib import config

# Import shared utilities
from src.lib.utils import (
    build_reference_entry,
    regenerate_references_md,
    load_references_json,
    save_references_json,
    create_reference_stub,
    check_hash_conflict,
    check_filename_conflict,
)

# Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

# Keep only GENERIC_TERMS (used locally in this script)
GENERIC_TERMS = {"introduction", "guide", "handbook", "manual"}


class DocumentProcessor:
    def __init__(self):
        self.processed_files = []
        self.log_entries = []
        self.skipped_large = []
        self.skipped_non_pdf = []
        self.errors = []
        self.conflicts = []  # Track files with hash/filename conflicts
        self.existing_references = None  # Pre-loaded references for conflict checking

    def extract_pdf_metadata(self, pdf_path: Path) -> Dict[str, str]:
        """Extract metadata from PDF file."""
        metadata = {"title": None, "author": None, "year": None, "publisher": None}

        try:
            with open(pdf_path, "rb") as f:
                pdf_reader = PdfReader(f)
                info = pdf_reader.metadata

                if info:
                    metadata["title"] = info.get("/Title", None)
                    metadata["author"] = info.get("/Author", None)

                    # Try to extract year from creation or modification date
                    for date_key in ["/CreationDate", "/ModDate"]:
                        if date_key in info and info[date_key]:
                            date_str = str(info[date_key])
                            year_match = re.search(r"(\d{4})", date_str)
                            if year_match:
                                metadata["year"] = year_match.group(1)
                                break

                    metadata["publisher"] = info.get("/Producer", None)
        except Exception as e:
            self.log_entries.append(
                f"Error extracting metadata from {pdf_path.name}: {str(e)}"
            )

        return metadata

    def extract_from_filename(self, filename: str) -> Dict[str, str]:
        """Extract author, title, and year from filename patterns."""
        info = {"author": None, "title": None, "year": None}

        # Remove extension
        name = filename.rsplit(".", 1)[0]

        # Pattern 1: [Author]Title
        match = re.match(r"\[([^\]]+)\](.+)", name)
        if match:
            info["author"] = match.group(1).strip()
            info["title"] = match.group(2).strip()
            return info

        # Pattern 2: YYYY-Author-Title
        match = re.match(r"(\d{4})-([^-]+)-(.+)", name)
        if match:
            info["year"] = match.group(1)
            info["author"] = match.group(2).strip()
            info["title"] = match.group(3).strip()
            return info

        # Pattern 3: YYYY_Book_Title or similar
        match = re.match(r"(\d{4})_(?:Book|Article)_(.+)", name)
        if match:
            info["year"] = match.group(1)
            info["title"] = match.group(2).strip()
            return info

        # Pattern 4: arxiv number + title
        match = re.match(r"(\d{4}\.\d+)\s*(.+)?", name)
        if match:
            info["title"] = match.group(2).strip() if match.group(2) else match.group(1)
            return info

        # Default: treat whole name as title
        info["title"] = name

        # Try to extract year from anywhere in filename
        year_match = re.search(r"(\d{4})", name)
        if year_match:
            info["year"] = year_match.group(1)

        return info

    def process_file(self, file_path: Path) -> bool:
        """Process a single PDF file with pre-flight conflict detection."""
        try:
            # Extract metadata
            metadata = self.extract_pdf_metadata(file_path)
            filename_info = self.extract_from_filename(file_path.name)

            # Merge information (prefer metadata, fallback to filename)
            author = metadata.get("author") or filename_info.get("author")
            title = (
                metadata.get("title") or filename_info.get("title") or file_path.stem
            )
            year = metadata.get("year") or filename_info.get("year") or "n.d."
            publisher = metadata.get("publisher")

            # Create reference stub with hash and filename before processing.
            # Reserve names against both this batch's processed files and
            # references.json (including orphaned entries with no file on
            # disk), so a suffix is never reused.
            processed_filenames = {p["new_filename"] for p in self.processed_files} | {
                e["filename"] for e in self.existing_references
            }
            stub = create_reference_stub(
                file_path=file_path,
                author=author,
                title=title,
                year=year if year != "n.d." else None,
                publisher=publisher,
                processed_files=processed_filenames,
            )

            # Check for conflicts against existing references
            conflicts_found = []

            hash_conflict = check_hash_conflict(
                stub["file_hash"], self.existing_references
            )
            if hash_conflict:
                conflicts_found.append(
                    {
                        "type": "hash_duplicate",
                        "existing_filename": hash_conflict["filename"],
                        "existing_title": hash_conflict.get("title", ""),
                        "message": f"File hash matches existing entry: {hash_conflict['filename']}",
                    }
                )

            filename_conflict = check_filename_conflict(
                stub["filename"], self.existing_references
            )
            if filename_conflict:
                conflicts_found.append(
                    {
                        "type": "filename_collision",
                        "existing_filename": filename_conflict["filename"],
                        "existing_title": filename_conflict.get("title", ""),
                        "message": (
                            f"Filename would collide with existing: "
                            f"{filename_conflict['filename']}"
                        ),
                    }
                )

            # If conflicts found, skip this file and keep in todo/
            if conflicts_found:
                self.conflicts.append(
                    {
                        "file_path": str(file_path),
                        "original_filename": file_path.name,
                        "stub": stub,
                        "conflicts": conflicts_found,
                    }
                )
                self.log_entries.append(
                    f"CONFLICT: {file_path.name} - {conflicts_found[0]['message']}"
                )
                return False  # Skip this file

            new_filename = stub["filename"]

            # Check for excessively long filename
            if len(new_filename) > 150:
                self.log_entries.append(
                    f"Long filename ({len(new_filename)} chars): {file_path.name} -> {new_filename}"
                )

            # Move file from todo/ to reference/ (changed from copy)
            dest_path = config.REFERENCE_DIR / new_filename
            shutil.move(str(file_path), str(dest_path))

            # Append to the in-memory references list (saved once at the end
            # of run()) so later files in this batch see it immediately via
            # self.existing_references, closing the within-batch duplicate
            # window.
            self.existing_references.append(
                build_reference_entry(
                    stub["author_names"],
                    stub["year"],
                    stub["title"],
                    stub["publisher"],
                    new_filename,
                    original_filename=file_path.name,
                    file_hash=stub["file_hash"],
                )
            )

            # Record processing
            self.processed_files.append(
                {
                    "original_filename": file_path.name,
                    "new_filename": new_filename,
                    "author": author,
                    "title": title,
                    "year": year,
                    "file_hash": stub["file_hash"],
                }
            )

            return True

        except Exception as e:
            self.errors.append(f"Error processing {file_path.name}: {str(e)}")
            return False

    def run(self):
        """Main processing loop."""
        print("Starting document processing...")

        # Pre-load existing references for conflict checking
        print("Loading existing references...")
        self.existing_references = load_references_json()
        print(f"  Found {len(self.existing_references)} existing entries")

        # Scan files (sorted for deterministic ingest order: when two files
        # would collide on filename, the alphabetically-first one wins the
        # clean name)
        all_files = sorted(config.TODO_DIR.glob("*"))
        pdf_files = [f for f in all_files if f.suffix.lower() == ".pdf"]
        non_pdf_files = [
            f for f in all_files if f.suffix.lower() != ".pdf" and f.is_file()
        ]

        print(
            f"Found {len(pdf_files)} PDF files and {len(non_pdf_files)} non-PDF files"
        )

        # Categorize PDFs by size
        small_pdfs = []
        large_pdfs = []

        for pdf in pdf_files:
            size = pdf.stat().st_size
            if size >= MAX_FILE_SIZE:
                large_pdfs.append(pdf)
                self.skipped_large.append(f"{pdf.name} ({size / 1024 / 1024:.1f}MB)")
            else:
                small_pdfs.append(pdf)

        print(
            f"Processing {len(small_pdfs)} PDFs (<50MB), skipping {len(large_pdfs)} large PDFs"
        )

        # Record non-PDF files
        for f in non_pdf_files:
            self.skipped_non_pdf.append(f.name)

        # Process small PDFs
        for i, pdf_file in enumerate(small_pdfs, 1):
            print(f"Processing {i}/{len(small_pdfs)}: {pdf_file.name}")
            self.process_file(pdf_file)

            # Progress indicator
            if i % 50 == 0:
                print(f"  ... {i} files processed")

        # Save references.json once, then generate references.md from it
        if self.processed_files:
            print("Saving references.json...")
            save_references_json(self.existing_references)
            print("Generating references.md from JSON...")
            if regenerate_references_md():
                print("  ✓ References.md generated successfully")
            else:
                print("  ⚠ Warning: generate_references_md.py failed")

        # Write log
        print("Writing log...")
        with open(config.MARKDOWN_DIR / "log.md", "w", encoding="utf-8") as f:
            f.write("# Document Processing Log\n\n")
            f.write("## Summary\n\n")
            f.write(f"- **Total PDFs processed**: {len(self.processed_files)}\n")
            f.write(
                f"- **Conflicts detected (kept in todo/)**: {len(self.conflicts)}\n"
            )
            f.write(f"- **Large PDFs skipped (≥50MB)**: {len(self.skipped_large)}\n")
            f.write(f"- **Non-PDF files skipped**: {len(self.skipped_non_pdf)}\n")
            f.write(f"- **Errors encountered**: {len(self.errors)}\n")
            f.write(f"- **Issues logged**: {len(self.log_entries)}\n\n")

            if self.conflicts:
                f.write("## Files with Conflicts (Kept in todo/)\n\n")
                for conflict_info in self.conflicts:
                    f.write(f"### {conflict_info['original_filename']}\n\n")
                    for c in conflict_info["conflicts"]:
                        f.write(f"- **{c['type']}**: {c['message']}\n")
                        f.write(f"  - Existing file: `{c['existing_filename']}`\n")
                        if c.get("existing_title"):
                            f.write(f"  - Existing title: {c['existing_title']}\n")
                    f.write("\n")

            if self.skipped_large:
                f.write("## Large Files Skipped (≥50MB)\n\n")
                for item in self.skipped_large:
                    f.write(f"- {item}\n")
                f.write("\n")

            if self.skipped_non_pdf:
                f.write("## Non-PDF Files Skipped\n\n")
                for item in self.skipped_non_pdf:
                    f.write(f"- {item}\n")
                f.write("\n")

            if self.errors:
                f.write("## Errors\n\n")
                for error in self.errors:
                    f.write(f"- {error}\n")
                f.write("\n")

            if self.log_entries:
                f.write("## Issues and Warnings\n\n")
                for entry in self.log_entries:
                    f.write(f"- {entry}\n")
                f.write("\n")

        # Write JSON conflict report if there are conflicts
        if self.conflicts:
            conflict_report = {
                "generated": datetime.now().isoformat(),
                "conflicts": self.conflicts,
            }
            conflict_file = config.JSON_OUTPUT_DIR / "ingestion_conflicts.json"
            with open(conflict_file, "w", encoding="utf-8") as f:
                json.dump(conflict_report, f, indent=2, ensure_ascii=False)
            print(f"  Conflict report written to: {conflict_file}")

        print("\n✓ Processing complete!")
        print(f"  - Processed: {len(self.processed_files)} files")
        print(f"  - Conflicts: {len(self.conflicts)} files (kept in todo/)")
        print(f"  - Skipped (large): {len(self.skipped_large)} files")
        print(f"  - Skipped (non-PDF): {len(self.skipped_non_pdf)} files")
        print(f"  - Errors: {len(self.errors)}")
        print(f"  - Issues: {len(self.log_entries)}")


if __name__ == "__main__":
    processor = DocumentProcessor()
    processor.run()
