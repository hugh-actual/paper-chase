#!/usr/bin/env python3
"""
Update metadata-mismatch entries from metadata_mismatches.json:
- Clear a publisher that looks like PDF-producing software.
- Apply filename-derived author/title/year corrections.
- Rename files and update references.md; handle quarantine.
"""

import json

from src.lib.steps import UpdateStep


class UpdateMetadataMismatches(UpdateStep):
    """Update script for metadata mismatches from metadata_mismatches.json."""

    name = "metadata mismatches"
    input_filename = "metadata_mismatches.json"
    log_filename = "metadata_mismatches_update_log.md"
    log_title = "Metadata Mismatches Update Log"

    def load_entries(self) -> list[dict]:
        """Load metadata mismatch entries from metadata_mismatches.json."""
        with open(self.input_file, "r", encoding="utf-8") as f:
            entries = json.load(f)
        return entries


def main():
    """Main entry point."""
    return UpdateMetadataMismatches.run_as_main()


if __name__ == "__main__":
    exit(main())
