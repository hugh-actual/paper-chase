#!/usr/bin/env python3
"""Verify files match bibliography entries and identify suspect filenames"""

# Import configuration from config.py
from src.lib.config import REFERENCE_DIR, MARKDOWN_DIR
from src.lib.utils import load_references_json, is_suspect_filename


def main():
    # Get all PDF files
    pdf_files = set(f.name for f in REFERENCE_DIR.glob("*.pdf"))
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
    with open(MARKDOWN_DIR / "bad_metadata.md", "w", encoding="utf-8") as f:
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

    if files_not_in_bib:
        print(
            f"\n⚠️  FILES IN FOLDER BUT NOT IN BIBLIOGRAPHY ({len(files_not_in_bib)}):"
        )
        for f in sorted(files_not_in_bib):
            print(f"  - {f}")
    else:
        print("\n✓ All files in folder are in bibliography")

    if bib_not_in_files:
        print(
            f"\n⚠️  FILES IN BIBLIOGRAPHY BUT NOT IN FOLDER ({len(bib_not_in_files)}):"
        )
        for f in sorted(bib_not_in_files):
            print(f"  - {f}")
    else:
        print("\n✓ All bibliography entries have corresponding files")

    if suspect_files:
        print(f"\n⚠️  SUSPECT FILENAMES FOUND ({len(suspect_files)}):")
        for f in suspect_files[:10]:  # Show first 10
            print(f"  - {f}")
        if len(suspect_files) > 10:
            print(f"  ... and {len(suspect_files) - 10} more (see bad_metadata.md)")
    else:
        print("\n✓ No suspect filenames found")

    print("\n" + "=" * 60)
    print(
        f"✓ Created {MARKDOWN_DIR / 'bad_metadata.md'} with {len(suspect_files)} suspect files"
    )
    print("=" * 60)

    return len(files_not_in_bib) + len(bib_not_in_files)


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
