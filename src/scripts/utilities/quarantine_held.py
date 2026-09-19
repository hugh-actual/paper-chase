#!/usr/bin/env python3
"""
Move held duplicates out of todo/ into quarantine/.

`make ingest` keeps a byte-identical duplicate of an existing file in
todo/ and lists it in json-output/ingestion_conflicts.json. This clears
them -- but only after re-checking, at the time of the move, that each
really is a duplicate:

- it is a `hash_duplicate` conflict and the file is still in todo/;
- the existing copy it duplicates is present in reference/;
- both files hash identically *now*.

Anything else is left where it is. Files are moved, never deleted, and
never overwrite a same-named file in quarantine/ (a suffix is added).
Each move is journalled (`quarantine_held`) before it happens.

Dry run by default; `--apply` (`make quarantine-held APPLY=1`) moves.
"""

import argparse
import json
import shutil

from src.lib import config
from src.lib.steps import StepError
from src.lib.utils import append_history, calculate_file_hash, check_duplicate_filename

REPORT_FILENAME = "ingestion_conflicts.json"


def load_held_duplicates() -> list[tuple[str, str]]:
    """(todo filename, existing reference filename) for every held
    `hash_duplicate` in the last ingest's conflict report."""
    report_file = config.JSON_OUTPUT_DIR / REPORT_FILENAME
    if not report_file.exists():
        return []
    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    held = []
    for item in report.get("conflicts", []):
        for conflict in item.get("conflicts", []):
            if conflict.get("type") == "hash_duplicate":
                held.append((item["original_filename"], conflict["existing_filename"]))
                break
    return held


def run(apply: bool = False) -> int:
    """Check (and with apply, move) every held duplicate. Returns an exit
    code: 1 only on a genuine failure (a hash read or move that raised)."""
    held = load_held_duplicates()
    errors: list[StepError] = []
    moved = []

    print("=" * 70)
    print("QUARANTINE HELD DUPLICATES" + ("" if apply else " (dry run)"))
    print("=" * 70)

    if not held:
        print("No held duplicates in the last ingest's conflict report.")

    for todo_name, existing_name in held:
        todo_path = config.TODO_DIR / todo_name
        existing_path = config.REFERENCE_DIR / existing_name

        # Refusals are routine (the situation changed since ingest); they
        # leave the file in todo/ and don't fail the run.
        if not todo_path.exists():
            errors.append(StepError("check", todo_name, "No longer in todo/", False))
            continue
        if not existing_path.exists():
            errors.append(
                StepError(
                    "check",
                    todo_name,
                    f"Existing copy {existing_name} is missing -- kept; "
                    "run 'make ingest' to restore it from this file",
                    False,
                )
            )
            continue

        todo_hash = calculate_file_hash(todo_path)
        existing_hash = calculate_file_hash(existing_path)
        if todo_hash is None or existing_hash is None:
            errors.append(StepError("check", todo_name, "Could not read file", True))
            continue
        if todo_hash != existing_hash:
            errors.append(
                StepError(
                    "check",
                    todo_name,
                    f"Content differs from {existing_name} -- not a duplicate, kept",
                    False,
                )
            )
            continue

        dest_name = check_duplicate_filename(todo_name, set(), config.QUARANTINE_DIR)
        if not apply:
            print(f"  would move: todo/{todo_name} → quarantine/{dest_name}")
            moved.append(todo_name)
            continue

        try:
            append_history(
                "quarantine_held",
                original_filename=todo_name,
                quarantine_filename=dest_name,
                file_hash=todo_hash,
                existing_filename=existing_name,
            )
            shutil.move(str(todo_path), str(config.QUARANTINE_DIR / dest_name))
        except Exception as e:
            errors.append(StepError("move", todo_name, str(e), True))
            continue
        print(f"  moved: todo/{todo_name} → quarantine/{dest_name}")
        moved.append(todo_name)

    fatal = [e for e in errors if e.fatal]
    skipped = [e for e in errors if not e.fatal]
    for label, group in (("Failures", fatal), ("Kept in todo/", skipped)):
        if group:
            print(f"\n{label}:")
            for err in group:
                print(f"  - [{err.phase}/{err.filename}] {err.message}")

    print()
    if not apply and moved:
        print(f"Dry run: {len(moved)} file(s) would move. Run with APPLY=1 to move.")
    elif apply and moved:
        print(f"Moved {len(moved)} file(s). Run 'make ingest' to refresh the report.")
    if fatal:
        print(f"✗ {len(fatal)} genuine failure(s) -- this run did not fully apply.")
        return 1
    print("✓ Completed with no failures.")
    return 0


def main(argv=None) -> int:
    """Entry point: 0 on success (including a dry run), 1 on failure."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="move the files (default: dry run)"
    )
    args = parser.parse_args(argv)
    return run(apply=args.apply)


if __name__ == "__main__":
    exit(main())
