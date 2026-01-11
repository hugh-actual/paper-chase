#!/usr/bin/env python3
"""
Enrich manual_metadata.json with better metadata by:
1. Re-parsing the extracted first page text more carefully
2. Identifying real vs fake arXiv IDs
3. Extracting author/title from first page intelligently
"""

import json
import re
from pathlib import Path

# Import configuration from config.py
from src.lib.config import JSON_OUTPUT_DIR

METADATA_JSON = JSON_OUTPUT_DIR / "bad_metadata_extracted.json"
MANUAL_METADATA = JSON_OUTPUT_DIR / "manual_metadata.json"

# Known mappings from first page analysis
KNOWN_BOOKS = {
    "0002624_323629_Print_indd.pdf": {
        "author": "John Hunt",
        "title": "A Beginner's Guide to Scala, Object Orientation and Functional Programming",
        "year": "2020",
        "publisher": "Springer",
    },
    "0002624_431553_Print_indd.pdf": {
        "author": "Dilip Datta",
        "title": "LaTeX in 24 Hours: A Practical Guide for Scientific Writing",
        "year": "2020",
        "publisher": "Springer",
    },
    "0002624_447511_Print_indd.pdf": {
        "author": "Gerard O'Regan",
        "title": "Concise Guide to Software Engineering: From Fundamentals to Application Methods",
        "year": "2020",
        "publisher": "Springer",
    },
    "0002624_454700_Print_indd.pdf": {
        "author": "Antti Laaksonen",
        "title": "Guide to Competitive Programming: Learning and Improving Algorithms Through Contests",
        "year": "2017",
        "publisher": "Springer",
    },
    "0002624_StatisticalLearningFromARegres.pdf": {
        "author": "Richard A. Berk",
        "title": "Statistical Learning from a Regression Perspective",
        "year": "2017",
        "publisher": "Springer",
    },
}


def is_valid_arxiv_id(arxiv_id):
    """Check if arXiv ID is in valid format (YYMM.NNNNN)."""
    return bool(re.match(r"^\d{4}\.\d{4,5}$", arxiv_id))


def parse_first_page_carefully(first_page, filename):
    """Parse first page text more carefully to extract author and title."""
    lines = [l.strip() for l in first_page.split("\n") if l.strip()]

    result = {"author": None, "title": None}

    # Special patterns for different types of documents

    # Pattern 1: Author name followed by title (common in books)
    # Look for capitalized name followed by a longer title
    author_line_idx = None
    for i, line in enumerate(lines[:20]):
        # Check if line looks like an author name
        # (2-4 words, each capitalized, not too long)
        words = line.split()
        if (
            2 <= len(words) <= 4
            and all(w[0].isupper() for w in words if w)
            and len(line) < 50
            and "@" not in line
        ):
            # Next few lines might be the title
            author_line_idx = i
            result["author"] = line
            break

    if author_line_idx is not None:
        # Look for title in next few lines
        for i in range(author_line_idx + 1, min(author_line_idx + 5, len(lines))):
            line = lines[i]
            # Title is usually longer, may span multiple conceptual parts
            if (
                20 < len(line) < 150
                and not line.isupper()
                and "@" not in line
                and "http" not in line.lower()
            ):
                result["title"] = line
                break

    # Pattern 2: Paper style - title at top, then authors
    if not result["title"]:
        for i, line in enumerate(lines[:10]):
            if (
                30 < len(line) < 150
                and not "@" in line
                and not "http" in line.lower()
                and not line.startswith("Springer")
                and not line.startswith("Undergraduate")
            ):
                result["title"] = line
                # Look for author in next few lines
                for j in range(i + 1, min(i + 5, len(lines))):
                    author_line = lines[j]
                    # Author often has @ or appears before it
                    if "@" in author_line or "gmail" in author_line:
                        # Extract name before @
                        match = re.search(
                            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})", author_line
                        )
                        if match:
                            result["author"] = match.group(1)
                            break
                break

    return result


def enrich_metadata():
    """Enrich manual metadata with better data."""
    # Load extracted data
    with open(METADATA_JSON, "r", encoding="utf-8") as f:
        extracted = json.load(f)

    # Load current manual metadata
    with open(MANUAL_METADATA, "r", encoding="utf-8") as f:
        manual = json.load(f)

    # Create lookup dict
    extracted_dict = {
        item["filename"]: item for item in extracted if item.get("success")
    }

    enriched_count = 0

    for filename in manual.keys():
        # Apply known metadata first
        if filename in KNOWN_BOOKS:
            manual[filename].update(KNOWN_BOOKS[filename])
            manual[filename]["notes"] = ["Manually identified from first page"]
            enriched_count += 1
            continue

        # Get extracted data
        if filename not in extracted_dict:
            continue

        item = extracted_dict[filename]
        first_page = item.get("first_page_preview", "")
        identifiers = item.get("identifiers", {})

        # Fix arXiv IDs - remove fake ones
        if "arxiv" in identifiers:
            arxiv_id = identifiers["arxiv"]
            if not is_valid_arxiv_id(arxiv_id):
                # Remove fake arXiv ID
                manual[filename]["notes"] = [
                    n
                    for n in manual[filename].get("notes", [])
                    if not n.startswith("arXiv:")
                ]
                manual[filename]["publisher"] = None

        # Re-parse first page for better author/title
        parsed = parse_first_page_carefully(first_page, filename)

        # Update if we found better data
        if parsed["author"] and not manual[filename]["author"]:
            manual[filename]["author"] = parsed["author"]
            enriched_count += 1

        if parsed["title"] and (
            not manual[filename]["title"]
            or len(parsed["title"]) > len(str(manual[filename]["title"]))
        ):
            manual[filename]["title"] = parsed["title"]
            enriched_count += 1

    # Write back
    with open(MANUAL_METADATA, "w", encoding="utf-8") as f:
        json.dump(manual, f, indent=2, ensure_ascii=False)

    print(f"✓ Enriched {enriched_count} metadata entries")
    print(f"✓ Updated: {MANUAL_METADATA}")

    # Show files still needing attention
    needs_review = []
    for filename, meta in manual.items():
        if not meta.get("author") or not meta.get("title"):
            needs_review.append(filename)

    print(f"\n⚠️  {len(needs_review)} files still need manual review")
    if needs_review:
        for f in needs_review[:10]:
            print(f"  - {f}")
        if len(needs_review) > 10:
            print(f"  ... and {len(needs_review) - 10} more")


if __name__ == "__main__":
    enrich_metadata()
