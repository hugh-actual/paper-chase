#!/usr/bin/env python3
"""
Find all entries in references.md with Unknown authors and extract their metadata.
Creates a report for manual review and metadata enrichment.
"""

import re
from pathlib import Path
import PyPDF2
import json

# Import configuration from config.py
from src.lib.config import (
    REFERENCE_DIR,
    MARKDOWN_DIR,
    JSON_OUTPUT_DIR,
)
from src.lib.utils import load_references_json

OUTPUT_JSON = JSON_OUTPUT_DIR / "unknown_authors_extracted.json"


def parse_references_file():
    """Load references from JSON and extract all Unknown author entries."""
    entries = load_references_json()

    unknown_entries = []

    for entry in entries:
        # Check if author is "Unknown"
        if entry.get("author", "").strip() == "Unknown":
            unknown_entries.append(
                {
                    "filename": entry["filename"],
                    "current_year": entry.get("year", "n.d.") or "n.d.",
                    "current_title": entry.get("title", "Unknown"),
                    "current_publisher": entry.get("publisher"),
                }
            )

    return unknown_entries


def extract_pdf_metadata(pdf_path):
    """Extract metadata from PDF."""
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)

            metadata = {}
            if reader.metadata:
                for key in [
                    "/Title",
                    "/Author",
                    "/Subject",
                    "/Creator",
                    "/Producer",
                    "/CreationDate",
                    "/ModDate",
                ]:
                    if key in reader.metadata:
                        metadata[key.replace("/", "")] = str(reader.metadata[key])

            # Extract first page text
            first_page_text = ""
            if len(reader.pages) > 0:
                try:
                    first_page_text = reader.pages[0].extract_text()[:2000]
                except:
                    first_page_text = "[Could not extract text]"

            return {
                "success": True,
                "metadata": metadata,
                "first_page_preview": first_page_text,
                "num_pages": len(reader.pages),
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def identify_author_from_text(first_page_text, title):
    """Try to identify author from first page text."""
    if not first_page_text or first_page_text == "[Could not extract text]":
        return None

    lines = [l.strip() for l in first_page_text.split("\n") if l.strip()]

    # Common patterns for author identification
    potential_authors = []

    # Pattern 1: Look for email addresses and extract name before them
    for i, line in enumerate(lines[:20]):
        if "@" in line:
            # Look at previous lines for author name
            for j in range(max(0, i - 3), i):
                name_line = lines[j]
                # Check if it looks like a name (2-4 words, capitalized)
                words = name_line.split()
                if (
                    2 <= len(words) <= 4
                    and all(w[0].isupper() for w in words if w and len(w) > 1)
                    and len(name_line) < 50
                ):
                    potential_authors.append(name_line)

    # Pattern 2: Look for "by Author Name" patterns
    for line in lines[:15]:
        by_match = re.search(
            r"(?:by|By|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})", line
        )
        if by_match:
            potential_authors.append(by_match.group(1))

    # Pattern 3: Name followed by affiliation/institution
    for i, line in enumerate(lines[:15]):
        if any(
            inst in line.lower()
            for inst in ["university", "college", "institute", "laboratory"]
        ):
            # Check previous line for name
            if i > 0:
                name_line = lines[i - 1]
                words = name_line.split()
                if (
                    2 <= len(words) <= 4
                    and all(w[0].isupper() for w in words if w and len(w) > 1)
                    and len(name_line) < 50
                ):
                    potential_authors.append(name_line)

    # Return most likely author (first one found)
    if potential_authors:
        return potential_authors[0]

    return None


def identify_title_from_text(first_page_text, current_title):
    """Try to identify better title from first page text."""
    if not first_page_text or first_page_text == "[Could not extract text]":
        return None

    lines = [l.strip() for l in first_page_text.split("\n") if l.strip()]

    # Look for title-like lines (longer, not all caps, early in document)
    for line in lines[:10]:
        # Skip very short or very long lines
        if len(line) < 15 or len(line) > 200:
            continue

        # Skip lines that look like metadata
        if any(
            skip in line.lower()
            for skip in ["@", "http", "doi:", "arxiv:", "page", "volume"]
        ):
            continue

        # Skip all-caps lines (usually headers/metadata)
        if line.isupper():
            continue

        # This looks like a potential title
        if len(line) > 30 and not line.startswith("Abstract"):
            return line

    return None


def extract_year_from_metadata(metadata):
    """Extract year from PDF metadata dates."""
    for key in ["CreationDate", "ModDate"]:
        if key in metadata:
            date_str = metadata[key]
            # Format: D:20200501183358Z00'00'
            year_match = re.search(r"D:(\d{4})", date_str)
            if year_match:
                year = year_match.group(1)
                # Sanity check (reasonable year range)
                if 1990 <= int(year) <= 2025:
                    return year
    return None


def main():
    print("Finding Unknown author entries in references.md...")

    # Parse references.md
    unknown_entries = parse_references_file()
    print(f"Found {len(unknown_entries)} entries with Unknown authors\n")

    results = []

    # Process each unknown entry
    for i, entry in enumerate(unknown_entries, 1):
        filename = entry["filename"]
        filepath = REFERENCE_DIR / filename

        print(f"[{i}/{len(unknown_entries)}] Processing: {filename}")

        if not filepath.exists():
            print(f"  ⚠️  File not found!")
            entry["pdf_analysis"] = {"success": False, "error": "File not found"}
            results.append(entry)
            continue

        # Extract PDF metadata
        pdf_data = extract_pdf_metadata(filepath)
        entry["pdf_analysis"] = pdf_data

        if pdf_data["success"]:
            # Try to identify author
            metadata_author = pdf_data["metadata"].get("Author", "")
            identified_author = identify_author_from_text(
                pdf_data["first_page_preview"], entry["current_title"]
            )

            if metadata_author and metadata_author != entry.get("current_title", ""):
                print(f"  → PDF metadata author: {metadata_author}")
                entry["suggested_author"] = metadata_author
            elif identified_author:
                print(f"  → Identified from text: {identified_author}")
                entry["suggested_author"] = identified_author
            else:
                print(f"  → No author found")
                entry["suggested_author"] = None

            # Try to identify better title
            metadata_title = pdf_data["metadata"].get("Title", "")
            identified_title = identify_title_from_text(
                pdf_data["first_page_preview"], entry["current_title"]
            )

            if metadata_title and len(metadata_title) > 10:
                entry["suggested_title"] = metadata_title
            elif identified_title and len(identified_title) > len(
                entry.get("current_title", "")
            ):
                entry["suggested_title"] = identified_title
            else:
                entry["suggested_title"] = None

            # Try to extract better year
            if entry["current_year"] == "n.d.":
                extracted_year = extract_year_from_metadata(pdf_data["metadata"])
                if extracted_year:
                    print(f"  → Found year: {extracted_year}")
                    entry["suggested_year"] = extracted_year
                else:
                    entry["suggested_year"] = None
            else:
                entry["suggested_year"] = None

        results.append(entry)

    # Save results
    print(f"\nSaving results to {OUTPUT_JSON}")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Generate summary report
    markdown_dir = MARKDOWN_DIR
    markdown_dir.mkdir(exist_ok=True)

    report_file = markdown_dir / "unknown_authors_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# Unknown Authors Report\n\n")
        f.write(f"Found {len(results)} entries with Unknown authors.\n\n")
        f.write("---\n\n")

        # Categorize results
        with_author = [r for r in results if r.get("suggested_author")]
        with_title = [r for r in results if r.get("suggested_title")]
        with_year = [r for r in results if r.get("suggested_year")]
        with_any_suggestion = [
            r
            for r in results
            if r.get("suggested_author")
            or r.get("suggested_title")
            or r.get("suggested_year")
        ]
        no_suggestions = [
            r
            for r in results
            if not (
                r.get("suggested_author")
                or r.get("suggested_title")
                or r.get("suggested_year")
            )
            and r.get("pdf_analysis", {}).get("success")
        ]
        failed = [r for r in results if not r.get("pdf_analysis", {}).get("success")]

        f.write(f"## Summary\n\n")
        f.write(f"- **With ANY suggestions**: {len(with_any_suggestion)}\n")
        f.write(f"  - Suggested authors: {len(with_author)}\n")
        f.write(f"  - Suggested titles: {len(with_title)}\n")
        f.write(f"  - Suggested years: {len(with_year)}\n")
        f.write(f"- **No suggestions found**: {len(no_suggestions)}\n")
        f.write(f"- **Failed to process**: {len(failed)}\n\n")
        f.write("---\n\n")

        if with_any_suggestion:
            f.write("## Entries With Suggested Metadata\n\n")
            for entry in with_any_suggestion[:100]:  # First 100
                f.write(f"### {entry['filename']}\n\n")
                f.write(
                    f"**Current**: Unknown ({entry['current_year']}) *{entry['current_title']}*\n\n"
                )

                suggestions = []
                if entry.get("suggested_author"):
                    suggestions.append(
                        f"- **Suggested Author**: {entry['suggested_author']}"
                    )
                if entry.get("suggested_title"):
                    suggestions.append(
                        f"- **Suggested Title**: {entry['suggested_title']}"
                    )
                if entry.get("suggested_year"):
                    suggestions.append(
                        f"- **Suggested Year**: {entry['suggested_year']}"
                    )

                if suggestions:
                    f.write("\n".join(suggestions))
                    f.write("\n\n")

            if len(with_any_suggestion) > 100:
                f.write(
                    f"\n... and {len(with_any_suggestion) - 100} more (see JSON file)\n\n"
                )

        f.write("---\n\n")
        f.write(f"**Full results**: `{OUTPUT_JSON}`\n")

    print(f"\n✓ Report saved to: {report_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Unknown entries: {len(results)}")
    print(f"With ANY suggestions: {len(with_any_suggestion)}")
    print(f"  - Suggested authors: {len(with_author)}")
    print(f"  - Suggested titles: {len(with_title)}")
    print(f"  - Suggested years: {len(with_year)}")
    print(f"No suggestions found: {len(no_suggestions)}")
    print(f"Failed to process: {len(failed)}")
    print("\nNext steps:")
    print(f"1. Review {report_file}")
    print(f"2. Review and edit {OUTPUT_JSON}")
    print(f"3. Create update script to apply improvements to references.md")
    print("=" * 60)


if __name__ == "__main__":
    main()
