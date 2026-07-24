#!/usr/bin/env python3
"""
Detect potential duplicate PDFs in the reference collection.
Generates JSON reports for manual review - does not modify files.

Detection strategies:
1. Exact duplicates: Same file hash (SHA256)
2. Similar entries: Same author + 70%+ title similarity
3. Filename suffixes: Files with _2, _3, etc. (flagged during ingestion)

Writes two reports, each the sole annotation surface for its update script:
- duplicate_candidates.json: exact duplicates (annotated, read by
  update-dups) plus suffix-pattern files for information
- similar_pairs.json: annotated similar pairs (read by update-similar)
"""

import json
import re
from datetime import datetime

from src.lib import config
from src.lib.utils import (
    load_references_json,
    detect_exact_duplicates,
    detect_similar_entries,
    add_annotation_fields,
)

SIMILARITY_THRESHOLD = 0.70


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
        print("File hashes are added automatically during ingestion.")
        return
    elif has_hash < len(entries):
        print(f"⚠ Warning: Only {has_hash}/{len(entries)} entries have file hashes")
        print("Some files may not be checked for exact duplicates\n")

    generated = datetime.now().isoformat()

    # Tier 1: Exact duplicates (same hash)
    print("1. Detecting exact duplicates (same file hash)...")
    exact_duplicates = detect_exact_duplicates(entries)
    for group in exact_duplicates:
        add_annotation_fields(group["files"])
    print(f"   Found {len(exact_duplicates)} groups with exact duplicates")

    # Tier 2: Similar title + author, with annotation fields
    print(
        "2. Detecting similar entries (same author, "
        f"{SIMILARITY_THRESHOLD:.0%}+ title similarity)..."
    )
    similar_pairs = detect_similar_entries(
        entries, similarity_threshold=SIMILARITY_THRESHOLD, include_annotations=True
    )
    print(f"   Found {len(similar_pairs)} similar pairs")

    # Tier 3: Filename suffix pattern (informational only - no update
    # script consumes annotations on this tier)
    print("3. Detecting filename suffix patterns (_2.pdf, _3.pdf)...")
    suffix_files = detect_filename_suffix_duplicates(entries)
    print(f"   Found {len(suffix_files)} files with numeric suffixes")

    # Full report; similar pairs live only in similar_pairs.json so there
    # is a single annotatable copy
    output = {
        "summary": {
            "total_files": len(entries),
            "exact_duplicate_groups": len(exact_duplicates),
            "similar_pairs": len(similar_pairs),
            "suffix_pattern_files": len(suffix_files),
            "generated": generated,
        },
        "exact_duplicates": exact_duplicates,
        "suffix_pattern_files": suffix_files,
    }

    output_file = config.JSON_OUTPUT_DIR / "duplicate_candidates.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Similar-pairs report (read by update-similar and status)
    similar_output = {
        "summary": {
            "total_files": len(entries),
            "similar_pairs": len(similar_pairs),
            "threshold": SIMILARITY_THRESHOLD,
            "generated": generated,
        },
        "similar_pairs": similar_pairs,
    }

    similar_file = config.JSON_OUTPUT_DIR / "similar_pairs.json"
    with open(similar_file, "w", encoding="utf-8") as f:
        json.dump(similar_output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total files analyzed: {len(entries)}")
    print(f"Exact duplicate groups: {len(exact_duplicates)}")
    print(f"Similar pairs ({SIMILARITY_THRESHOLD:.0%}+ match): {len(similar_pairs)}")
    print(f"Filename suffix patterns: {len(suffix_files)}")
    print(f"\n✓ Report saved to: {output_file}")
    print(f"✓ Similar pairs saved to: {similar_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
