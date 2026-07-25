#!/usr/bin/env python3
"""
Update exact duplicate entries from duplicate_candidates.json.
Processes files with quarantine flags or suggested metadata updates.
"""

import json

from src.lib.steps import UpdateStep


class UpdateExactDuplicates(UpdateStep):
    """Update script for exact duplicates from duplicate_candidates.json."""

    name = "exact duplicates"
    input_filename = "duplicate_candidates.json"
    log_filename = "exact_duplicates_update_log.md"
    log_title = "Exact Duplicates Update Log"

    def load_entries(self) -> list[dict]:
        """Load and flatten exact duplicate entries from duplicate_candidates.json."""
        with open(self.input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        exact_duplicates = data.get("exact_duplicates", [])

        # Flatten all files from all groups
        all_files = []
        for group in exact_duplicates:
            for file_entry in group.get("files", []):
                all_files.append(file_entry)

        return all_files


def main():
    """Main entry point."""
    return UpdateExactDuplicates.run_as_main()


if __name__ == "__main__":
    exit(main())
