#!/usr/bin/env python3
"""
Update Unknown author entries from manual review JSON.
Updates author, title, year, renames files, handles quarantine.
"""

import json
from pathlib import Path

from src.lib.utils import (
    REFERENCE_DIR,
    QUARANTINE_DIR,
    MARKDOWN_DIR,
    JSON_OUTPUT_DIR,
    get_entry_from_references_json,
    update_entry_in_references_json,
    remove_entry_from_references_json,
    parse_author,
    sanitize_title,
    check_duplicate_filename,
    rename_file,
    regenerate_references_md,
)

INPUT_JSON = JSON_OUTPUT_DIR / "unknown_authors.json"


def main():
    print("Updating Unknown authors from JSON...")
    print("=" * 70)

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries\n")

    # Tracking lists
    quarantined = []
    entries_updated = []
    entries_skipped = []
    errors = []
    processed_files = set()

    # =========================================================================
    # PHASE 1: Process quarantine entries
    # =========================================================================
    quarantine_entries = [e for e in entries if e.get("quarantine") == True]

    if quarantine_entries:
        print(f"{'=' * 70}")
        print(f"PHASE 1: Processing {len(quarantine_entries)} quarantine entries")
        print(f"{'=' * 70}\n")

        for i, entry in enumerate(quarantine_entries, 1):
            old_filename = entry["filename"]
            current_author = entry.get("author", "Unknown")
            current_title = entry.get("title", "Untitled")

            print(f"[{i}/{len(quarantine_entries)}] Processing: {old_filename}")

            # Get current entry from references.json
            current_entry = get_entry_from_references_json(old_filename)
            if not current_entry:
                print(f"  [!] Entry not found in references.json")
                errors.append(f"Entry not found in references.json: {old_filename}")
                continue

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

            # Generate new filename
            author_filename, author_names = parse_author(final_author)
            title_filename = sanitize_title(final_title)
            new_filename = f"{author_filename}_{title_filename}.pdf"

            # Truncate if too long
            if len(new_filename) > 150:
                title_filename = "_".join(title_filename.split("_")[:10])
                new_filename = f"{author_filename}_{title_filename}.pdf"

            # Check for duplicates in quarantine folder
            new_filename = check_duplicate_filename(
                new_filename, processed_files, QUARANTINE_DIR
            )
            processed_files.add(new_filename)

            # Move file to quarantine
            old_path = REFERENCE_DIR / old_filename
            new_path = QUARANTINE_DIR / new_filename

            if not old_path.exists():
                print(f"  [!] File not found: {old_filename}")
                errors.append(f"File not found: {old_filename}")
                continue

            rename_file(old_path, new_path)
            print(f"  -> Moved to quarantine: {new_filename}")

            # Remove from references.json
            if remove_entry_from_references_json(old_filename):
                print(f"  -> Removed from references.json")
            else:
                print(f"  [!] Failed to remove from references.json")
                errors.append(f"Failed to remove from references.json: {old_filename}")

            quarantined.append(
                {
                    "old_filename": old_filename,
                    "new_filename": new_filename,
                    "author": final_author,
                    "title": final_title,
                }
            )

    # =========================================================================
    # PHASE 2: Process regular entries
    # =========================================================================
    regular_entries = [e for e in entries if e.get("quarantine") != True]

    if regular_entries:
        print(f"\n{'=' * 70}")
        print(f"PHASE 2: Processing {len(regular_entries)} regular entries")
        print(f"{'=' * 70}\n")

        for i, entry in enumerate(regular_entries, 1):
            old_filename = entry["filename"]

            print(f"[{i}/{len(regular_entries)}] Processing: {old_filename}")

            # Check if there are any suggestions
            has_suggestions = (
                entry.get("suggested_author") is not None
                or entry.get("suggested_title") is not None
                or entry.get("suggested_year") is not None
            )

            if not has_suggestions:
                print(f"  -> No suggestions, skipping")
                entries_skipped.append(old_filename)
                continue

            # Get current entry from references.json
            current_entry = get_entry_from_references_json(old_filename)
            if not current_entry:
                print(f"  [!] Entry not found in references.json")
                errors.append(f"Entry not found in references.json: {old_filename}")
                continue

            current_author = current_entry.get("author", "Unknown")
            current_title = current_entry.get("title", "Untitled")
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

            # Generate new filename
            author_filename, author_names = parse_author(final_author)
            title_filename = sanitize_title(final_title)
            new_filename = f"{author_filename}_{title_filename}.pdf"

            # Truncate if too long
            if len(new_filename) > 150:
                title_filename = "_".join(title_filename.split("_")[:10])
                new_filename = f"{author_filename}_{title_filename}.pdf"

            # Check for duplicates
            new_filename = check_duplicate_filename(
                new_filename, processed_files, REFERENCE_DIR
            )
            processed_files.add(new_filename)

            # Skip if filename unchanged and only year changed
            if (
                old_filename == new_filename
                and not author_changed
                and not title_changed
            ):
                print(f"  -> Filename unchanged, updating metadata only")
                # Update metadata in references.json
                if update_entry_in_references_json(
                    old_filename,
                    new_filename,
                    author_names,
                    final_year,
                    final_title,
                    current_publisher,
                ):
                    print(f"  -> Updated references.json")
                    entries_updated.append(
                        {
                            "old_filename": old_filename,
                            "new_filename": new_filename,
                            "author": final_author,
                            "title": final_title,
                            "year": final_year,
                            "changes": ["year"] if year_changed else [],
                        }
                    )
                else:
                    print(f"  [!] Failed to update references.json")
                    errors.append(f"Failed to update references.json: {old_filename}")
                continue

            # Verify file exists
            old_path = REFERENCE_DIR / old_filename
            if not old_path.exists():
                print(f"  [!] File not found: {old_filename}")
                errors.append(f"File not found: {old_filename}")
                continue

            # Rename file
            new_path = REFERENCE_DIR / new_filename
            rename_file(old_path, new_path)
            print(f"  -> Renamed to: {new_filename}")

            # Update references.json
            if update_entry_in_references_json(
                old_filename,
                new_filename,
                author_names,
                final_year,
                final_title,
                current_publisher,
            ):
                print(f"  -> Updated references.json")
            else:
                print(f"  [!] Entry not found in references.json")
                errors.append(f"Entry not found in references.json: {old_filename}")

            # Track changes
            changes = []
            if author_changed:
                changes.append("author")
            if title_changed:
                changes.append("title")
            if year_changed:
                changes.append("year")

            entries_updated.append(
                {
                    "old_filename": old_filename,
                    "new_filename": new_filename,
                    "author": final_author,
                    "title": final_title,
                    "year": final_year,
                    "changes": changes,
                }
            )

    # =========================================================================
    # PHASE 3: Regenerate references.md
    # =========================================================================
    if quarantined or entries_updated:
        print(f"\n{'=' * 70}")
        print("Generating references.md from JSON...")
        if regenerate_references_md():
            print("✓ References.md generated successfully")
        else:
            print("⚠ Warning: generate_references_md.py failed")

    # =========================================================================
    # PHASE 4: Summary and Log
    # =========================================================================
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Files updated: {len(entries_updated)}")
    print(f"Files quarantined: {len(quarantined)}")
    print(f"Files skipped: {len(entries_skipped)}")
    print(f"Errors: {len(errors)}")

    if errors:
        print(f"\nErrors:")
        for err in errors:
            print(f"  - {err}")

    # Save log
    log_file = MARKDOWN_DIR / "unknown_authors_update_log.md"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("# Unknown Authors Update Log\n\n")
        f.write(f"- **Files updated**: {len(entries_updated)}\n")
        f.write(f"- **Files quarantined**: {len(quarantined)}\n")
        f.write(f"- **Files skipped**: {len(entries_skipped)}\n")
        f.write(f"- **Errors**: {len(errors)}\n\n")

        if quarantined:
            f.write("## Files Quarantined\n\n")
            for entry in quarantined:
                f.write(
                    f"- {entry['old_filename']} → quarantine/{entry['new_filename']}\n"
                )
                f.write(f"  - Author: {entry['author']}\n")
                f.write(f"  - Title: {entry['title']}\n")
            f.write("\n")

        if entries_updated:
            f.write("## Files Updated\n\n")
            for entry in entries_updated:
                f.write(f"- {entry['old_filename']} → {entry['new_filename']}\n")
                f.write(f"  - Author: {entry['author']}\n")
                f.write(f"  - Title: {entry['title']}\n")
                if entry.get("year"):
                    f.write(f"  - Year: {entry['year']}\n")
                if entry.get("changes"):
                    f.write(f"  - Changed: {', '.join(entry['changes'])}\n")
            f.write("\n")

        if entries_skipped:
            f.write("## Files Skipped (No Suggestions)\n\n")
            for filename in entries_skipped:
                f.write(f"- {filename}\n")
            f.write("\n")

        if errors:
            f.write("## Errors\n\n")
            for err in errors:
                f.write(f"- {err}\n")

    print(f"\n[OK] Log saved to: {log_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
