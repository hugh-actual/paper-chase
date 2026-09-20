#!/usr/bin/env python3
"""
Update broken title entries using curated metadata from broken_titles.json
- Replace title if suggested_title is not null
- Replace author if suggested_author is not null
- Rename files and update references.md
- Handle quarantine entries
"""

from src.lib.steps import UpdateStep


class UpdateBrokenTitles(UpdateStep):
    """Update script for broken titles from broken_titles.json."""

    name = "broken titles"
    input_filename = "broken_titles.json"
    log_filename = "broken_titles_update_log.md"
    log_title = "Broken Titles Update Log"
    detect_command = "find-broken"

    def load_entries(self) -> list[dict]:
        """Load broken title entries from broken_titles.json."""
        return self._read_input_json() or []


def main():
    """Main entry point."""
    return UpdateBrokenTitles.run_as_main()


if __name__ == "__main__":
    exit(main())
