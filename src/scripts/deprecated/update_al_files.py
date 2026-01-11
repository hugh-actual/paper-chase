#!/usr/bin/env python3
"""
Update files starting with 'al_' using fixes from al_files_to_fix.json.
Renames files and updates references.json.
"""

import json
from pathlib import Path

from src.lib.utils import (
    REFERENCE_DIR,
    MARKDOWN_DIR,
    JSON_OUTPUT_DIR,
    update_entry_in_references_json,
    rename_file,
    regenerate_references_md,
)

INPUT_JSON = JSON_OUTPUT_DIR / "al_files_to_fix.json"


def main():
    print("Updating 'al_*' files from JSON...")
    print("=" * 70)

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries\n")

    files_updated = []
    errors = []

    for i, entry in enumerate(entries, 1):
        old_filename = entry["old_filename"]
        new_filename = entry["new_filename"]
        author = entry["author"]
        title = entry["title"]
        year = entry.get("year")
        publisher = entry.get("publisher")

        print(f"[{i}/{len(entries)}] Processing: {old_filename}")

        # Skip if old and new are the same
        if old_filename == new_filename:
            print(f"  -> Filename unchanged, skipping")
            continue

        old_path = REFERENCE_DIR / old_filename
        new_path = REFERENCE_DIR / new_filename

        if not old_path.exists():
            print(f"  [!] File not found: {old_filename}")
            errors.append(f"File not found: {old_filename}")
            continue

        # Rename the file
        rename_file(old_path, new_path)
        print(f"  -> Renamed to: {new_filename}")

        # Update references.json
        # Parse author to get list format
        if author == "Unknown":
            author_names = ["Unknown"]
        elif " et al" in author:
            # Extract first author for the list
            first_author = (
                author.replace(" et al", "")
                .replace(" Et Al", "")
                .replace(" ET AL", "")
                .strip()
            )
            author_names = [author]  # Keep original format
        else:
            author_names = [author]

        if update_entry_in_references_json(
            old_filename, new_filename, author_names, year, title, publisher
        ):
            print(f"  -> Updated references.json")
        else:
            print(f"  [!] Entry not found in references.json")
            errors.append(f"Entry not found in JSON: {old_filename}")

        files_updated.append(
            {
                "old_filename": old_filename,
                "new_filename": new_filename,
                "author": author,
                "title": title,
            }
        )

    # Generate references.md from references.json
    if files_updated:
        print(f"\n{'=' * 70}")
        print("Generating references.md from JSON...")
        if regenerate_references_md():
            print("✓ References.md generated successfully")
        else:
            print("⚠ Warning: generate_references_md.py failed")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Files updated: {len(files_updated)}")
    print(f"Errors: {len(errors)}")

    if errors:
        print(f"\nErrors:")
        for err in errors:
            print(f"  - {err}")

    # Save log
    log_file = MARKDOWN_DIR / "al_files_update_log.md"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("# 'al_*' Files Update Log\n\n")
        f.write(f"- **Files updated**: {len(files_updated)}\n")
        f.write(f"- **Errors**: {len(errors)}\n\n")

        if files_updated:
            f.write("## Files Updated\n\n")
            for entry in files_updated:
                f.write(f"- {entry['old_filename']} → {entry['new_filename']}\n")
            f.write("\n")

        if errors:
            f.write("## Errors\n\n")
            for err in errors:
                f.write(f"- {err}\n")

    print(f"\n[OK] Log saved to: {log_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
