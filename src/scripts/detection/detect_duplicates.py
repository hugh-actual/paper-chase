#!/usr/bin/env python3
"""
Detect potential duplicate PDFs in the reference collection.
Generates a JSON report for manual review - does not modify files.

Detection strategies:
1. Exact duplicates: Same file hash (SHA256)
2. Similar entries: Same author + 70%+ title similarity
3. Filename suffixes: Files with _2, _3, etc. (flagged during ingestion)
"""

import json
import re

from src.lib.utils import (
    load_references_json,
    JSON_OUTPUT_DIR,
    detect_exact_duplicates,
    detect_similar_entries,
)


def detect_filename_suffix_duplicates(entries):
    """
    Find files with numeric suffixes (_2, _3, etc.) that suggest duplicates.
    These were likely flagged during ingestion.
    """
    suffix_pattern = re.compile(r"(.+)_(\d+)\.pdf$")
    suffix_files = []

    for entry in entries:
        filename = entry["filename"]
        match = suffix_pattern.match(filename)
        if match:
            base_name = match.group(1)
            suffix_num = match.group(2)
            suffix_files.append(
                {
                    "filename": filename,
                    "base_name": base_name,
                    "suffix": suffix_num,
                    "author": entry.get("author", ""),
                    "title": entry.get("title", ""),
                    "year": entry.get("year", ""),
                    "publisher": entry.get("publisher", ""),
                    "original_filename": entry.get("original_filename", ""),
                }
            )

    # Sort by base_name, then suffix
    suffix_files.sort(key=lambda x: (x["base_name"], int(x["suffix"])))

    return suffix_files


def main():
    print("Detecting duplicate PDFs...")
    print("=" * 70)

    # Load references
    entries = load_references_json()
    print(f"Loaded {len(entries)} entries\n")

    # Check that file hashes exist
    has_hash = sum(1 for e in entries if "file_hash" in e and e["file_hash"])
    if has_hash == 0:
        print("⚠ Warning: No file hashes found in references.json")
        print("Run 'uv run python add_file_hashes.py' first")
        return
    elif has_hash < len(entries):
        print(f"⚠ Warning: Only {has_hash}/{len(entries)} entries have file hashes")
        print("Some files may not be checked for exact duplicates\n")

    # Tier 1: Exact duplicates (same hash)
    print("1. Detecting exact duplicates (same file hash)...")
    exact_duplicates = detect_exact_duplicates(entries)
    print(f"   Found {len(exact_duplicates)} groups with exact duplicates")

    # Tier 2: Similar title + author (70% threshold)
    print("2. Detecting similar entries (same author, 70%+ title similarity)...")
    similar_pairs = detect_similar_entries(entries, similarity_threshold=0.70)
    print(f"   Found {len(similar_pairs)} similar pairs")

    # Tier 3: Filename suffix pattern
    print("3. Detecting filename suffix patterns (_2.pdf, _3.pdf)...")
    suffix_files = detect_filename_suffix_duplicates(entries)
    print(f"   Found {len(suffix_files)} files with numeric suffixes")

    # Generate output
    output = {
        "summary": {
            "total_files": len(entries),
            "exact_duplicate_groups": len(exact_duplicates),
            "similar_pairs": len(similar_pairs),
            "suffix_pattern_files": len(suffix_files),
            "generated": "2025-12-30",
        },
        "exact_duplicates": exact_duplicates,
        "similar_pairs": similar_pairs,
        "suffix_pattern_files": suffix_files,
    }

    # Save to JSON
    output_file = JSON_OUTPUT_DIR / "duplicate_candidates.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total files analyzed: {len(entries)}")
    print(f"Exact duplicate groups: {len(exact_duplicates)}")
    print(f"Similar pairs (70%+ match): {len(similar_pairs)}")
    print(f"Filename suffix patterns: {len(suffix_files)}")
    print(f"\n✓ Report saved to: {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
