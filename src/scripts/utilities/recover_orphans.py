#!/usr/bin/env python3
"""
Rebuild references.json entries from the history journal.

An interrupted run can leave references.json out of step with reference/:

- Orphan files: a PDF in reference/ with no entry (moved or renamed, but
  the run died before references.json was saved). The latest `ingest`,
  `rename` or `relink` event whose target filename AND hash match the file
  on disk holds everything needed to rebuild its entry.
- Missing files: an entry whose file isn't in reference/ because a later
  `rename` moved it (the entry is pointed at the new name) or a
  `quarantine` moved it out (the entry is dropped).

Dry run by default; `--apply` (`make recover APPLY=1`) writes
references.json and regenerates references.md. Never moves files.
"""

import argparse

from src.lib import config
from src.lib.utils import (
    build_reference_entry,
    calculate_file_hash,
    latest_history_event,
    load_history,
    load_references_json,
    regenerate_references_md,
    save_references_json,
)

# Events whose `filename` is where the file ended up in reference/
PLACING_EVENTS = ("ingest", "rename", "relink")
METADATA_FIELDS = ("author", "year", "title", "publisher", "original_filename")

# Guard against a (malformed) rename cycle when following a chain
MAX_RENAME_HOPS = 50


def _metadata_for(history, event):
    """Metadata for the file `event` placed, folded over every earlier event
    for the same hash -- so a `rename` that only records the fields it
    changed still inherits the rest (e.g. original_filename) from the
    `ingest` before it."""
    fields = {}
    for record in history:
        if record.get("file_hash") == event["file_hash"] and (
            record.get("event") in PLACING_EVENTS
        ):
            fields.update({k: record[k] for k in METADATA_FIELDS if k in record})
        if record is event:
            break
    return fields


def _rebuild_entry(history, event):
    fields = _metadata_for(history, event)
    return build_reference_entry(
        fields.get("author", ""),
        fields.get("year"),
        fields.get("title", ""),
        fields.get("publisher"),
        event["filename"],
        original_filename=fields.get("original_filename"),
        file_hash=event["file_hash"],
    )


def explain_orphan(history, filename, file_hash):
    """The latest event that placed `filename` with this hash, or None."""
    if not file_hash:
        return None
    return latest_history_event(
        history, PLACING_EVENTS, filename=filename, file_hash=file_hash
    )


def _trace_missing(history, entry):
    """Explain where a missing entry's file went.

    Returns ("renamed", event) for the rename chain's last hop whose target
    exists on disk with the recorded hash, ("quarantined", event) when a
    quarantine event moved it out and the quarantined file exists, or
    (None, None) when history doesn't explain it.
    """
    filename = entry["filename"]
    file_hash = entry.get("file_hash")
    renamed = None

    for _ in range(MAX_RENAME_HOPS):
        match = {"filename": filename}
        if file_hash:
            match["file_hash"] = file_hash
        quarantine = latest_history_event(history, ("quarantine",), **match)
        if quarantine and quarantine.get("quarantine_filename"):
            if (config.QUARANTINE_DIR / quarantine["quarantine_filename"]).exists():
                return "quarantined", quarantine

        match = {"old_filename": filename}
        if file_hash:
            match["file_hash"] = file_hash
        rename = latest_history_event(history, ("rename",), **match)
        if not rename or not rename.get("file_hash"):
            break
        file_hash = rename["file_hash"]
        filename = rename["filename"]
        target = config.REFERENCE_DIR / filename
        if target.exists() and calculate_file_hash(target) == file_hash:
            renamed = rename
            # Keep following: the file may have been renamed again

    return ("renamed", renamed) if renamed else (None, None)


