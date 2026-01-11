#!/usr/bin/env python3
"""
Generate references.md from references.json.
Sorts entries by author surname and creates Harvard-style markdown.
"""

import json
from pathlib import Path
from src.lib.config import REFERENCES_JSON, REFERENCES_FILE
from src.lib.utils import create_harvard_reference


def extract_surname(author_str):
    """Extract surname for sorting."""
    # Handle special cases
    if author_str.startswith("---") or author_str == "Unknown":
        return "ZZZ"  # Sort broken/unknown entries to end

    # Get first author's surname
    if " and " in author_str:
        author_str = author_str.split(" and ")[0]
    if ", " in author_str:
        author_str = author_str.split(",")[0]

    # Get last word as surname
    parts = author_str.strip().split()
    if parts:
        # Handle "(eds)" or other suffixes
        surname = parts[-1].strip("()").replace("(eds)", "")
        return surname
    return author_str


def parse_author_names(author_str):
    """Parse author string into list of names for create_harvard_reference."""
    if not author_str or author_str == "Unknown":
        return ["Unknown"]

    # Handle "and" separators
    if " and " in author_str:
        # Split on "and" and clean up commas
        parts = author_str.split(" and ")
        names = []
        for part in parts:
            # Remove trailing commas from parts before "and"
            cleaned = part.strip().rstrip(",")
            names.append(cleaned)
        return names
    # Handle comma separators
    elif ", " in author_str:
        return [a.strip() for a in author_str.split(",")]
    else:
        return [author_str.strip()]


def generate_markdown():
    """Generate references.md from references.json."""
    # Load JSON
    if not REFERENCES_JSON.exists():
        print(f"❌ {REFERENCES_JSON} not found")
        return False

    with open(REFERENCES_JSON, "r", encoding="utf-8") as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries from {REFERENCES_JSON}")

    # Sort by filename (matches directory listing order)
    sorted_entries = sorted(entries, key=lambda e: e["filename"].lower())

    # Generate markdown
    lines = [
        "# References\n",
        "\n",
        "Harvard-style bibliography of processed documents.\n",
        "\n",
        "---\n",
        "\n",
    ]

    for entry in sorted_entries:
        author_names = parse_author_names(entry["author"])
        year = entry["year"] if entry["year"] else None

        harvard_ref = create_harvard_reference(
            author_names,
            year,
            entry["title"],
            entry["publisher"] if entry["publisher"] else None,
            entry["filename"],
        )
        lines.append(harvard_ref + "\n\n")

    # Write to file
    with open(REFERENCES_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✓ Generated {REFERENCES_FILE}")
    print(f"  {len(sorted_entries)} entries sorted by filename")
    return True


if __name__ == "__main__":
    success = generate_markdown()
    exit(0 if success else 1)
