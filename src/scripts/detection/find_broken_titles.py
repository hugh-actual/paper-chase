#!/usr/bin/env python3
"""
Find truly broken or nonsensical titles in references.md.

Only generic structural checks live here. Collection-specific patterns
(e.g. known-bad metadata artifacts or off-topic subjects) can be supplied
via an optional, untracked JSON file: json-output/local_title_patterns.json
"""

import re
import json

# Import configuration from config.py
from src.lib import config
from src.lib.utils import load_references_json

OUTPUT_JSON = config.JSON_OUTPUT_DIR / "broken_titles.json"
LOCAL_PATTERNS_JSON = config.JSON_OUTPUT_DIR / "local_title_patterns.json"


def load_local_patterns(path=LOCAL_PATTERNS_JSON):
    """
    Load optional collection-specific title patterns.

    The file is a JSON list of objects: {"pattern": <regex>, "reason": <text>}.
    Patterns are matched case-insensitively with re.search. Returns [] if the
    file does not exist. Invalid entries (missing keys, bad regex) are skipped
    with a warning rather than aborting the run.
    """
    if not path.exists():
        return []

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    patterns = []
    for item in raw:
        if not isinstance(item, dict) or "pattern" not in item or "reason" not in item:
            print(f"⚠ Skipping invalid local pattern entry: {item!r}")
            continue
        try:
            compiled = re.compile(item["pattern"], re.IGNORECASE)
        except re.error as e:
            print(f"⚠ Skipping unparseable local pattern {item['pattern']!r}: {e}")
            continue
        patterns.append({"regex": compiled, "reason": item["reason"]})
    return patterns


def is_broken_title(title, author, filename, local_patterns=None):
    """
    Determine if a title is truly broken/problematic.
    Returns a list of reasons (empty if the title looks fine).
    """
    reasons = []

    # DEFINITELY BROKEN: Titles with underscores (improperly extracted metadata)
    if "_" in title and not title.startswith("9781"):  # Exclude ISBNs for now
        reasons.append("Contains underscores - likely extraction error")

    # DEFINITELY BROKEN: Generic placeholder titles
    generic_placeholders = [
        r"^My title$",
        r"^untitled\b",
        r"^Data Driven$",
        r"^Deep Learning$",
        r"^Machine Learning$",
    ]
    for pattern in generic_placeholders:
        if re.match(pattern, title, re.IGNORECASE):
            reasons.append("Generic placeholder title")
            break

    # DEFINITELY BROKEN: Titles that are ISBN codes
    if re.match(r"^978\d{10}", title):
        reasons.append("Title is an ISBN code")

    # DEFINITELY BROKEN: Titles in ALL CAPS (except acronyms)
    if title.isupper() and len(title) > 15 and " " in title:
        reasons.append("All CAPS - formatting error")

    # DEFINITELY BROKEN: Titles that look like file formats/extensions
    if re.search(r"\.(pdf|dvi|tex|indd|docx?|pptx?)$", title.lower()):
        reasons.append("Contains file extension")

    # DEFINITELY BROKEN: Very short ambiguous titles
    very_short_ambiguous = [
        r"^Lecture \d+$",
        r"^Slide \d+$",
        r"^Chapter \d+$",
    ]
    for pattern in very_short_ambiguous:
        if re.match(pattern, title, re.IGNORECASE):
            reasons.append("Very short/broken title")
            break

    # DEFINITELY BROKEN: Publisher/software names as titles
    if re.match(r"^(PII:|DOI:)", title):
        reasons.append("PII/DOI code as title")

    # PROBABLY BROKEN: Metadata artifacts left by authoring tools.
    # Keep these generic (tool signatures, not subject matter) -- patterns
    # specific to one collection belong in local_title_patterns.json.
    broken_metadata = [
        r"^Microsoft Word - ",
        r"^Microsoft PowerPoint - ",
        r"Combined DVI Document",
        r"^Adobe (Acrobat|InDesign)",
        r"^print(job|out)?$",
    ]
    for pattern in broken_metadata:
        if re.search(pattern, title, re.IGNORECASE):
            reasons.append("Metadata artifact/placeholder")
            break

    # PROBABLY BROKEN: Line breaks in title (multiline extraction error)
    if "\n" in title:
        reasons.append("Title contains line break")

    # COLLECTION-SPECIFIC: optional local patterns (see load_local_patterns)
    for entry in local_patterns or []:
        if entry["regex"].search(title):
            reasons.append(entry["reason"])

    return reasons


def find_broken_titles():
    """Find and report broken titles."""
    entries = load_references_json()
    local_patterns = load_local_patterns()
    if local_patterns:
        print(f"Loaded {len(local_patterns)} local title pattern(s)")
    broken = []

    print(f"Analyzing {len(entries)} bibliography entries for broken titles...")
    print("=" * 70)

    for entry in entries:
        reasons = is_broken_title(
            entry["title"], entry["author"], entry["filename"], local_patterns
        )

        if reasons:
            broken_entry = {
                "author": entry["author"],
                "title": entry["title"],
                "filename": entry["filename"],
                "reasons": reasons,
            }
            broken.append(broken_entry)

            print(f"\n{entry['author']} ({entry['year']})")
            print(f"  Title: {entry['title']}")
            print(f"  File: {entry['filename']}")
            print(f"  Issues: {'; '.join(reasons)}")

    print("\n" + "=" * 70)
    print(f"Found {len(broken)} broken/problematic titles out of {len(entries)} total")

    # Save to JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(broken, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved to: {OUTPUT_JSON}")

    return broken


if __name__ == "__main__":
    find_broken_titles()
