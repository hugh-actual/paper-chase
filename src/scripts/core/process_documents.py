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
from typing import Dict, Optional
from pypdf import PdfReader

# Configuration is accessed as config.<NAME> so tests can redirect
# paths by patching src.lib.config alone
from src.lib import config
from src.lib.steps import StepError

# Import shared utilities
from src.lib.utils import (
    append_history,
    build_reference_entry,
    calculate_file_hash,
    regenerate_references_md,
    load_references_json,
    save_references_json,
    create_reference_stub,
    check_hash_conflict,
    _atomic_write_text,
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
        self.conflicts = []  # Track files with hash/filename conflicts
        self.relinked = []  # Files that restored an entry's missing file
        self.existing_references = None  # Pre-loaded references for conflict checking
        # references.json is saved after every file; only the first save of
        # the run backs up, so references.json.bak is the pre-run state.
        self._backed_up = False

        # Single record of everything that went wrong, with the same
        # fatal/routine split as UpdateStep: a fatal error (an exception
        # while ingesting a file, references.json or references.md failing
        # to write) makes the script exit nonzero; conflicts and skipped
        # large/non-PDF files are routine and don't.
        self.errors: list[StepError] = []

    def _record_error(
        self, phase: str, filename: str, message: str, fatal: bool = False
    ) -> None:
        """Record a failure or a skip. See StepError for the distinction."""
        self.errors.append(StepError(phase, filename, message, fatal))

    @property
    def fatal_errors(self) -> list[StepError]:
        return [e for e in self.errors if e.fatal]

    @property
    def skipped_errors(self) -> list[StepError]:
        return [e for e in self.errors if not e.fatal]

    @classmethod
    def run_as_main(cls) -> int:
        """Entry point for `python -m`: nonzero only on genuine failures,
        so `make ingest` stops before `verify` prints a misleading
        all-clear. Conflicts and skipped files still exit 0."""
        return 1 if cls().run()["fatal_errors"] else 0

    @staticmethod
    def _describe(err: StepError) -> str:
        """One-line rendering of an error, including which phase it came from."""
        where = f"{err.phase}/{err.filename}" if err.filename else err.phase
        return f"[{where}] {err.message}"

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
            conflicts_found, relink_entry = self._check_conflicts(stub)

            # Hash matches an entry whose file is gone: this *is* that file,
            # so put it back under the entry's name instead of holding it.
            if relink_entry is not None:
                self._relink(file_path, relink_entry)
                return True

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
                self._record_error(
                    "conflict", file_path.name, conflicts_found[0]["message"]
                )
                return False  # Skip this file

            new_filename = stub["filename"]

            # Check for excessively long filename
            if len(new_filename) > 150:
                self.log_entries.append(
                    f"Long filename ({len(new_filename)} chars): {file_path.name} -> {new_filename}"
                )

            # Build the entry up front and journal it *before* the move: if
            # the run dies after the move but before references.json is
            # saved, the history still holds everything needed to rebuild
            # this entry (original name, new name, hash, metadata).
            entry = build_reference_entry(
                stub["author_names"],
                stub["year"],
                stub["title"],
                stub["publisher"],
                new_filename,
                original_filename=file_path.name,
                file_hash=stub["file_hash"],
            )
            append_history("ingest", **entry)

            # Move file from todo/ to reference/ (changed from copy).
            # BaseException so a Ctrl-C landing on the move is journalled too.
            dest_path = config.REFERENCE_DIR / new_filename
            try:
                shutil.move(str(file_path), str(dest_path))
            except BaseException as e:
                append_history(
                    "ingest_failed",
                    original_filename=file_path.name,
                    filename=new_filename,
                    file_hash=stub["file_hash"],
                    error=str(e) or type(e).__name__,
                )
                raise

            # Append to the in-memory references list so later files in
            # this batch see it immediately via self.existing_references,
            # closing the within-batch duplicate window.
            self.existing_references.append(entry)

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

        except Exception as e:
            self._record_error("ingest", file_path.name, str(e), fatal=True)
            return False

        # Save after every file, not once at the end: an interrupted batch
        # must not leave moved files with no references.json entry. The file
        # *is* ingested either way (moved, journalled, in memory for the
        # final save), so a failure here is recorded but still returns True.
        self._save_references(file_path.name)
        return True

    def _check_conflicts(self, stub: dict) -> tuple[list[dict], Optional[dict]]:
        """Check an incoming file against existing references.

        Returns (conflicts, relink_entry). A hash match is classified by
        the state of the existing entry's file:
        - present with the same hash -> `hash_duplicate` (a true duplicate);
        - missing from reference/ -> relink: the incoming file restores it
          (returned as relink_entry, no conflict);
        - name occupied by different content -> `hash_matches_missing_file`
          (held: restoring it would overwrite that other file).
        """
        conflicts = []

        hash_match = check_hash_conflict(stub["file_hash"], self.existing_references)
        if hash_match:
            existing_path = config.REFERENCE_DIR / hash_match["filename"]
            if not existing_path.exists():
                return [], hash_match
            present = calculate_file_hash(existing_path) == stub["file_hash"]
            if present:
                message = f"File hash matches existing entry: {hash_match['filename']}"
            else:
                message = (
                    f"File hash matches entry {hash_match['filename']}, whose file "
                    "is missing and whose name is taken by different content"
                )
            conflicts.append(
                {
                    "type": (
                        "hash_duplicate" if present else "hash_matches_missing_file"
                    ),
                    "existing_filename": hash_match["filename"],
                    "existing_title": hash_match.get("title", ""),
                    "existing_file_present": present,
                    "message": message,
                }
            )

        # No filename-collision check: create_reference_stub already
        # suffixes the name against every existing entry and this batch, so
        # a colliding name can't reach here.

        return conflicts, None

    def _relink(self, file_path: Path, entry: dict) -> None:
        """Move `file_path` to the missing file of `entry`, keeping the
        entry's metadata. Journalled before the move, like an ingest."""
        append_history("relink", **entry, incoming_filename=file_path.name)
        dest_path = config.REFERENCE_DIR / entry["filename"]
        try:
            shutil.move(str(file_path), str(dest_path))
        except BaseException as e:
            append_history(
                "ingest_failed",
                original_filename=file_path.name,
                filename=entry["filename"],
                file_hash=entry["file_hash"],
                error=str(e) or type(e).__name__,
            )
            raise
        self.relinked.append(
            {"original_filename": file_path.name, "new_filename": entry["filename"]}
        )
        # The entry itself is unchanged, but save as after an ingest so the
        # run's .bak/atomic-write guarantees cover it too.
        self._save_references(file_path.name)

    def _save_references(self, filename: str = "") -> bool:
        """Save references.json, recording a failure as fatal rather than
        raising (so it can't mask an interrupt already propagating)."""
        try:
            save_references_json(self.existing_references, backup=not self._backed_up)
            self._backed_up = True
            return True
        except Exception as e:
            self._record_error(
                "output", filename, f"Failed to save references.json: {e}", fatal=True
            )
            return False

    def run(self) -> dict:
        """Main processing loop. Returns a summary dict with counts."""
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
                self._record_error(
                    "skip", pdf.name, f"Large PDF ({size / 1024 / 1024:.1f}MB, ≥50MB)"
                )
            else:
                small_pdfs.append(pdf)

        print(
            f"Processing {len(small_pdfs)} PDFs (<50MB), skipping {len(large_pdfs)} large PDFs"
        )

        # Record non-PDF files
        for f in non_pdf_files:
            self.skipped_non_pdf.append(f.name)
            self._record_error("skip", f.name, "Not a PDF")

        # Process small PDFs. Each file saves references.json as it goes;
        # the finally makes sure an interrupted batch (Ctrl-C is a
        # BaseException, so no `except Exception` sees it) still gets its
        # final save and its log before the interrupt propagates.
        completed = False
        try:
            for i, pdf_file in enumerate(small_pdfs, 1):
                print(f"Processing {i}/{len(small_pdfs)}: {pdf_file.name}")
                self.process_file(pdf_file)

                # Progress indicator
                if i % 50 == 0:
                    print(f"  ... {i} files processed")
            completed = True
        finally:
            self._finish(completed)

        return {
            "processed": len(self.processed_files),
            "relinked": len(self.relinked),
            "conflicts": len(self.conflicts),
            "skipped": len(self.skipped_errors),
            "fatal_errors": len(self.fatal_errors),
        }

    def _finish(self, completed: bool) -> None:
        """Save, regenerate, and log -- on success and on interruption alike."""
        if not completed:
            print("\n⚠ Interrupted -- saving progress before exiting...")
            self.log_entries.append(
                "Run interrupted: files still in todo/ were not processed"
            )

        # Final save, then generate references.md from it
        if self.processed_files:
            print("Saving references.json...")
            self._save_references()
            print("Generating references.md from JSON...")
            try:
                regenerated = regenerate_references_md()
            except Exception as e:
                # Recorded, not raised: it must not mask a propagating interrupt
                print(f"  [!] Error: {e}")
                regenerated = False
            if regenerated:
                print("  ✓ References.md generated successfully")
            else:
                print("  ⚠ Warning: generate_references_md.py failed")
                # references.json now lists files references.md doesn't, and
                # `verify` never reads references.md -- nothing downstream
                # would catch this.
                self._record_error(
                    "output", "", "Failed to regenerate references.md", fatal=True
                )

        # Written in the finally too, so a failure here is recorded rather
        # than raised -- raising would replace a propagating interrupt.
        written = set()
        for write, name in (
            (self._write_conflict_report, "ingestion_conflicts.json"),
            (lambda: self._write_log(completed), "log.md"),
        ):
            try:
                write()
                written.add(name)
            except Exception as err:
                print(f"  [!] Error writing {name}: {err}")
                self._record_error(
                    "output", "", f"Failed to write {name}: {err}", fatal=True
                )

        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Processed: {len(self.processed_files)} files")
        if self.relinked:
            print(f"Relinked: {len(self.relinked)} missing files restored")
        print(f"Conflicts: {len(self.conflicts)} files (kept in todo/)")
        print(f"Failures: {len(self.fatal_errors)}")
        print(f"Skipped: {len(self.skipped_errors)}")

        if self.fatal_errors:
            print("\nFailures:")
            for err in self.fatal_errors:
                print(f"  - {self._describe(err)}")

        if self.skipped_errors:
            print("\nSkipped (left in todo/):")
            for err in self.skipped_errors:
                print(f"  - {self._describe(err)}")

        if "log.md" in written:
            print(f"\n✓ Log saved to: {config.MARKDOWN_DIR / 'log.md'}")
        # Last line on screen, deliberately: the detail above scrolls off, and
        # a partially-applied run must not end on an unqualified success.
        if not completed:
            print("✗ Interrupted -- progress so far is saved; rerun to continue.")
        elif self.fatal_errors:
            print(
                f"✗ {len(self.fatal_errors)} genuine failure(s) "
                "-- this run did not fully apply."
            )
        else:
            print("✓ Completed with no failures.")
        print("=" * 70)

    def _write_log(self, completed: bool) -> None:
        """Write log.md."""
        print("Writing log...")
        with open(config.MARKDOWN_DIR / "log.md", "w", encoding="utf-8") as f:
            f.write("# Document Processing Log\n\n")
            if not completed:
                f.write(
                    "**Interrupted**: this run stopped early. Files still in "
                    "todo/ were not processed.\n\n"
                )
            f.write("## Summary\n\n")
            f.write(f"- **Total PDFs processed**: {len(self.processed_files)}\n")
            f.write(f"- **Missing files restored (relinked)**: {len(self.relinked)}\n")
            f.write(
                f"- **Conflicts detected (kept in todo/)**: {len(self.conflicts)}\n"
            )
            f.write(f"- **Large PDFs skipped (≥50MB)**: {len(self.skipped_large)}\n")
            f.write(f"- **Non-PDF files skipped**: {len(self.skipped_non_pdf)}\n")
            f.write(f"- **Failures**: {len(self.fatal_errors)}\n")
            f.write(f"- **Skipped**: {len(self.skipped_errors)}\n")
            f.write(f"- **Issues logged**: {len(self.log_entries)}\n\n")

            if self.processed_files:
                f.write("## Ingested Files\n\n")
                for p in self.processed_files:
                    f.write(f"- {p['original_filename']} → {p['new_filename']}\n")
                f.write("\n")

            if self.relinked:
                f.write("## Relinked Files\n\n")
                f.write(
                    "Matched the hash of an entry whose file was missing; "
                    "restored under the entry's name.\n\n"
                )
                for p in self.relinked:
                    f.write(f"- {p['original_filename']} → {p['new_filename']}\n")
                f.write("\n")

            if self.fatal_errors:
                f.write("## Failures\n\n")
                for err in self.fatal_errors:
                    f.write(f"- {self._describe(err)}\n")
                f.write("\n")

            if self.skipped_errors:
                f.write("## Skipped\n\n")
                f.write("Left in todo/ -- conflicts, large and non-PDF files.\n\n")
                for err in self.skipped_errors:
                    f.write(f"- {self._describe(err)}\n")
                f.write("\n")

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

            if self.log_entries:
                f.write("## Issues and Warnings\n\n")
                for entry in self.log_entries:
                    f.write(f"- {entry}\n")
                f.write("\n")

    def _write_conflict_report(self) -> None:
        """Write json-output/ingestion_conflicts.json -- always, so a clean
        run replaces a previous run's report instead of leaving it stale."""
        conflict_report = {
            "generated": datetime.now().isoformat(),
            "conflicts": self.conflicts,
        }
        conflict_file = config.JSON_OUTPUT_DIR / "ingestion_conflicts.json"
        _atomic_write_text(
            conflict_file, json.dumps(conflict_report, indent=2, ensure_ascii=False)
        )
        if self.conflicts:
            print(f"  Conflict report written to: {conflict_file}")
            if any(
                c["type"] == "hash_duplicate"
                for item in self.conflicts
                for c in item["conflicts"]
            ):
                print(
                    "  Held duplicates: 'make quarantine-held' previews moving "
                    "them to quarantine/ (APPLY=1 to move)"
                )


def main():
    """Main entry point."""
    return DocumentProcessor.run_as_main()


if __name__ == "__main__":
    exit(main())
