#!/usr/bin/env python3
"""
Show the current status of the paper-chase collection.

Displays:
- references.json statistics
- Detection JSON files and their status
- Annotated entries ready for update
- Recommendations for next actions
"""

import json
from datetime import datetime
from pathlib import Path

from src.lib import config
from src.lib.utils import load_references_json, flatten_files_from_pairs


def format_timestamp(filepath: Path) -> str:
    """Format file modification time as a readable string."""
    if not filepath.exists():
        return "never"
    mtime = filepath.stat().st_mtime
    dt = datetime.fromtimestamp(mtime)
    now = datetime.now()
    delta = now - dt

    if delta.days == 0:
        return "today"
    elif delta.days == 1:
        return "yesterday"
    elif delta.days < 7:
        return f"{delta.days} days ago"
    else:
        return dt.strftime("%Y-%m-%d")


def count_annotated_entries(entries: list[dict]) -> int:
    """Count entries with at least one non-null suggested_* field."""
    annotated = 0
    for entry in entries:
        if (
            entry.get("suggested_author") is not None
            or entry.get("suggested_title") is not None
            or entry.get("suggested_year") is not None
            or entry.get("quarantine") is True
        ):
            annotated += 1
    return annotated


def check_similar_pairs() -> dict:
    """Check status of similar_pairs.json."""
    filepath = config.JSON_OUTPUT_DIR / "similar_pairs.json"
    if not filepath.exists():
        return {"exists": False}

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    pairs = data.get("similar_pairs", [])
    files = flatten_files_from_pairs(pairs)

    total_files = len(files)
    annotated_files = count_annotated_entries(files)

    return {
        "exists": True,
        "timestamp": format_timestamp(filepath),
        "pairs": len(pairs),
        "total_files": total_files,
        "annotated_files": annotated_files,
    }


def check_unknown_authors() -> dict:
    """Check status of unknown_authors.json."""
    filepath = config.JSON_OUTPUT_DIR / "unknown_authors.json"
    if not filepath.exists():
        return {"exists": False}

    with open(filepath, "r", encoding="utf-8") as f:
        entries = json.load(f)

    annotated = count_annotated_entries(entries)

    return {
        "exists": True,
        "timestamp": format_timestamp(filepath),
        "total": len(entries),
        "annotated": annotated,
    }


def check_broken_titles() -> dict:
    """Check status of broken_titles.json."""
    filepath = config.JSON_OUTPUT_DIR / "broken_titles.json"
    if not filepath.exists():
        return {"exists": False}

    with open(filepath, "r", encoding="utf-8") as f:
        entries = json.load(f)

    annotated = count_annotated_entries(entries)

    return {
        "exists": True,
        "timestamp": format_timestamp(filepath),
        "total": len(entries),
        "annotated": annotated,
    }


def check_duplicate_candidates() -> dict:
    """Check status of duplicate_candidates.json."""
    filepath = config.JSON_OUTPUT_DIR / "duplicate_candidates.json"
    if not filepath.exists():
        return {"exists": False}

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    exact_duplicates = data.get("exact_duplicates", [])
    total_files = sum(len(group.get("files", [])) for group in exact_duplicates)

    # Count annotated files
    all_files = []
    for group in exact_duplicates:
        all_files.extend(group.get("files", []))
    annotated = count_annotated_entries(all_files)

    return {
        "exists": True,
        "timestamp": format_timestamp(filepath),
        "groups": len(exact_duplicates),
        "total_files": total_files,
        "annotated": annotated,
    }


def main():
    """Display collection status and recommendations."""
    print("=" * 70)
    print("PAPER-CHASE STATUS")
    print("=" * 70)

    # References.json status
    references = load_references_json()
    refs_timestamp = format_timestamp(config.REFERENCES_JSON)
    print(f"\n📚 Collection: {len(references)} entries")
    print(f"   Last modified: {refs_timestamp}")

    # Detection files status
    print("\n📊 Detection Results:")

    similar = check_similar_pairs()
    if similar["exists"]:
        print(f"\n   Similar Pairs ({similar['timestamp']}):")
        print(f"   - {similar['pairs']} pairs found")
        print(f"   - {similar['total_files']} files total")
        print(f"   - {similar['annotated_files']} files annotated")
    else:
        print("\n   Similar Pairs: not generated")

    unknown = check_unknown_authors()
    if unknown["exists"]:
        print(f"\n   Unknown Authors ({unknown['timestamp']}):")
        print(f"   - {unknown['total']} entries found")
        print(f"   - {unknown['annotated']} entries annotated")
    else:
        print("\n   Unknown Authors: not generated")

    broken = check_broken_titles()
    if broken["exists"]:
        print(f"\n   Broken Titles ({broken['timestamp']}):")
        print(f"   - {broken['total']} entries found")
        print(f"   - {broken['annotated']} entries annotated")
    else:
        print("\n   Broken Titles: not generated")

    duplicates = check_duplicate_candidates()
    if duplicates["exists"]:
        print(f"\n   Duplicate Candidates ({duplicates['timestamp']}):")
        print(f"   - {duplicates['groups']} groups found")
        print(f"   - {duplicates['total_files']} files total")
        print(f"   - {duplicates['annotated']} files annotated")
    else:
        print("\n   Duplicate Candidates: not generated")

    # Recommendations
    print("\n💡 Recommendations:")

    recommendations = []

    # Check for unannotated detection results
    if similar["exists"] and similar["total_files"] > 0:
        unannotated = similar["total_files"] - similar["annotated_files"]
        if unannotated > 0:
            recommendations.append(
                f"Annotate {unannotated} files in similar_pairs.json, "
                f"then run 'make update-similar'"
            )
        elif similar["annotated_files"] > 0:
            recommendations.append("Run 'make update-similar' to apply annotations")

    if unknown["exists"] and unknown["total"] > 0:
        unannotated = unknown["total"] - unknown["annotated"]
        if unannotated > 0:
            recommendations.append(
                f"Annotate {unannotated} entries in unknown_authors.json, "
                f"then run 'make update-unknown'"
            )
        elif unknown["annotated"] > 0:
            recommendations.append("Run 'make update-unknown' to apply annotations")

    if broken["exists"] and broken["total"] > 0:
        unannotated = broken["total"] - broken["annotated"]
        if unannotated > 0:
            recommendations.append(
                f"Annotate {unannotated} entries in broken_titles.json, "
                f"then run 'make update-broken'"
            )
        elif broken["annotated"] > 0:
            recommendations.append("Run 'make update-broken' to apply annotations")

    if duplicates["exists"] and duplicates["total_files"] > 0:
        unannotated = duplicates["total_files"] - duplicates["annotated"]
        if unannotated > 0:
            recommendations.append(
                f"Annotate {unannotated} files in duplicate_candidates.json, "
                f"then run 'make update-dups'"
            )
        elif duplicates["annotated"] > 0:
            recommendations.append("Run 'make update-dups' to apply annotations")

    # Check if no detection has been run
    if not any(
        [similar["exists"], unknown["exists"], broken["exists"], duplicates["exists"]]
    ):
        recommendations.append(
            "Run 'make detect-all' to find issues in your collection"
        )

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"\n   {i}. {rec}")
    else:
        print("\n   ✅ All detection results have been processed!")
        print("   Run 'make verify' to check collection consistency")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
