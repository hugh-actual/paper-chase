#!/usr/bin/env python3
"""Fix duplicate author names in references.json using the corrected parse_author function"""

import json
import re
from pathlib import Path
from src.lib.utils import parse_author

# Load references.json
refs_path = Path("~/docs/references.json")
with open(refs_path, "r") as f:
    references = json.load(f)

print(f"Total references: {len(references)}")
print("=" * 80)
print("FIXING DUPLICATED AUTHOR NAMES")
print("=" * 80)

fixes_made = 0
backup_path = refs_path.with_suffix('.json.backup')

# Create backup
print(f"\nCreating backup at: {backup_path}")
with open(backup_path, "w") as f:
    json.dump(references, f, indent=2, ensure_ascii=False)

for i, ref in enumerate(references):
    author = ref.get("author", "")
    if not author or author == "Unknown":
        continue

    # Use the fixed parse_author to get the correct author list
    _, correct_author_names = parse_author(author)

    # Remove duplicates from the author list while preserving order
    seen = set()
    deduped_names = []
    for name in correct_author_names:
        # Normalize for comparison (lowercase, strip)
        name_lower = name.lower().strip()
        if name_lower not in seen:
            seen.add(name_lower)
            deduped_names.append(name)

    # Reconstruct the author string
    corrected_author = ", ".join(deduped_names)

    # Check if it's different from the original
    if corrected_author != author:
        print(f"\nEntry {i + 1}:")
        print(f"  OLD: {author}")
        print(f"  NEW: {corrected_author}")
        print(f"  Title: {ref.get('title', '')[:60]}...")

        # Update the reference
        ref["author"] = corrected_author
        fixes_made += 1

# Save the corrected references
if fixes_made > 0:
    print(f"\n{'=' * 80}")
    print(f"Saving {fixes_made} corrections to {refs_path}")
    with open(refs_path, "w") as f:
        json.dump(references, f, indent=2, ensure_ascii=False)
    print("Done!")
else:
    print(f"\n{'=' * 80}")
    print("No corrections needed - all authors are already correct!")

print(f"{'=' * 80}")
print(f"Total fixes applied: {fixes_made}")
