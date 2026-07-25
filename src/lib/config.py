#!/usr/bin/env python3
"""
Configuration loader from .env file.
Loads paths from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()


def _env_path(name: str, default) -> Path:
    """Read a path from the environment, expanding a leading `~`.

    dotenv interpolates `${DOCS_BASE_DIR}/reference` into a literal string
    before Path() ever sees it, so the derived vars arrive already carrying
    whatever `~` the base var held -- every var needs expanding, not just
    the two base ones. Without this, copying .env.example verbatim creates
    a literal `~` directory in the working directory, silently, because of
    the mkdir loop below.
    """
    return Path(os.getenv(name, str(default))).expanduser()


# Get base paths from environment
DOCS_BASE_DIR = _env_path("DOCS_BASE_DIR", Path.home() / "Docs")
PROCESSOR_DIR = _env_path("PROCESSOR_DIR", Path(__file__).resolve().parents[2])

# Data directories
REFERENCE_DIR = _env_path("REFERENCE_DIR", DOCS_BASE_DIR / "reference")
QUARANTINE_DIR = _env_path("QUARANTINE_DIR", DOCS_BASE_DIR / "quarantine")
TODO_DIR = _env_path("TODO_DIR", DOCS_BASE_DIR / "todo")
MARKDOWN_DIR = _env_path("MARKDOWN_DIR", DOCS_BASE_DIR / "markdown")

# Files
REFERENCES_FILE = _env_path("REFERENCES_FILE", DOCS_BASE_DIR / "references.md")
REFERENCES_JSON = _env_path("REFERENCES_JSON", DOCS_BASE_DIR / "references.json")

# JSON output
JSON_OUTPUT_DIR = _env_path("JSON_OUTPUT_DIR", PROCESSOR_DIR / "json-output")

# Ensure directories exist
for _dir in (REFERENCE_DIR, QUARANTINE_DIR, TODO_DIR, MARKDOWN_DIR, JSON_OUTPUT_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
