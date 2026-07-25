#!/usr/bin/env python3
"""
Base classes for pipeline steps.

This module provides abstract base classes for update operations,
extracting the common quarantine/update/regenerate/log pattern
that is shared across all update scripts.
"""

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.lib import config
from src.lib.utils import (
    generate_new_filename,
    rename_file,
    load_references_json,
    save_references_json,
    regenerate_references_md,
)


@dataclass(frozen=True)
class StepError:
    """One thing that went wrong during a step.

    `fatal` is the distinction that matters: a fatal error is a genuine
    failure (an exception, a rename that raised, references.md failing to
    regenerate) and makes the script exit nonzero. Everything else is a
    "file not found" / "not in references.json" skip, which is routine
    when rerunning over stale annotations -- those stay non-fatal so
    `make update-all` keeps chaining through harmless reruns.
    """

    phase: str  # "quarantine" | "update" | "output"
    filename: str  # "" for run-level failures with no single file
    message: str
    fatal: bool


class UpdateStep(ABC):
    """
    Base class for update scripts that process annotated JSON files.

    All update scripts follow the same pattern:
    1. Load entries from JSON (with quarantine and suggested_* fields)
    2. Phase 1: Process quarantine entries
       (move to quarantine/, remove from references.json)
    3. Phase 2: Process regular entries
       (merge suggested_* with current, rename, update references.json)
    4. Phase 3: Regenerate references.md
    5. Phase 4: Write summary log

    Subclasses only need to implement:
    - Class attributes: name, input_filename, log_filename, log_title
    - load_entries(): Load and flatten entries from the specific JSON format
    """

    # Class attributes that subclasses must override
    name: str = ""  # Step name for logging
    input_filename: str = ""  # JSON file to read
    log_filename: str = ""  # Log file to write
    log_title: str = ""  # Title for the markdown log

    def __init__(self):
        self.input_file = config.JSON_OUTPUT_DIR / self.input_filename
        self.log_file = config.MARKDOWN_DIR / self.log_filename

        # Result tracking
        self.quarantined = 0
        self.updated = 0
        self.processed_files = set()

        # Single record of everything that went wrong. The per-phase and
        # fatal views below are derived from it, so they cannot drift.
        self.errors: list[StepError] = []

        # Loaded once in run(), mutated in memory, saved once at the end
        self.references = []

    def _record_error(
        self, phase: str, filename: str, message: str, fatal: bool = False
    ) -> None:
        """Record a failure or a skip. See StepError for the distinction."""
        self.errors.append(StepError(phase, filename, message, fatal))

    def _errors_in(self, phase: str) -> list[StepError]:
        return [e for e in self.errors if e.phase == phase]

    @property
    def quarantine_errors(self) -> list[StepError]:
        return self._errors_in("quarantine")

    @property
    def update_errors(self) -> list[StepError]:
        return self._errors_in("update")

    @property
    def fatal_errors(self) -> list[StepError]:
        return [e for e in self.errors if e.fatal]

    @property
    def skipped_errors(self) -> list[StepError]:
        return [e for e in self.errors if not e.fatal]

    @property
    def quarantine_error_files(self) -> set:
        return {e.filename for e in self.quarantine_errors}

    @property
    def update_error_files(self) -> set:
        return {e.filename for e in self.update_errors}

    @classmethod
    def run_as_main(cls) -> int:
        """Entry point for `python -m`: nonzero only on genuine failures.

        Routine skips still exit 0, so `make update-all` keeps chaining
        through reruns over stale annotations.
        """
        return 1 if cls().run()["fatal_errors"] else 0

    @abstractmethod
    def load_entries(self) -> list[dict]:
        """
        Load and flatten entries from the input JSON file.

        Must return a list of dicts with this structure:
        {
            "filename": str,
            "author": str,
            "title": str,
            "year": str (optional),
            "publisher": str (optional),
            "quarantine": bool or None,
            "suggested_author": str or None,
            "suggested_title": str or None,
            "suggested_year": str or None,
        }
        """
        pass

    def run(self) -> dict:
        """
        Execute the full update workflow.
        Returns a summary dict with counts.
        """
        print(f"Processing {self.name} from {self.input_filename}...")
        print("=" * 70)

        # Load entries and the reference metadata (saved once after both phases)
        all_entries = self.load_entries()
        self.references = load_references_json()
        print(f"Total entries to process: {len(all_entries)}\n")

        # Phase 1: Quarantine
        quarantine_entries = [e for e in all_entries if e.get("quarantine") is True]
        if quarantine_entries:
            print("PHASE 1: Processing quarantine entries...")
            print("-" * 70)
            print(f"Files to quarantine: {len(quarantine_entries)}\n")
            self._process_quarantine(quarantine_entries)
            print(f"\nPhase 1 Complete: {self.quarantined} files quarantined\n")

        # Phase 2: Updates
        update_entries = [
            e
            for e in all_entries
            if e.get("quarantine") is not True
            and (
                e.get("suggested_author") is not None
                or e.get("suggested_title") is not None
                or e.get("suggested_year") is not None
            )
        ]
        if update_entries:
            print("PHASE 2: Processing metadata updates...")
            print("-" * 70)
            print(f"Files to update: {len(update_entries)}\n")
            self._process_updates(update_entries)
            print(f"\nPhase 2 Complete: {self.updated} files updated\n")

        # Phase 3: Save references.json and regenerate references.md
        if self.quarantined > 0 or self.updated > 0:
            save_references_json(self.references)
            print("Generating references.md...")
            if regenerate_references_md():
                print("  ✓ references.md generated\n")
            else:
                print("  ⚠ Warning: generate_references_md.py failed\n")
                # references.json now describes changes references.md doesn't
                # reflect, and `verify` compares the filesystem against the
                # JSON only -- so nothing downstream would catch this.
                self._record_error(
                    "output", "", "Failed to regenerate references.md", fatal=True
                )

        # Phase 4: Summary and log
        self._print_summary(len(all_entries))
        self._write_log(all_entries, quarantine_entries, update_entries)

        return {
            "total": len(all_entries),
            "quarantined": self.quarantined,
            "updated": self.updated,
            "quarantine_errors": len(self.quarantine_errors),
            "update_errors": len(self.update_errors),
            "fatal_errors": len(self.fatal_errors),
        }

    def _process_quarantine(self, entries: list[dict]) -> None:
        """Process quarantine entries: move files and remove from references.json."""
        for entry in entries:
            filename = entry["filename"]
            print(f"  Quarantining: {filename}")

            old_path = config.REFERENCE_DIR / filename
            new_path = config.QUARANTINE_DIR / filename

            if not old_path.exists():
                print(f"    [!] File not found: {filename}")
                self._record_error("quarantine", filename, "File not found")
                continue

            try:
                shutil.move(str(old_path), str(new_path))

                # Remove from the in-memory references
                remaining = [e for e in self.references if e["filename"] != filename]

                if len(remaining) < len(self.references):
                    self.references = remaining
                    self.quarantined += 1
                    print("    ✓ Moved to quarantine/")
                else:
                    print("    [!] Warning: Entry not found in references.json")
                    self._record_error(
                        "quarantine", filename, "Entry not in references.json"
                    )

            except Exception as e:
                print(f"    [!] Error: {e}")
                self._record_error("quarantine", filename, str(e), fatal=True)

    def _process_updates(self, entries: list[dict]) -> None:
        """
        Process metadata updates.

        Merge suggested_* fields, rename files, update references.json.
        """
        for entry in entries:
            filename = entry["filename"]

            # Look up current metadata in the in-memory references
            current_entry = None
            for ref_entry in self.references:
                if ref_entry["filename"] == filename:
                    current_entry = ref_entry
                    break

            if not current_entry:
                print(f"  [!] File not found in references.json: {filename}")
                self._record_error("update", filename, "Not in references.json")
                continue

            current_author = current_entry.get("author", "")
            current_title = current_entry.get("title", "")
            current_year = current_entry.get("year", "")
            current_publisher = current_entry.get("publisher", "")

            # Merge suggested fields with current (only override if suggested field is not null)
            final_author = (
                entry.get("suggested_author")
                if entry.get("suggested_author") is not None
                else current_author
            )
            final_title = (
                entry.get("suggested_title")
                if entry.get("suggested_title") is not None
                else current_title
            )
            final_year = (
                entry.get("suggested_year")
                if entry.get("suggested_year") is not None
                else current_year
            )

            # Track what changed
            author_changed = entry.get("suggested_author") is not None
            title_changed = entry.get("suggested_title") is not None
            year_changed = entry.get("suggested_year") is not None

            changes = []
            if author_changed:
                changes.append(f"author: '{current_author}' → '{final_author}'")
            if title_changed:
                changes.append(f"title: '{current_title}' → '{final_title}'")
            if year_changed:
                changes.append(f"year: '{current_year}' → '{final_year}'")

            if not changes:
                continue

            print(f"  Updating: {filename}")
            for change in changes:
                print(f"    {change}")

            # Check if file exists
            old_path = config.REFERENCE_DIR / filename
            if not old_path.exists():
                print(f"    [!] File not found: {filename}")
                self._record_error("update", filename, "File not found")
                continue

            # Generate new filename
            new_filename, author_names = generate_new_filename(
                final_author, final_title, self.processed_files, config.REFERENCE_DIR
            )

            # Rename file first so the metadata never points at a missing file
            if filename != new_filename:
                new_path = config.REFERENCE_DIR / new_filename
                try:
                    rename_file(old_path, new_path)
                    print(f"    ✓ Renamed to: {new_filename}")
                except Exception as e:
                    print(f"    [!] Error renaming file: {e}")
                    self._record_error(
                        "update", filename, f"Error renaming: {e}", fatal=True
                    )
                    continue
            else:
                print("    ✓ Metadata updated (filename unchanged)")

            # Update the in-memory entry
            final_year_clean = final_year if final_year not in ["n.d.", ""] else None
            current_entry.update(
                {
                    "author": ", ".join(author_names),
                    "year": final_year_clean or "",
                    "title": final_title,
                    "publisher": current_publisher or "",
                    "filename": new_filename,
                }
            )

            self.processed_files.add(new_filename)
            self.updated += 1

    @staticmethod
    def _describe(err: StepError) -> str:
        """One-line rendering of an error, including which phase it came from."""
        where = f"{err.phase}/{err.filename}" if err.filename else err.phase
        return f"[{where}] {err.message}"

    def _print_summary(self, total: int) -> None:
        """Print summary to stdout."""
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Total files processed: {total}")
        print(f"Files quarantined: {self.quarantined}")
        print(f"Files updated: {self.updated}")
        print(f"Failures: {len(self.fatal_errors)}")
        print(f"Skipped (already applied): {len(self.skipped_errors)}")

        if self.fatal_errors:
            print("\nFailures:")
            for err in self.fatal_errors:
                print(f"  - {self._describe(err)}")

        if self.skipped_errors:
            print("\nSkipped (nothing to do -- already applied, or not present):")
            for err in self.skipped_errors:
                print(f"  - {self._describe(err)}")

    def _write_log(
        self,
        all_entries: list[dict],
        quarantine_entries: list[dict],
        update_entries: list[dict],
    ) -> None:
        """Write markdown log file."""
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"# {self.log_title}\n\n")
            f.write("## Summary\n\n")
            f.write(f"- **Total files processed**: {len(all_entries)}\n")
            f.write(f"- **Files quarantined**: {self.quarantined}\n")
            f.write(f"- **Files updated**: {self.updated}\n")
            f.write(f"- **Failures**: {len(self.fatal_errors)}\n")
            f.write(f"- **Skipped**: {len(self.skipped_errors)}\n\n")

            if self.quarantined > 0:
                f.write("## Quarantined Files\n\n")
                for entry in quarantine_entries:
                    if entry["filename"] not in self.quarantine_error_files:
                        f.write(f"- {entry['filename']}\n")
                f.write("\n")

            if self.updated > 0:
                f.write("## Updated Files\n\n")
                for entry in update_entries:
                    if entry["filename"] not in self.update_error_files:
                        changes = []
                        if entry.get("suggested_author"):
                            changes.append(f"author → {entry['suggested_author']}")
                        if entry.get("suggested_title"):
                            changes.append(f"title → {entry['suggested_title']}")
                        if entry.get("suggested_year"):
                            changes.append(f"year → {entry['suggested_year']}")
                        if changes:
                            entry_name = entry["filename"]
                            change_list = ", ".join(changes)
                            f.write(f"- **{entry_name}**: {change_list}\n")
                f.write("\n")

            if self.fatal_errors:
                f.write("## Failures\n\n")
                for err in self.fatal_errors:
                    f.write(f"- {self._describe(err)}\n")
                f.write("\n")

            if self.skipped_errors:
                f.write("## Skipped\n\n")
                f.write("Nothing to do -- already applied, or not present.\n\n")
                for err in self.skipped_errors:
                    f.write(f"- {self._describe(err)}\n")
                f.write("\n")

        print(f"\n✓ Log saved to: {self.log_file}")
        # Last line on screen, deliberately: the detail above scrolls off, and
        # a partially-applied run must not end on an unqualified success.
        if self.fatal_errors:
            print(
                f"✗ {len(self.fatal_errors)} genuine failure(s) "
                "-- this run did not fully apply."
            )
        else:
            print("✓ Completed with no failures.")
        print("=" * 70)
