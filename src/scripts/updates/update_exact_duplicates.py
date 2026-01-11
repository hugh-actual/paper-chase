#!/usr/bin/env python3
"""
Update exact duplicate entries from duplicate_candidates.json.
Processes files with quarantine flags or suggested metadata updates.
"""

import json
import shutil
from pathlib import Path

from src.lib.utils import (
    REFERENCE_DIR,
    QUARANTINE_DIR,
    MARKDOWN_DIR,
    JSON_OUTPUT_DIR,
    generate_new_filename,
    rename_file,
    load_references_json,
    save_references_json,
    remove_entry_from_references_json,
    update_entry_in_references_json,
    regenerate_references_md,
)


def main():
    print("Processing exact duplicates from duplicate_candidates.json...")
    print("=" * 70)

    # Load duplicate candidates
    candidates_file = JSON_OUTPUT_DIR / "duplicate_candidates.json"
    with open(candidates_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    exact_duplicates = data.get("exact_duplicates", [])
    print(f"Found {len(exact_duplicates)} duplicate groups\n")

    # Flatten all files from all groups
    all_files = []
    for group in exact_duplicates:
        for file_entry in group.get("files", []):
            all_files.append(file_entry)

    print(f"Total files to process: {len(all_files)}\n")

    # Phase 1: Process quarantine entries
    print("PHASE 1: Processing quarantine entries...")
    print("-" * 70)

    quarantine_entries = [f for f in all_files if f.get("quarantine") == True]
    print(f"Files to quarantine: {len(quarantine_entries)}\n")

    quarantined = 0
    quarantine_errors = []

    for entry in quarantine_entries:
        filename = entry["filename"]
        print(f"  Quarantining: {filename}")

        # Move file
        old_path = REFERENCE_DIR / filename
        new_path = QUARANTINE_DIR / filename

        if not old_path.exists():
            print(f"    [!] File not found: {filename}")
            quarantine_errors.append(f"File not found: {filename}")
            continue

        try:
            shutil.move(str(old_path), str(new_path))

            # Remove from references.json
            removed = remove_entry_from_references_json(filename)

            if removed:
                quarantined += 1
                print(f"    ✓ Moved to quarantine/")
            else:
                print(f"    [!] Warning: Entry not found in references.json")
                quarantine_errors.append(f"Entry not in references.json: {filename}")

        except Exception as e:
            print(f"    [!] Error: {e}")
            quarantine_errors.append(f"{filename}: {e}")

    print(f"\nPhase 1 Complete: {quarantined} files quarantined\n")

    # Phase 2: Process metadata updates
    print("PHASE 2: Processing metadata updates...")
    print("-" * 70)

    # Filter for non-quarantined entries with suggested fields
    update_entries = [
        f
        for f in all_files
        if f.get("quarantine") != True
        and (
            f.get("suggested_author")
            or f.get("suggested_title")
            or f.get("suggested_year")
        )
    ]

    print(f"Files to update: {len(update_entries)}\n")

    updated = 0
    update_errors = []
    processed_files = set()

    for entry in update_entries:
        filename = entry["filename"]
        current_author = entry.get("author", "")
        current_title = entry.get("title", "")
        current_year = entry.get("year", "")

        # Get suggested values (fallback to current if not provided)
        final_author = entry.get("suggested_author") or current_author
        final_title = entry.get("suggested_title") or current_title
        final_year = entry.get("suggested_year") or current_year

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
        old_path = REFERENCE_DIR / filename
        if not old_path.exists():
            print(f"    [!] File not found: {filename}")
            update_errors.append(f"File not found: {filename}")
            continue

        # Generate new filename
        new_filename, author_names = generate_new_filename(
            final_author, final_title, processed_files, REFERENCE_DIR
        )

        # Update references.json
        success = update_entry_in_references_json(
            filename,
            new_filename,
            author_names,
            final_year if final_year not in ["n.d.", ""] else None,
            final_title,
            entry.get("publisher", ""),
        )

        if not success:
            print(f"    [!] Failed to update references.json")
            update_errors.append(f"Failed to update references.json: {filename}")
            continue

        # Rename file if filename changed
        if filename != new_filename:
            new_path = REFERENCE_DIR / new_filename
            try:
                rename_file(old_path, new_path)
                print(f"    ✓ Renamed to: {new_filename}")
            except Exception as e:
                print(f"    [!] Error renaming file: {e}")
                update_errors.append(f"Error renaming {filename}: {e}")
                continue
        else:
            print(f"    ✓ Metadata updated (filename unchanged)")

        processed_files.add(new_filename)
        updated += 1

    print(f"\nPhase 2 Complete: {updated} files updated\n")

    # Generate references.md
    print("Generating references.md...")
    if regenerate_references_md():
        print("  ✓ references.md generated\n")
    else:
        print("  ⚠ Warning: generate_references_md.py failed\n")

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files processed: {len(all_files)}")
    print(f"Files quarantined: {quarantined}")
    print(f"Files updated: {updated}")
    print(f"Quarantine errors: {len(quarantine_errors)}")
    print(f"Update errors: {len(update_errors)}")

    if quarantine_errors:
        print(f"\nQuarantine errors:")
        for err in quarantine_errors:
            print(f"  - {err}")

    if update_errors:
        print(f"\nUpdate errors:")
        for err in update_errors:
            print(f"  - {err}")

    # Write log
    log_file = MARKDOWN_DIR / "exact_duplicates_update_log.md"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("# Exact Duplicates Update Log\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- **Total files processed**: {len(all_files)}\n")
        f.write(f"- **Files quarantined**: {quarantined}\n")
        f.write(f"- **Files updated**: {updated}\n")
        f.write(f"- **Quarantine errors**: {len(quarantine_errors)}\n")
        f.write(f"- **Update errors**: {len(update_errors)}\n\n")

        if quarantined > 0:
            f.write(f"## Quarantined Files\n\n")
            for entry in quarantine_entries:
                if entry["filename"] not in [
                    e.split(":")[0] for e in quarantine_errors
                ]:
                    f.write(f"- {entry['filename']}\n")
            f.write("\n")

        if updated > 0:
            f.write(f"## Updated Files\n\n")
            for entry in update_entries:
                if entry["filename"] not in [e.split(":")[0] for e in update_errors]:
                    changes = []
                    if entry.get("suggested_author"):
                        changes.append(f"author → {entry['suggested_author']}")
                    if entry.get("suggested_title"):
                        changes.append(f"title → {entry['suggested_title']}")
                    if entry.get("suggested_year"):
                        changes.append(f"year → {entry['suggested_year']}")
                    if changes:
                        f.write(f"- **{entry['filename']}**: {', '.join(changes)}\n")
            f.write("\n")

        if quarantine_errors:
            f.write(f"## Quarantine Errors\n\n")
            for err in quarantine_errors:
                f.write(f"- {err}\n")
            f.write("\n")

        if update_errors:
            f.write(f"## Update Errors\n\n")
            for err in update_errors:
                f.write(f"- {err}\n")
            f.write("\n")

    print(f"\n✓ Log saved to: {log_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
