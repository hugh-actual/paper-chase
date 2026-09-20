#!/usr/bin/env python3
"""
Update metadata-mismatch entries from metadata_mismatches.json:
- Clear a publisher that looks like PDF-producing software.
- Apply filename-derived author/title/year corrections.
- Rename files and update references.md; handle quarantine.
"""

from src.lib.steps import UpdateStep


class UpdateMetadataMismatches(UpdateStep):
    """Update script for metadata mismatches from metadata_mismatches.json."""

    name = "metadata mismatches"
    input_filename = "metadata_mismatches.json"
    log_filename = "metadata_mismatches_update_log.md"
    log_title = "Metadata Mismatches Update Log"
    detect_command = "find-mismatches"

    def load_entries(self) -> list[dict]:
        """Load metadata mismatch entries from metadata_mismatches.json."""
        return self._read_input_json() or []


def main():
    """Main entry point."""
    return UpdateMetadataMismatches.run_as_main()


if __name__ == "__main__":
    exit(main())
