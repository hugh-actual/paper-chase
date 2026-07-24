#!/usr/bin/env python3
"""
Update similar pairs from similar_pairs.json.
Processes files with quarantine flags or suggested metadata updates.
Handles file1, file2, and any additional fileN entries.
"""

import json

from src.lib.steps import UpdateStep
from src.lib.utils import flatten_files_from_pairs


class UpdateSimilarPairs(UpdateStep):
    """Update script for similar pairs from similar_pairs.json."""

    name = "similar pairs"
    input_filename = "similar_pairs.json"
    log_filename = "similar_pairs_update_log.md"
    log_title = "Similar Pairs Update Log"

    def load_entries(self) -> list[dict]:
        """Load and flatten similar pair entries from similar_pairs.json."""
        with open(self.input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        similar_pairs = data.get("similar_pairs", [])
        return flatten_files_from_pairs(similar_pairs)


def main():
    """Main entry point."""
    step = UpdateSimilarPairs()
    step.run()


if __name__ == "__main__":
    main()
