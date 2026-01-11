#!/usr/bin/env python3
"""
Add SHA256 file hash to each entry in references.json.
This is a one-time operation to enable duplicate detection.
"""

from src.lib.utils import (
    REFERENCE_DIR,
    load_references_json,
    save_references_json,
    calculate_file_hash,
)


def main():
    print("Adding file hashes to references.json...")
    print("=" * 70)

    # Load references
    entries = load_references_json()
    print(f"Loaded {len(entries)} entries\n")

    # Track progress
    updated = 0
    already_had_hash = 0
    errors = []

    print("Calculating hashes (this may take ~30 seconds)...")
    print("")

    for i, entry in enumerate(entries, 1):
        filename = entry["filename"]

        # Skip if already has hash
        if "file_hash" in entry and entry["file_hash"]:
            already_had_hash += 1
            if i % 50 == 0:
                print(f"  Progress: {i}/{len(entries)} files...")
            continue

        # Calculate hash
        filepath = REFERENCE_DIR / filename
        if not filepath.exists():
            print(f"  [!] File not found: {filename}")
            errors.append(f"File not found: {filename}")
            continue

        file_hash = calculate_file_hash(filepath)
        if file_hash:
            entry["file_hash"] = file_hash
            updated += 1

        # Progress indicator
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(entries)} files...")

    # Save updated references.json
    save_references_json(entries)

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total entries: {len(entries)}")
    print(f"Hashes added: {updated}")
    print(f"Already had hash: {already_had_hash}")
    print(f"Errors: {len(errors)}")

    if errors:
        print(f"\nErrors:")
        for err in errors:
            print(f"  - {err}")

    print(f"\n✓ references.json updated with file hashes")
    print("=" * 70)


if __name__ == "__main__":
    main()
