#!/usr/bin/env python3
"""Verify files match bibliography entries and identify suspect filenames"""

# Import configuration from config.py
from src.lib import config
from src.lib.utils import (
    calculate_file_hash,
    explain_missing_file,
    explain_orphan,
    is_suspect_filename,
    latest_history_event,
    load_history,
    load_references_json,
)


def _verify() -> int:
    """Run verification and return discrepancy count."""
    # Get all PDF files
    pdf_files = set(f.name for f in config.REFERENCE_DIR.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in reference folder")

    # Load references from JSON
    entries = load_references_json()
    referenced_files = set(e["filename"] for e in entries)

    print(f"Found {len(referenced_files)} files referenced in bibliography")

    # Find discrepancies
    files_not_in_bib = pdf_files - referenced_files
    bib_not_in_files = referenced_files - pdf_files

    # Find suspect filenames
    suspect_files = []
    for filename in sorted(pdf_files):
        if is_suspect_filename(filename):
            suspect_files.append(filename)

    # Write bad_metadata.md
    with open(config.MARKDOWN_DIR / "bad_metadata.md", "w", encoding="utf-8") as f:
        f.write("# Files with Suspect Metadata\n\n")
        f.write(
            "These files appear to have bad or missing metadata based on their filenames.\n"
        )
        f.write("They may need manual review and renaming.\n\n")
        f.write(f"**Total suspect files**: {len(suspect_files)}\n\n")
        f.write("---\n\n")

        if suspect_files:
            f.write("## Files to Review\n\n")
            for i, filename in enumerate(suspect_files, 1):
                f.write(f"{i}. `{filename}`\n")
        else:
            f.write("No suspect files found.\n")

    # Write verification report
    print("\n" + "=" * 60)
    print("VERIFICATION REPORT")
    print("=" * 60)

    # The history journal usually knows what an orphan was called before
    # ingest renamed it, or where a missing file was moved to -- and
    # `make recover` can then fix references.json.
    history = load_history() if (files_not_in_bib or bib_not_in_files) else []
    explained = 0

    if files_not_in_bib:
        print(
            f"\n⚠️  FILES IN FOLDER BUT NOT IN BIBLIOGRAPHY ({len(files_not_in_bib)}):"
        )
        for f in sorted(files_not_in_bib):
            file_hash = calculate_file_hash(config.REFERENCE_DIR / f)
            event = explain_orphan(history, f, file_hash)
            if event:
                explained += 1
                # A rename event may not carry the original name; the
                # ingest for the same hash does.
                ingest = latest_history_event(history, ("ingest",), file_hash=file_hash)
                origin = event.get("original_filename") or (
                    (ingest or {}).get("original_filename") or "unknown"
                )
                print(f"  - {f}  (originally: {origin})")
            else:
                print(f"  - {f}")
    else:
        print("\n✓ All files in folder are in bibliography")

    if bib_not_in_files:
        print(
            f"\n⚠️  FILES IN BIBLIOGRAPHY BUT NOT IN FOLDER ({len(bib_not_in_files)}):"
        )
        by_name = {e["filename"]: e for e in entries}
        for f in sorted(bib_not_in_files):
            kind, event = explain_missing_file(history, by_name[f])
            if kind == "renamed":
                explained += 1
                print(f"  - {f}  (renamed to: {event['filename']})")
            elif kind == "quarantined":
                explained += 1
                print(f"  - {f}  (quarantined as: {event['quarantine_filename']})")
            else:
                print(f"  - {f}")
    else:
        print("\n✓ All bibliography entries have corresponding files")

    if explained:
        print(
            f"\n→ History explains {explained} of these: run 'make recover' to "
            "preview the fixes, 'make recover APPLY=1' to apply them"
        )

    if suspect_files:
        print(f"\n⚠️  SUSPECT FILENAMES FOUND ({len(suspect_files)}):")
        for f in suspect_files[:10]:  # Show first 10
            print(f"  - {f}")
        if len(suspect_files) > 10:
            print(f"  ... and {len(suspect_files) - 10} more (see bad_metadata.md)")
    else:
        print("\n✓ No suspect filenames found")

    print("\n" + "=" * 60)
    report_path = config.MARKDOWN_DIR / "bad_metadata.md"
    print(f"✓ Created {report_path} with {len(suspect_files)} suspect files")
    print("=" * 60)

    return len(files_not_in_bib) + len(bib_not_in_files)


def main() -> int:
    """Entry point: return 0 if no discrepancies, 1 if any found."""
    discrepancy_count = _verify()
    return 1 if discrepancy_count else 0


if __name__ == "__main__":
    exit(main())