def plan_recovery(references, history):
    """Work out the fixes without touching anything.

    Returns a dict with:
      restored   -- entries rebuilt for orphan files in reference/
      renamed    -- (old entry, fixed entry) for entries a rename explains
      dropped    -- entries whose file a quarantine moved out
      unresolved -- orphan filenames history can't explain
      missing    -- entry filenames history can't explain
    """
    result = {
        "restored": [],
        "renamed": [],
        "dropped": [],
        "unresolved": [],
        "missing": [],
    }
    on_disk = {f.name for f in config.REFERENCE_DIR.glob("*.pdf")}

    # Missing files first: a rename fix claims its target filename, so the
    # forward pass below won't also rebuild that file as a new entry.
    claimed = set()
    for entry in references:
        if entry["filename"] in on_disk:
            continue
        kind, event = _trace_missing(history, entry)
        if kind == "renamed":
            fixed = dict(entry)
            fixed["filename"] = event["filename"]
            fixed["file_hash"] = event["file_hash"]
            # Take metadata history records for this file (a rename may
            # have changed it); keep the entry's own value for the rest.
            recorded = _metadata_for(history, event)
            rebuilt = _rebuild_entry(history, event)
            for key in ("author", "year", "title", "publisher"):
                if key in recorded:
                    fixed[key] = rebuilt[key]
            result["renamed"].append((entry, fixed))
            claimed.add(fixed["filename"])
        elif kind == "quarantined":
            result["dropped"].append(entry)
        else:
            result["missing"].append(entry["filename"])

    referenced = {e["filename"] for e in references} | claimed
    for name in sorted(on_disk - referenced):
        event = explain_orphan(
            history, name, calculate_file_hash(config.REFERENCE_DIR / name)
        )
        if event:
            result["restored"].append(_rebuild_entry(history, event))
        else:
            result["unresolved"].append(name)

    return result


def apply_recovery(references, plan):
    """Return the references list with `plan` applied."""
    dropped = {id(e) for e in plan["dropped"]}
    fixes = {id(old): new for old, new in plan["renamed"]}
    updated = [fixes.get(id(e), e) for e in references if id(e) not in dropped]
    return updated + plan["restored"]


def run(apply: bool = False) -> int:
    """Plan (and with apply, write) the recovery. Returns an exit code:
    1 only on a genuine failure writing the result."""
    references = load_references_json()
    history = load_history()
    plan = plan_recovery(references, history)

    print("=" * 70)
    print("RECOVER FROM HISTORY" + ("" if apply else " (dry run)"))
    print("=" * 70)

    for entry in plan["restored"]:
        origin = entry.get("original_filename") or "unknown original"
        print(f"  + restore entry: {entry['filename']}  (originally: {origin})")
    for old, new in plan["renamed"]:
        print(f"  ~ renamed on disk: {old['filename']} → {new['filename']}")
    for entry in plan["dropped"]:
        print(f"  - quarantined, dropping entry: {entry['filename']}")
    for name in plan["unresolved"]:
        print(f"  ? no history for file: {name}")
    for name in plan["missing"]:
        print(f"  ? no history for missing file: {name}")

    changes = len(plan["restored"]) + len(plan["renamed"]) + len(plan["dropped"])
    print(
        f"\n{changes} fix(es), {len(plan['unresolved'])} unexplained file(s), "
        f"{len(plan['missing'])} unexplained missing file(s)"
    )

    if not changes:
        print("✓ Nothing to recover.")
        return 0
    if not apply:
        print("Dry run: nothing written. Run 'make recover APPLY=1' to apply.")
        return 0

    try:
        save_references_json(apply_recovery(references, plan))
    except Exception as e:
        print(f"✗ Failed to save references.json: {e}")
        return 1
    if not regenerate_references_md():
        print("✗ references.json saved, but references.md failed to regenerate.")
        return 1
    print(f"✓ Applied {changes} fix(es) to references.json.")
    return 0


def main(argv=None) -> int:
    """Entry point: 0 on success (including a dry run), 1 on failure."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="write references.json (default: dry run)"
    )
    args = parser.parse_args(argv)
    return run(apply=args.apply)


if __name__ == "__main__":
    exit(main())
