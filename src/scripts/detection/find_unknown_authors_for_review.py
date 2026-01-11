#!/usr/bin/env python3
"""
Find all entries with Unknown/null/--- authors and generate a review file.
Creates JSON output similar to broken_titles.json for user review.
"""

import json

from src.lib.config import JSON_OUTPUT_DIR
from src.lib.utils import load_references_json, is_unknown_author

OUTPUT_JSON = JSON_OUTPUT_DIR / "unknown_authors.json"


def main():
    print("Finding entries with Unknown/null/--- authors...")
    print("=" * 70)

    # Load all references
    entries = load_references_json()

    # Find entries with unknown authors
    unknown_entries = [e for e in entries if is_unknown_author(e.get("author", ""))]
    print(f"Found {len(unknown_entries)} entries with unknown authors\n")

    results = []

    print("Entries with unknown authors:\n")
    print(f"{'FILENAME':<60} | {'TITLE'}")
    print("=" * 120)

    for entry in unknown_entries:
        filename = entry.get("filename", "")
        author = entry.get("author", "")
        title = entry.get("title", "")
        year = entry.get("year", "")
        publisher = entry.get("publisher", "")

        # Create result entry
        result = {
            "author": author,
            "title": title,
            "suggested_author": None,  # User to fill in
            "suggested_title": None,  # User to fill in (if needed)
            "year": year,
            "publisher": publisher,
            "filename": filename,
            "reasons": [],
        }

        # Add reasons
        if not author or author.strip() == "":
            result["reasons"].append("Author field is empty")
        elif author.strip().lower() == "unknown":
            result["reasons"].append('Author is "Unknown"')
        elif author.strip() == "---":
            result["reasons"].append('Author is "---"')

        results.append(result)

        # Print for review
        print(f"{filename:<60} | {title[:55]}")

    # Sort by filename for easier review
    results.sort(key=lambda x: x["filename"])

    # Save to JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 120)
    print(f"\n✓ Saved {len(results)} entries to: {OUTPUT_JSON}")
    print(f"\nNext steps:")
    print(f"1. Review the entries above")
    print(f"2. Open {OUTPUT_JSON} and fill in 'suggested_author' for each entry")
    print(f"3. Optionally update 'suggested_title' if title also needs fixing")
    print(f"4. Run update script to apply changes")
    print("=" * 120)


if __name__ == "__main__":
    main()
