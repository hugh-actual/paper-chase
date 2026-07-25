#!/usr/bin/env python3
"""
Update Unknown author entries from manual review JSON.
Updates author, title, year, renames files, handles quarantine.
"""

import json

from src.lib.steps import UpdateStep


class UpdateUnknownAuthors(UpdateStep):
    """Update script for unknown authors from unknown_authors.json."""

    name = "unknown authors"
    input_filename = "unknown_authors.json"
    log_filename = "unknown_authors_update_log.md"
    log_title = "Unknown Authors Update Log"

    def load_entries(self) -> list[dict]:
        """Load unknown author entries from unknown_authors.json."""
        with open(self.input_file, "r", encoding="utf-8") as f:
            entries = json.load(f)
        return entries


def main():
    """Main entry point."""
    step = UpdateUnknownAuthors()
    result = step.run()
    return 1 if result["fatal_errors"] else 0


if __name__ == "__main__":
    exit(main())
