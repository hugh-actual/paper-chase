#!/usr/bin/env python3
"""
Fix filenames that don't match the expected pattern based on author names.

These mismatches were created by the old buggy parse_author function.
This script will:
1. Identify all mismatched filenames
2. Generate correct filenames based on current author metadata
3. Rename the actual PDF files in reference/
4. Update references.json with the new filenames
"""

import json
from pathlib import Path
from src.lib.utils import (
    parse_author,
    sanitize_title,
    check_duplicate_filename,
    rename_file,
    update_entry_in_references_json,
    load_references_json,
    save_references_json,
)
from src.lib.config import REFERENCE_DIR, REFERENCES_JSON

print("=" * 80)
print("FIXING MISMATCHED FILENAMES")
print("=" * 80)

# Load references
references = load_references_json()
print(f"\nTotal references: {len(references)}")

# Find mismatches
mismatches = []
for i, ref in enumerate(references):
    author = ref.get("author", "")
    title = ref.get("title", "")
    actual_filename = ref.get("filename", "")

    if not author or not title or author == "Unknown":
        continue

    # Generate expected filename
    author_filename, author_names = parse_author(author)
    expected_prefix = author_filename

    # Check if actual filename starts with expected author part
    if not actual_filename.startswith(expected_prefix):
        # Generate the correct full filename
        title_filename = sanitize_title(title)
        expected_filename = f"{author_filename}_{title_filename}.pdf"

        # Truncate if too long
        if len(expected_filename) > 150:
            title_filename = "_".join(title_filename.split("_")[:10])
            expected_filename = f"{author_filename}_{title_filename}.pdf"

        mismatches.append({
            "index": i,
            "author": author,
            "title": title,
            "old_filename": actual_filename,
            "new_filename": expected_filename,
            "expected_prefix": expected_prefix,
        })

print(f"Found {len(mismatches)} mismatched filenames\n")

if not mismatches:
    print("No mismatches found - all filenames are correct!")
    exit(0)

# Display the mismatches
print("=" * 80)
print("MISMATCHES TO FIX:")
print("=" * 80)
for i, mismatch in enumerate(mismatches, 1):
    print(f"\n{i}. Author: {mismatch['author']}")
    print(f"   Title: {mismatch['title'][:60]}...")
    print(f"   OLD: {mismatch['old_filename']}")
    print(f"   NEW: {mismatch['new_filename']}")

print("\n" + "=" * 80)
response = input(f"\nDo you want to rename these {len(mismatches)} files? (yes/no): ")

if response.lower() not in ["yes", "y"]:
    print("Cancelled - no files were renamed.")
    exit(0)

# Create backup of references.json
backup_path = REFERENCES_JSON.with_suffix('.json.backup-filenames')
print(f"\nCreating backup: {backup_path}")
save_references_json(references)
import shutil
shutil.copy(REFERENCES_JSON, backup_path)

# Process each mismatch
print("\n" + "=" * 80)
print("RENAMING FILES:")
print("=" * 80)

processed_files = set()
renamed_count = 0
error_count = 0

for mismatch in mismatches:
    old_filename = mismatch["old_filename"]
    new_filename = mismatch["new_filename"]

    # Check for duplicates with the new filename
    new_filename = check_duplicate_filename(
        new_filename, processed_files, target_dir=REFERENCE_DIR
    )

    old_path = REFERENCE_DIR / old_filename
    new_path = REFERENCE_DIR / new_filename

    print(f"\n{old_filename}")
    print(f"  -> {new_filename}")

    # Check if old file exists
    if not old_path.exists():
        print(f"  ERROR: File not found at {old_path}")
        error_count += 1
        continue

    # Rename the file
    try:
        if rename_file(old_path, new_path):
            # Update references.json
            ref = references[mismatch["index"]]
            ref["filename"] = new_filename
            processed_files.add(new_filename)
            renamed_count += 1
            print(f"  SUCCESS")
        else:
            print(f"  ERROR: Failed to rename file")
            error_count += 1
    except Exception as e:
        print(f"  ERROR: {e}")
        error_count += 1

# Save updated references.json
if renamed_count > 0:
    print("\n" + "=" * 80)
    print("Saving updated references.json...")
    save_references_json(references)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total mismatches: {len(mismatches)}")
print(f"Successfully renamed: {renamed_count}")
print(f"Errors: {error_count}")
print(f"Backup saved to: {backup_path}")
print("=" * 80)
