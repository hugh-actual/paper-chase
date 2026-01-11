#!/usr/bin/env python3
"""
Find truly broken, nonsensical, or out-of-place titles in references.md.
More selective criteria than the previous analysis.
"""

import re
import json
from pathlib import Path

# Import configuration from config.py
from src.lib.config import JSON_OUTPUT_DIR
from src.lib.utils import load_references_json

OUTPUT_JSON = JSON_OUTPUT_DIR / "broken_titles.json"


def is_broken_title(title, author, filename):
    """
    Determine if a title is truly broken/problematic.
    Returns (is_broken, reasons) tuple.
    """
    reasons = []

    # DEFINITELY BROKEN: Titles with underscores (improperly extracted metadata)
    if "_" in title and not title.startswith("9781"):  # Exclude ISBNs for now
        reasons.append("Contains underscores - likely extraction error")

    # DEFINITELY BROKEN: Generic placeholder titles
    generic_placeholders = [
        r"^My title$",
        r"^Untitled$",
        r"^untitled$",
        r"^Data Driven$",
        r"^Deep Learning$",
        r"^Machine Learning$",
    ]
    for pattern in generic_placeholders:
        if re.match(pattern, title):
            reasons.append("Generic placeholder title")
            break

    # DEFINITELY BROKEN: Titles that are ISBN codes
    if re.match(r"^978\d{10}", title):
        reasons.append("Title is an ISBN code")

    # DEFINITELY BROKEN: Titles in ALL CAPS (except acronyms)
    if title.isupper() and len(title) > 15 and " " in title:
        reasons.append("All CAPS - formatting error")

    # DEFINITELY BROKEN: Titles that look like file formats/extensions
    if re.search(r"\.(pdf|dvi|tex|indd)$", title.lower()):
        reasons.append("Contains file extension")

    # DEFINITELY BROKEN: Very short ambiguous titles
    very_short_ambiguous = [
        r"^IR_draft$",
        r"^SVMs$",
        r"^Dropout$",
        r"^backprop$",
        r"^Lecture \d+$",
        r"^nipstut\d+\.pdf$",
    ]
    for pattern in very_short_ambiguous:
        if re.match(pattern, title):
            reasons.append("Very short/broken title")
            break

    # DEFINITELY BROKEN: Publisher/software names as titles
    if re.match(r"^(PII:|DOI:)", title):
        reasons.append("PII/DOI code as title")

    # OUT OF PLACE: Cooking/food content
    if re.search(r"(cookbook|recipe|hero veg|celebration.*hero)", title, re.IGNORECASE):
        reasons.append("Cooking/food content - out of place")

    # OUT OF PLACE: Roman archaeology/history (very off-topic)
    if re.search(r"roman sacrifice", title, re.IGNORECASE):
        reasons.append("Roman archaeology - completely off-topic")

    # OUT OF PLACE: Music/warfare topics (unless acoustic analysis or military AI)
    if re.search(r"sonic warfare|music science", title, re.IGNORECASE):
        reasons.append("Music/sound topic - likely off-topic")

    # PROBABLY BROKEN: Metadata artifacts
    broken_metadata = [
        r"CITY UNIVERSITY$",
        r"Combined DVI Document",
        r"CIA Athens Document",
        r"Eriksson anomaly_$",
        r"The-Briefing-\d+-Print",
        r"Conference Proceedings Document$",
        r"Voice User Interface Document$",
    ]
    for pattern in broken_metadata:
        if re.search(pattern, title, re.IGNORECASE):
            reasons.append("Metadata artifact/placeholder")
            break

    # PROBABLY BROKEN: Line breaks in title (multiline extraction error)
    if "\n" in title:
        reasons.append("Title contains line break")

    # SUSPICIOUS: Medical/clinical topics (may or may not be relevant)
    if re.search(r"clinical|coronary|disease diagnosis|medical", title, re.IGNORECASE):
        # Only flag if it's clearly medical, not ML for medical
        if not re.search(
            r"machine learning|neural network|classification", title, re.IGNORECASE
        ):
            reasons.append("Medical/clinical topic - possibly off-topic")

    return reasons


def find_broken_titles():
    """Find and report broken titles."""
    entries = load_references_json()
    broken = []

    print(f"Analyzing {len(entries)} bibliography entries for broken titles...")
    print("=" * 70)

    for entry in entries:
        reasons = is_broken_title(entry["title"], entry["author"], entry["filename"])

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
