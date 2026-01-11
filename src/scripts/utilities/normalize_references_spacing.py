#!/usr/bin/env python3
"""
Normalize spacing in references.md to ensure exactly one blank line between entries.
"""

from pathlib import Path

# Import configuration from config.py
from src.lib.config import REFERENCES_FILE


def normalize_spacing():
    """Ensure exactly one blank line between bibliography entries."""
    with open(REFERENCES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    normalized = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Add the current line
        normalized.append(line)

        # If this is a **File**: line, ensure exactly one blank line follows
        if line.strip().startswith("**File**:"):
            i += 1

            # Skip any existing blank lines
            while i < len(lines) and not lines[i].strip():
                i += 1

            # Add exactly one blank line (unless we're at the end)
            if i < len(lines):
                normalized.append("\n")

            continue

        i += 1

    # Write back
    with open(REFERENCES_FILE, "w", encoding="utf-8") as f:
        f.writelines(normalized)

    print("✓ Normalized spacing in references.md")
    print("  Each entry now has exactly one blank line separator")


if __name__ == "__main__":
    normalize_spacing()
