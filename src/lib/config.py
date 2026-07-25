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

# Get base paths from environment
DOCS_BASE_DIR = Path(os.getenv("DOCS_BASE_DIR", str(Path.home() / "Docs"))).expanduser()
PROCESSOR_DIR = Path(
    os.getenv("PROCESSOR_DIR", str(Path(__file__).resolve().parents[2]))
).expanduser()

# Data directories
REFERENCE_DIR = Path(
    os.getenv("REFERENCE_DIR", DOCS_BASE_DIR / "reference")
).expanduser()
QUARANTINE_DIR = Path(
    os.getenv("QUARANTINE_DIR", DOCS_BASE_DIR / "quarantine")
).expanduser()
TODO_DIR = Path(os.getenv("TODO_DIR", DOCS_BASE_DIR / "todo")).expanduser()
MARKDOWN_DIR = Path(os.getenv("MARKDOWN_DIR", DOCS_BASE_DIR / "markdown")).expanduser()

# Files
REFERENCES_FILE = Path(
    os.getenv("REFERENCES_FILE", DOCS_BASE_DIR / "references.md")
).expanduser()
REFERENCES_JSON = Path(
    os.getenv("REFERENCES_JSON", DOCS_BASE_DIR / "references.json")
).expanduser()

# JSON output
JSON_OUTPUT_DIR = Path(
    os.getenv("JSON_OUTPUT_DIR", PROCESSOR_DIR / "json-output")
).expanduser()

# Ensure directories exist
for _dir in (REFERENCE_DIR, QUARANTINE_DIR, TODO_DIR, MARKDOWN_DIR, JSON_OUTPUT_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
