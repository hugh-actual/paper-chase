#!/usr/bin/env python3
"""
Update Unknown author entries from manual review JSON.
Updates author, title, year, renames files, handles quarantine.
"""

from src.lib.steps import UpdateStep


class UpdateUnknownAuthors(UpdateStep):
    """Update script for unknown authors from unknown_authors.json."""

    name = "unknown authors"
    input_filename = "unknown_authors.json"
    log_filename = "unknown_authors_update_log.md"
    log_title = "Unknown Authors Update Log"
    detect_command = "find-unknown"

    def load_entries(self) -> list[dict]:
        """Load unknown author entries from unknown_authors.json."""
        return self._read_input_json() or []


def main():
    """Main entry point."""
    return UpdateUnknownAuthors.run_as_main()


if __name__ == "__main__":
    exit(main())
