#!/usr/bin/env python3
"""
Update broken title entries using curated metadata from broken_titles.json
- Replace title if suggested_title is not null
- Replace author if suggested_author is not null
- Rename files and update references.md
- Handle quarantine entries
"""

import json

from src.lib.steps import UpdateStep


class UpdateBrokenTitles(UpdateStep):
    """Update script for broken titles from broken_titles.json."""

    name = "broken titles"
    input_filename = "broken_titles.json"
    log_filename = "broken_titles_update_log.md"
    log_title = "Broken Titles Update Log"

    def load_entries(self) -> list[dict]:
        """Load broken title entries from broken_titles.json."""
        with open(self.input_file, "r", encoding="utf-8") as f:
            entries = json.load(f)
        return entries


def main():
    """Main entry point."""
    step = UpdateBrokenTitles()
    result = step.run()
    return 1 if result["fatal_errors"] else 0


if __name__ == "__main__":
    exit(main())
