#!/usr/bin/env python3
"""
Find references.json entries whose stored metadata looks wrong:

- `publisher` that is actually PDF-producing software (an embedded
  `/Producer` string like "pdfTeX-1.40.21" or "Adobe Acrobat Pro DC")
  rather than a real publisher.
- `original_filename` that parses, via a structured
  `DocumentProcessor.extract_from_filename` pattern, into an
  author/title/year that disagrees with what's stored -- typically
  because embedded PDF metadata (scanner junk, an unsaved Word default)
  won the field at ingest time before T7's precedence fix.

Writes json-output/metadata_mismatches.json for manual review, consumed
by update-mismatches. Read-only: never touches references.json or any
file on disk.
"""

import json

from src.lib import config
from src.lib.utils import (
    _atomic_write_text,
    add_annotation_fields,
    is_junk_metadata,
    is_unknown_author,
    load_references_json,
    looks_like_pdf_software,
    normalize_text,
    parse_author,
)
from src.scripts.core.process_documents import DocumentProcessor


def _norm(value):
    """NFC-normalise, casefold and collapse whitespace, so two spellings
    of the same value (extra spaces, case) don't register as a mismatch."""
    return " ".join(normalize_text(value or "").casefold().split())


def _author_mismatch(stored_author, filename_author):
    """Compare on the filename-surname form (parse_author's first return
    value) so a full stored name ("Jane Smith") isn't flagged against a
    filename surname ("Smith")."""
    return _norm(parse_author(stored_author)[0]) != _norm(
        parse_author(filename_author)[0]
    )


def find_filename_mismatches(entry, filename_info):
    """Compare a structured filename parse against the stored entry.

    Returns (reasons, suggestions) for the fields that differ. Only
    fields the filename actually provides are compared -- a pattern with
    no year, for instance, suggests nothing for year.

    Author/title are pre-filled into suggested_* only when the *stored*
    value is junk (is_junk_metadata / is_unknown_author). A merely
    different but otherwise fine stored value is still reported, but the
    filename's value goes in an informational filename_author/
    filename_title field instead -- a structured-but-lazy filename (e.g.
    "[Smith]paper_final_v2.pdf") must not silently overwrite a good
    title if these suggestions are bulk-applied. Year has no such risk:
    a stored year mismatch predates T7's fix and came from /CreationDate
    (the scan date), so the filename year is the more reliable one and
    is always pre-filled when it differs.
    """
    reasons = []
    suggestions = {}

    filename_author = filename_info.get("author")
    if filename_author and _author_mismatch(entry.get("author", ""), filename_author):
        reasons.append("original filename suggests a different author")
        stored_author = entry.get("author", "")
        if is_unknown_author(stored_author) or is_junk_metadata(
            "author", stored_author
        ):
            suggestions["suggested_author"] = filename_author
        else:
            suggestions["filename_author"] = filename_author

    filename_title = filename_info.get("title")
    if filename_title and _norm(entry.get("title", "")) != _norm(filename_title):
        reasons.append("original filename suggests a different title")
        if is_junk_metadata("title", entry.get("title", "")):
            suggestions["suggested_title"] = filename_title
        else:
            suggestions["filename_title"] = filename_title

    filename_year = filename_info.get("year")
    if filename_year and _norm(entry.get("year", "")) != _norm(filename_year):
        reasons.append("original filename suggests a different year")
        suggestions["suggested_year"] = filename_year

    return reasons, suggestions


def find_metadata_mismatches():
    """Find and report metadata mismatches. Returns the list written."""
    entries = load_references_json()
    processor = DocumentProcessor()

    print(f"Analyzing {len(entries)} bibliography entries for metadata mismatches...")
    print("=" * 70)

    results = []
    for entry in entries:
        reasons = []
        suggestions = {}

        publisher = entry.get("publisher", "")
        if looks_like_pdf_software(publisher):
            reasons.append("publisher looks like PDF-generating software")
            suggestions["suggested_publisher"] = ""

        original_filename = entry.get("original_filename")
        if original_filename:
            filename_info = processor.extract_from_filename(original_filename)
            if filename_info.get("structured"):
                file_reasons, file_suggestions = find_filename_mismatches(
                    entry, filename_info
                )
                reasons.extend(file_reasons)
                suggestions.update(file_suggestions)

        if not reasons:
            continue

        result = {
            "filename": entry["filename"],
            "author": entry.get("author", ""),
            "title": entry.get("title", ""),
            "year": entry.get("year", ""),
            "publisher": entry.get("publisher", ""),
            "original_filename": original_filename or "",
            "reasons": reasons,
        }
        add_annotation_fields([result])
        result.update(suggestions)
        results.append(result)

        print(f"\n{result['filename']}")
        print(f"  Issues: {'; '.join(reasons)}")

    print("\n" + "=" * 70)
    print(
        f"Found {len(results)} entries with metadata mismatches "
        f"out of {len(entries)} total"
    )

    # Read as config.<NAME> at call time (not a module-level constant), so
    # tests that redirect config.JSON_OUTPUT_DIR per-run see it take effect.
    output_json = config.JSON_OUTPUT_DIR / "metadata_mismatches.json"
    _atomic_write_text(output_json, json.dumps(results, indent=2, ensure_ascii=False))

    print(f"✓ Saved to: {output_json}")

    return results


if __name__ == "__main__":
    find_metadata_mismatches()
