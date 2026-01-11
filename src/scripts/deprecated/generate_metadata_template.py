#!/usr/bin/env python3
"""
Generate manual_metadata.json template from extracted data.
Includes best-guess metadata that needs manual review and correction.
"""

import json
import re
from pathlib import Path

# Import configuration from config.py
from src.lib.config import JSON_OUTPUT_DIR

METADATA_JSON = JSON_OUTPUT_DIR / "bad_metadata_extracted.json"
OUTPUT_FILE = JSON_OUTPUT_DIR / "manual_metadata.json"


def extract_year_from_metadata(metadata_dict):
    """Extract year from metadata creation date."""
    for key in ["CreationDate", "ModDate"]:
        if key in metadata_dict:
            date_str = metadata_dict[key]
            # Format: D:20200501183358Z00'00'
            match = re.search(r"D:(\d{4})", date_str)
            if match:
                return match.group(1)
    return None


def clean_title(title_text):
    """Clean extracted title text."""
    if not title_text:
        return None

    # Remove common prefixes
    title_text = re.sub(
        r"^(Undergraduate Topics in Computer Science|Springer Texts in Statistics)\s*",
        "",
        title_text,
    )

    # Remove trailing ellipsis
    title_text = title_text.rstrip(".")

    # Basic cleanup
    title_text = title_text.strip()

    # If too short, it's probably not a good title
    if len(title_text) < 10:
        return None

    return title_text


def generate_metadata_from_extraction(item):
    """Generate best-guess metadata from extracted data."""
    filename = item["filename"]
    metadata = item.get("metadata", {})
    identifiers = item.get("identifiers", {})
    first_page = item.get("first_page_preview", "")

    result = {
        "author": None,
        "title": None,
        "year": None,
        "publisher": None,
        "notes": [],
    }

    # Try to get author
    if "extracted_author" in identifiers:
        result["author"] = identifiers["extracted_author"]
    elif (
        "Author" in metadata and metadata["Author"] and metadata["Author"] != "0002624"
    ):
        result["author"] = metadata["Author"]

    # Try to get title
    if "extracted_title" in identifiers:
        cleaned = clean_title(identifiers["extracted_title"])
        if cleaned:
            result["title"] = cleaned
        elif first_page:
            # Try to extract from first page more carefully
            lines = [l.strip() for l in first_page.split("\n") if l.strip()]
            for line in lines[:15]:  # Check first 15 lines
                # Look for author name followed by title
                if len(line) > 15 and len(line) < 150:
                    result["title"] = line
                    break

    if not result["title"] and "Title" in metadata and metadata["Title"]:
        result["title"] = (
            metadata["Title"].replace("_Print.indd", "").replace(".indd", "")
        )

    # Try to get year
    year = extract_year_from_metadata(metadata)
    if year:
        result["year"] = year

    # Check for real arXiv papers (2009.xxxxx, 2010.xxxxx format)
    if "arxiv" in identifiers:
        arxiv_id = identifiers["arxiv"]
        # Valid arXiv IDs are YYMM.NNNNN
        if re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
            result["notes"].append(f"arXiv:{arxiv_id}")
            result["publisher"] = "arXiv preprint"

    # Extract publisher hints
    if "Springer" in first_page:
        result["publisher"] = "Springer"
    elif "IEEE" in first_page:
        result["publisher"] = "IEEE"
    elif "Journal" in first_page:
        # Try to extract journal name
        match = re.search(r"(Journal[^,\n]{5,80})", first_page)
        if match:
            result["publisher"] = match.group(1).strip()

    # Extract DOI if present
    doi_match = re.search(r"10\.\d{4,}/[^\s]+", first_page)
    if doi_match:
        result["notes"].append(f"DOI:{doi_match.group(0)}")

    # Add special notes for certain file patterns
    if "_dvi.pdf" in filename:
        result["notes"].append("DVI conversion - may need special handling")
    if "Print_indd" in filename:
        result["notes"].append("InDesign print file")
    if filename.startswith("untitled"):
        result["notes"].append("NEEDS MANUAL REVIEW - untitled file")

    return result


def main():
    print("Generating manual metadata template...")

    with open(METADATA_JSON, "r", encoding="utf-8") as f:
        extracted_data = json.load(f)

    manual_metadata = {}

    for item in extracted_data:
        if not item.get("success"):
            continue

        filename = item["filename"]
        metadata = generate_metadata_from_extraction(item)

        manual_metadata[filename] = metadata

    # Write output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(manual_metadata, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Generated template: {OUTPUT_FILE}")
    print(f"✓ Contains {len(manual_metadata)} entries")
    print("\nNext steps:")
    print("1. Review and edit manual_metadata.json")
    print("2. Fill in missing author, title, year, publisher fields")
    print("3. For arXiv papers, look them up online using the arXiv ID")
    print("4. Run rename_and_update_bad_metadata.py to apply changes")

    # Show some examples that need attention
    needs_review = []
    for filename, meta in manual_metadata.items():
        if (
            not meta["author"]
            or not meta["title"]
            or "NEEDS MANUAL REVIEW" in str(meta["notes"])
        ):
            needs_review.append(filename)

    if needs_review:
        print(f"\n⚠️  {len(needs_review)} files need special attention:")
        for f in needs_review[:10]:
            print(f"  - {f}")
        if len(needs_review) > 10:
            print(f"  ... and {len(needs_review) - 10} more")


if __name__ == "__main__":
    main()
