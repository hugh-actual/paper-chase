#!/usr/bin/env python3
"""
Process files with bad metadata:
1. Extract metadata and first page text
2. Generate improved metadata report
3. Prepare for renaming and references.md update
"""

import json
import re
from pathlib import Path
import PyPDF2

# Import configuration from config.py
from src.lib.config import REFERENCE_DIR, MARKDOWN_DIR, JSON_OUTPUT_DIR

# Configuration
BAD_METADATA_FILE = MARKDOWN_DIR / "bad_metadata.md"
OUTPUT_JSON = JSON_OUTPUT_DIR / "bad_metadata_extracted.json"


def extract_metadata_safe(pdf_path):
    """Extract metadata and first page text from PDF without rendering."""
    try:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)

            # Get metadata
            metadata = reader.metadata

            # Get first page text (limited extraction)
            first_page_text = ""
            if len(reader.pages) > 0:
                try:
                    # Extract first 2000 chars from first page
                    first_page_text = reader.pages[0].extract_text()[:2000]
                except:
                    first_page_text = "[Could not extract text]"

            result = {
                "filename": pdf_path.name,
                "filepath": str(pdf_path),
                "success": True,
                "metadata": {},
                "first_page_preview": first_page_text,
                "num_pages": len(reader.pages),
                "identifiers": {},
            }

            # Extract metadata fields if available
            if metadata:
                for key in [
                    "/Title",
                    "/Author",
                    "/Subject",
                    "/Creator",
                    "/Producer",
                    "/CreationDate",
                    "/ModDate",
                ]:
                    if key in metadata:
                        result["metadata"][key.replace("/", "")] = str(metadata[key])

            # Try to identify papers by pattern
            result["identifiers"] = identify_paper(pdf_path.name, first_page_text)

            return result

    except Exception as e:
        return {
            "filename": pdf_path.name,
            "filepath": str(pdf_path),
            "success": False,
            "error": str(e),
        }


def identify_paper(filename, first_page_text):
    """Identify paper by arXiv ID, DOI, or other patterns."""
    identifiers = {}

    # Check for arXiv ID in filename (e.g., 2009_06732.pdf)
    arxiv_match = re.search(r"(\d{4})_(\d{4,5})", filename)
    if arxiv_match:
        identifiers["arxiv"] = f"{arxiv_match.group(1)}.{arxiv_match.group(2)}"
        identifiers["type"] = "arxiv"

    # Check for DOI in first page
    doi_match = re.search(r"10\.\d{4,}/[^\s]+", first_page_text)
    if doi_match:
        identifiers["doi"] = doi_match.group(0)
        identifiers["type"] = "doi"

    # Check for arXiv in first page text
    arxiv_text_match = re.search(r"arXiv:(\d{4}\.\d{4,5})", first_page_text)
    if arxiv_text_match:
        identifiers["arxiv"] = arxiv_text_match.group(1)
        identifiers["type"] = "arxiv"

    # Check for journal PII
    pii_match = re.search(r"PII[:\s]+([A-Z0-9\-()]+)", first_page_text)
    if pii_match:
        identifiers["pii"] = pii_match.group(1)
        identifiers["type"] = "journal"

    # Extract title from first page (usually in first few lines)
    # Look for lines with title-like characteristics
    lines = first_page_text.split("\n")
    potential_title = None
    for i, line in enumerate(lines[:10]):  # Check first 10 lines
        line = line.strip()
        # Title lines are usually: longer, not all caps, not email/url
        if (
            len(line) > 20
            and len(line) < 200
            and not "@" in line
            and not "http" in line
            and not line.isupper()
            and not line.startswith("[")
        ):
            potential_title = line
            break

    if potential_title:
        identifiers["extracted_title"] = potential_title

    # Extract author from first page (look for common patterns)
    author_patterns = [
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+[a-z]+@",  # Name before email
        r"(?:by|By)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",  # "by Author Name"
    ]
    for pattern in author_patterns:
        match = re.search(pattern, first_page_text)
        if match:
            identifiers["extracted_author"] = match.group(1)
            break

    return identifiers


def parse_bad_metadata_file():
    """Parse bad_metadata.md to get list of suspect files."""
    files = []
    with open(BAD_METADATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            # Look for lines like: 1. `filename.pdf`
            match = re.search(r"\d+\.\s+`([^`]+\.pdf)`", line)
            if match:
                files.append(match.group(1))
    return files


def main():
    print("Processing files with bad metadata...")

    # Get list of bad metadata files
    bad_files = parse_bad_metadata_file()
    print(f"Found {len(bad_files)} files to process\n")

    results = []

    # Process each file
    for i, filename in enumerate(bad_files, 1):
        filepath = REFERENCE_DIR / filename

        if not filepath.exists():
            print(f"[{i}/{len(bad_files)}] ⚠️  File not found: {filename}")
            results.append(
                {"filename": filename, "success": False, "error": "File not found"}
            )
            continue

        print(f"[{i}/{len(bad_files)}] Processing: {filename}")
        result = extract_metadata_safe(filepath)
        results.append(result)

        # Print summary
        if result["success"]:
            identifiers = result.get("identifiers", {})
            if "arxiv" in identifiers:
                print(f"  → arXiv ID: {identifiers['arxiv']}")
            if "extracted_title" in identifiers:
                print(f"  → Title: {identifiers['extracted_title'][:80]}...")
            if "extracted_author" in identifiers:
                print(f"  → Author: {identifiers['extracted_author']}")
        else:
            print(f"  → Error: {result.get('error', 'Unknown error')}")

    # Save results to JSON
    print(f"\nSaving results to {OUTPUT_JSON}")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Generate summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    successful = sum(1 for r in results if r.get("success", False))
    with_arxiv = sum(
        1 for r in results if r.get("success") and "arxiv" in r.get("identifiers", {})
    )
    with_title = sum(
        1
        for r in results
        if r.get("success") and "extracted_title" in r.get("identifiers", {})
    )

    print(f"Total files processed: {len(results)}")
    print(f"Successful extractions: {successful}")
    print(f"Files with arXiv ID: {with_arxiv}")
    print(f"Files with extracted title: {with_title}")
    print(f"\nResults saved to: {OUTPUT_JSON}")
    print(f"\nNext step: Review the JSON file and use it to:")
    print(f"  1. Look up missing metadata (especially arXiv papers)")
    print(f"  2. Rename files to proper Author_Title.pdf format")
    print(f"  3. Update references.md with correct citations")
    print("=" * 60)


if __name__ == "__main__":
    main()
