#!/usr/bin/env python3
"""
Find all files starting with 'al_' and generate proposed new filenames.
Creates JSON output with before/after comparison for user review.
"""

import json
from pathlib import Path

from src.lib.config import JSON_OUTPUT_DIR
from src.lib.utils import (
    load_references_json,
    parse_author,
    sanitize_title,
    check_duplicate_filename,
    REFERENCE_DIR,
)

OUTPUT_JSON = JSON_OUTPUT_DIR / "al_files_to_fix.json"


def main():
    print("Finding files starting with 'al_'...")
    print("=" * 70)

    # Load all references
    entries = load_references_json()

    # Find al_* files
    al_files = [e for e in entries if e["filename"].startswith("al_")]
    print(f"Found {len(al_files)} files starting with 'al_'\n")

    results = []
    processed_files = set()

    print("Generating proposed new filenames:\n")
    print(f"{'OLD FILENAME':<50} -> {'NEW FILENAME'}")
    print("=" * 110)

    for entry in al_files:
        old_filename = entry["filename"]
        author = entry.get("author", "Unknown")
        title = entry.get("title", "Untitled")
        year = entry.get("year", "")
        publisher = entry.get("publisher", "")

        # Generate new filename using FIXED parse_author()
        author_filename, author_names = parse_author(author)
        title_filename = sanitize_title(title)
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

        # Add to results
        result = {
            "old_filename": old_filename,
            "new_filename": new_filename,
            "author": author,
            "title": title,
            "year": year,
            "publisher": publisher,
        }
        results.append(result)

        # Print comparison
        print(f"{old_filename:<50} -> {new_filename}")

    # Save to JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 110)
    print(f"\n✓ Saved {len(results)} entries to: {OUTPUT_JSON}")
    print(f"\nNext steps:")
    print(f"1. Review the proposed changes above")
    print(f"2. Check {OUTPUT_JSON} for details")
    print(f"3. If approved, run: uv run python update_al_files.py")
    print("=" * 110)


if __name__ == "__main__":
    main()
