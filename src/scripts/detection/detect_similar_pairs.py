#!/usr/bin/env python3
"""
Detect similar pairs of PDFs (same author, 70%+ title similarity).
Generates fresh results based on current metadata in references.json.

Output includes annotation fields for manual review (quarantine, suggested_*).
"""

import json

from src.lib.utils import (
    load_references_json,
    JSON_OUTPUT_DIR,
    detect_similar_entries,
)


def main():
    print("Detecting similar pairs...")
    print("=" * 70)

    # Load references
    entries = load_references_json()
    print(f"Loaded {len(entries)} entries\n")

    # Detect similar pairs (70% threshold) with annotation fields
    print("Finding pairs with same author and 70%+ title similarity...")
    similar_pairs = detect_similar_entries(
        entries, similarity_threshold=0.70, include_annotations=True
    )
    print(f"Found {len(similar_pairs)} similar pairs\n")

    # Generate output
    output = {
        "summary": {
            "total_files": len(entries),
            "similar_pairs": len(similar_pairs),
            "threshold": 0.70,
            "generated": "2025-12-31",
        },
        "similar_pairs": similar_pairs,
    }

    # Save to JSON
    output_file = JSON_OUTPUT_DIR / "similar_pairs.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Show preview
    print("=" * 70)
    print("SIMILAR PAIRS PREVIEW")
    print("=" * 70)

    for i, pair in enumerate(similar_pairs[:5], 1):
        print(f"\n{i}. Similarity: {pair['similarity']} | Author: {pair['author']}")
        print(f"   File 1: {pair['file1']['filename']}")
        print(f"           {pair['file1']['title']} ({pair['file1']['year']})")
        print(f"   File 2: {pair['file2']['filename']}")
        print(f"           {pair['file2']['title']} ({pair['file2']['year']})")

    if len(similar_pairs) > 5:
        print(f"\n   ... and {len(similar_pairs) - 5} more pairs")

    print(f"\n{'=' * 70}")
    print(f"✓ Full report saved to: {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
