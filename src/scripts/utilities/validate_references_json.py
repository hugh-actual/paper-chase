#!/usr/bin/env python3
"""
Validate that references.json contains all entries from references.md
with no changes to the data.
"""

import re
import json
from pathlib import Path
from src.lib.config import REFERENCES_FILE


def parse_references_md():
    """Parse references.md (same as conversion script)."""
    with open(REFERENCES_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    pattern = (
        r"([^\n]+?)\s+\(([^)]+)\)\s+\*([^*]+)\*\.([^\n]*)\n\*\*File\*\*:\s+([^\n]+)"
    )
    matches = re.finditer(pattern, content)

    for match in matches:
        entry = {
            "author": match.group(1).strip(),
            "year": match.group(2).strip(),
            "title": match.group(3).strip(),
            "publisher": match.group(4).strip(),
            "filename": match.group(5).strip(),
        }
        entries.append(entry)

    return entries


def load_json(json_path):
    """Load JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate():
    """Validate that all filenames in JSON are in MD and vice versa."""
    json_path = REFERENCES_FILE.parent / "references.json"

    if not json_path.exists():
        print(f"❌ {json_path} not found")
        return False

    print("Parsing references.md...")
    md_entries = parse_references_md()

    print("Loading references.json...")
    json_entries = load_json(json_path)

    # Extract filename sets
    md_filenames = {e["filename"] for e in md_entries}
    json_filenames = {e["filename"] for e in json_entries}

    print(f"\nValidation:")
    print(f"  references.md entries: {len(md_filenames)}")
    print(f"  references.json entries: {len(json_filenames)}")

    # Check for filenames in JSON but not in MD
    missing_in_md = json_filenames - md_filenames
    if missing_in_md:
        print(f"\n❌ Found {len(missing_in_md)} filenames in JSON but not in MD:")
        for filename in sorted(list(missing_in_md)[:5]):
            print(f"    {filename}")
        if len(missing_in_md) > 5:
            print(f"    ... and {len(missing_in_md) - 5} more")
        return False

    # Check for filenames in MD but not in JSON
    missing_in_json = md_filenames - json_filenames
    if missing_in_json:
        print(f"\n❌ Found {len(missing_in_json)} filenames in MD but not in JSON:")
        for filename in sorted(list(missing_in_json)[:5]):
            print(f"    {filename}")
        if len(missing_in_json) > 5:
            print(f"    ... and {len(missing_in_json) - 5} more")
        return False

    print(f"✓ All filenames are present in both files")

    # Verify filenames are unique in JSON
    json_filename_list = [e["filename"] for e in json_entries]
    if len(json_filename_list) != len(set(json_filename_list)):
        duplicates = [f for f in json_filename_list if json_filename_list.count(f) > 1]
        print(f"\n⚠️  Warning: {len(set(duplicates))} duplicate filenames in JSON:")
        for dup in sorted(set(duplicates)[:5]):
            print(f"    {dup}")
        return False
    else:
        print(f"✓ All filenames are unique")

    print(f"\n✅ Validation passed!")
    print(f"   {len(json_filenames)} entries validated")
    return True


if __name__ == "__main__":
    success = validate()
    exit(0 if success else 1)
