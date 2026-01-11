#!/usr/bin/env python3
"""
Update broken title entries using curated metadata from broken_titles.json
- Replace title if suggested_title is not null
- Replace author if suggested_author is not null
- Rename files and update references.md
- Handle quarantine entries (rename first, then move to quarantine folder)
"""

import json
from pathlib import Path

from src.lib.utils import (
    REFERENCE_DIR,
    QUARANTINE_DIR,
    MARKDOWN_DIR,
    JSON_OUTPUT_DIR,
    parse_author,
    sanitize_title,
    get_entry_from_references_json,
    remove_entry_from_references_json,
    update_entry_in_references_json,
    check_duplicate_filename,
    rename_file,
    regenerate_references_md,
)

INPUT_JSON = JSON_OUTPUT_DIR / "broken_titles.json"


def process_entry(entry, processed_files):
    """Process a single entry: determine new filename based on suggested metadata."""
    old_filename = entry["filename"]
    current_author = entry.get("author", "Unknown")
    current_title = entry.get("title", "Untitled")

    # Extract year/publisher from references.json
    ref_entry = get_entry_from_references_json(old_filename)
    current_year = ref_entry.get("year") if ref_entry else None
    current_publisher = ref_entry.get("publisher") if ref_entry else None

    # Field-by-field merge
    final_author = entry.get("suggested_author") or current_author
    final_title = entry.get("suggested_title") or current_title

    author_changed = entry.get("suggested_author") is not None
    title_changed = entry.get("suggested_title") is not None

    # Generate new filename
    author_filename, author_names = parse_author(final_author)
    title_filename = sanitize_title(final_title)
    new_filename = f"{author_filename}_{title_filename}.pdf"

    if len(new_filename) > 150:
        title_filename = "_".join(title_filename.split("_")[:10])
        new_filename = f"{author_filename}_{title_filename}.pdf"

    is_quarantine = entry.get("quarantine") == True
    target_dir = QUARANTINE_DIR if is_quarantine else REFERENCE_DIR

    new_filename = check_duplicate_filename(new_filename, processed_files, target_dir)
    processed_files.add(new_filename)

    return {
        "old_filename": old_filename,
        "new_filename": new_filename,
        "author": final_author,
        "author_names": author_names,
        "title": final_title,
        "year": current_year,
        "publisher": current_publisher,
        "author_changed": author_changed,
        "title_changed": title_changed,
    }


def main():
    print("Updating broken title entries from curated metadata")
    print("=" * 60)

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries\n")

    quarantined = []
    entries_updated = []
    entries_skipped = []
    errors = []
    processed_files = set()

    quarantine_entries = [e for e in entries if e.get("quarantine") == True]
    regular_entries = [e for e in entries if not e.get("quarantine")]

    # Step 1: Process quarantine entries
    print("Step 1: Processing quarantine entries...")
    for entry in quarantine_entries:
        old_filename = entry["filename"]
        print(f"  Processing: {old_filename}")

        result = process_entry(entry, processed_files)
        new_filename = result["new_filename"]
        old_path = REFERENCE_DIR / old_filename

        if not old_path.exists():
            print(f"    [!] File not found")
            errors.append(f"File not found: {old_filename}")
            continue

        new_path = QUARANTINE_DIR / new_filename
        rename_file(old_path, new_path)
        print(f"    -> Renamed and moved to quarantine: {new_filename}")

        if remove_entry_from_references_json(old_filename):
            print(f"    -> Removed from references.json")
        else:
            print(f"    [!] Entry not found in references.json")

        quarantined.append(
            {
                "old_filename": old_filename,
                "new_filename": new_filename,
                "author": result["author"],
                "title": result["title"],
            }
        )

    print(f"\n[OK] Quarantined {len(quarantined)} files\n")

    # Step 2: Update regular entries
    print("Step 2: Updating entries with improved metadata...")
    for i, entry in enumerate(regular_entries, 1):
        old_filename = entry["filename"]
        print(f"[{i}/{len(regular_entries)}] Processing: {old_filename}")

        if not entry.get("suggested_author") and not entry.get("suggested_title"):
            print(f"  -> No suggestions, skipping")
            entries_skipped.append(old_filename)
            continue

        result = process_entry(entry, processed_files)
        new_filename = result["new_filename"]
        old_path = REFERENCE_DIR / old_filename
        new_path = REFERENCE_DIR / new_filename

        if not old_path.exists():
            print(f"  [!] File not found: {old_filename}")
            errors.append(f"File not found: {old_filename}")
            continue

        if old_filename != new_filename:
            rename_file(old_path, new_path)
            print(f"  -> Renamed to: {new_filename}")
        else:
            print(f"  -> Filename unchanged")

        if update_entry_in_references_json(
            old_filename,
            new_filename,
            result["author_names"],
            result["year"],
            result["title"],
            result["publisher"],
        ):
            print(f"  -> Updated references.json")
        else:
            print(f"  [!] Entry not found in references.json")
            errors.append(f"Entry not found: {old_filename}")

        entries_updated.append(
            {
                "old_filename": old_filename,
                "new_filename": new_filename,
                "author": result["author"],
                "title": result["title"],
                "year": result["year"],
                "author_changed": result["author_changed"],
                "title_changed": result["title_changed"],
            }
        )

    # Generate references.md from references.json
    if quarantined or entries_updated:
        print(f"\n{'=' * 60}")
        print("Generating references.md from JSON...")
        if regenerate_references_md():
            print("✓ References.md generated successfully")
        else:
            print("⚠ Warning: generate_references_md.py failed")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"Quarantined: {len(quarantined)}")
    print(f"Entries updated: {len(entries_updated)}")
    print(f"Entries skipped: {len(entries_skipped)}")
    print(f"Errors: {len(errors)}")

    # Save log
    log_file = MARKDOWN_DIR / "broken_titles_update_log.md"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("# Broken Titles Update Log\n\n")
        f.write(f"- **Quarantined**: {len(quarantined)}\n")
        f.write(f"- **Updated**: {len(entries_updated)}\n")
        f.write(f"- **Skipped**: {len(entries_skipped)}\n")
        f.write(f"- **Errors**: {len(errors)}\n\n")

        if quarantined:
            f.write("## Quarantined\n\n")
            for q in quarantined:
                f.write(f"- {q['old_filename']} -> {q['new_filename']}\n")
            f.write("\n")

        if entries_updated:
            f.write("## Updated\n\n")
            for e in entries_updated:
                f.write(f"- {e['old_filename']} -> {e['new_filename']}\n")
            f.write("\n")

        if errors:
            f.write("## Errors\n\n")
            for err in errors:
                f.write(f"- {err}\n")

    print(f"\n[OK] Log saved to: {log_file}")


if __name__ == "__main__":
    main()
