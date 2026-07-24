#!/usr/bin/env python3
"""
Shared utilities for document processing.
Contains common functions for parsing authors, sanitizing titles,
managing references.md, and file operations.
"""

import hashlib
import re
import json
import shutil
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

# Configuration is accessed as config.<NAME> (not from-imported) so that
# tests can redirect paths by patching src.lib.config alone.
from . import config

# =============================================================================
# Constants for title/author processing
# =============================================================================

PREPOSITIONS = {
    "a",
    "an",
    "the",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "from",
    "by",
    "and",
    "or",
    "but",
    "nor",
}

DOMAIN_ADJECTIVES = {
    "deep",
    "applied",
    "statistical",
    "neural",
    "bayesian",
    "machine",
    "artificial",
    "computational",
    "numerical",
    "data",
    "quantum",
}

# =============================================================================
# Author parsing
# =============================================================================


def parse_author(author_str):
    """
    Parse author string and return (formatted_name_for_filename, list_of_full_names).

    Examples:
        "John Smith" -> ("Smith", ["John Smith"])
        "Smith and Jones" -> ("Smith_Jones", ["Smith", "Jones"])
        "Smith, Jones, and Brown" -> ("Smith_et_al", ["Smith", "Jones", "Brown"])
    """
    if not author_str or author_str == "Unknown":
        return "Unknown", ["Unknown"]

    author_str = author_str.strip()

    # Remove invalid filename characters (but keep for bibliography)
    author_str_clean = re.sub(r'[/\\<>:"|?*]', " ", author_str)

    # Split on any author separator: ", and " / ", " / "; " / " and " / " & "
    # (longer patterns first so ", and " is not split twice)
    separator_pattern = r",\s+and\s+|,\s+|;\s+|\s+and\s+|\s+&\s+"
    authors_clean = [
        a.strip() for a in re.split(separator_pattern, author_str_clean) if a.strip()
    ]
    authors_original = [
        a.strip() for a in re.split(separator_pattern, author_str) if a.strip()
    ]

    # Extract surnames from cleaned authors for filename
    surnames = []
    full_names = []
    has_et_al = False  # Track if "et al" is present

    for i, author_clean in enumerate(authors_clean):
        if not author_clean:
            continue

        # Check for "et al" and strip it for surname extraction
        clean_for_surname = re.sub(
            r"\s+et\s+al\.?$", "", author_clean, flags=re.IGNORECASE
        ).strip()
        if clean_for_surname != author_clean:
            has_et_al = True

        parts = clean_for_surname.split()
        if parts:
            surname = parts[-1].strip(",.")
            surnames.append(surname)

        # Use original author string for full_names
        if i < len(authors_original):
            full_names.append(authors_original[i].strip())
        else:
            full_names.append(author_clean.strip())

    if not surnames:
        return "Unknown", ["Unknown"]

    # Format for filename
    if len(surnames) == 1:
        if has_et_al:
            return f"{surnames[0]}_et_al", full_names
        return surnames[0], full_names
    elif len(surnames) == 2:
        return f"{surnames[0]}_{surnames[1]}", full_names
    else:
        return f"{surnames[0]}_et_al", full_names


# =============================================================================
# Title sanitization
# =============================================================================


def sanitize_title(title):
    """
    Sanitize title for use in filename.
    Removes prepositions, special characters, keeps domain-specific terms.
    """
    if not title:
        return "Untitled"

    # Remove special characters, keep alphanumeric and spaces
    title = re.sub(r"[^\w\s-]", " ", title)

    words = title.split()
    filtered_words = []

    for i, word in enumerate(words):
        word_lower = word.lower()

        # Skip prepositions (even at start)
        if word_lower in PREPOSITIONS:
            continue

        # Keep domain-specific terms
        if word_lower in DOMAIN_ADJECTIVES:
            filtered_words.append(word)
            continue

        # Keep other substantial words (length > 2)
        if len(word) > 2:
            filtered_words.append(word)

    sanitized = "_".join(filtered_words)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_")

    return sanitized if sanitized else "Untitled"


# =============================================================================
# Harvard reference formatting
# =============================================================================


def create_harvard_reference(author_names, year, title, publisher, filename):
    """
    Create Harvard-style bibliography entry.

    Format: Author(s) (Year) *Title*. Publisher.
            **File**: filename.pdf
    """
    # Format authors
    if not author_names or author_names == ["Unknown"]:
        author_part = "Unknown"
    elif len(author_names) == 1:
        author_part = author_names[0]
    elif len(author_names) == 2:
        author_part = f"{author_names[0]} and {author_names[1]}"
    else:
        author_part = ", ".join(author_names[:-1]) + f" and {author_names[-1]}"

    year_part = f"({year})" if year else "(n.d.)"
    title_part = f"*{title}*" if title else "*Untitled*"
    publisher_part = f" {publisher}." if publisher else ""

    reference = (
        f"{author_part} {year_part} {title_part}.{publisher_part}\n**File**: {filename}"
    )
    return reference


# =============================================================================
# References JSON operations (source of truth)
# =============================================================================


def load_references_json():
    """Load all references from JSON file."""
    if not config.REFERENCES_JSON.exists():
        return []
    with open(config.REFERENCES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_references_json(entries):
    """Save all references to JSON file."""
    with open(config.REFERENCES_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def add_entry_to_references_json(
    author_names,
    year,
    title,
    publisher,
    filename,
    original_filename=None,
    file_hash=None,
):
    """Add a new entry to references.json or update if it already exists."""
    entries = load_references_json()

    # Check if entry already exists
    for entry in entries:
        if entry["filename"] == filename:
            # Update existing entry
            entry.update(
                {
                    "author": (
                        ", ".join(author_names)
                        if isinstance(author_names, list)
                        else author_names
                    ),
                    "year": year or "",
                    "title": title,
                    "publisher": publisher or "",
                    "filename": filename,
                }
            )
            # Add original_filename if provided and not already present
            if original_filename and "original_filename" not in entry:
                entry["original_filename"] = original_filename
            # Add file_hash if provided
            if file_hash:
                entry["file_hash"] = file_hash
            save_references_json(entries)
            return True

    # Add new entry
    new_entry = {
        "author": (
            ", ".join(author_names) if isinstance(author_names, list) else author_names
        ),
        "year": year or "",
        "title": title,
        "publisher": publisher or "",
        "filename": filename,
    }
    # Add original_filename if provided
    if original_filename:
        new_entry["original_filename"] = original_filename
    # Add file_hash if provided
    if file_hash:
        new_entry["file_hash"] = file_hash
    entries.append(new_entry)
    save_references_json(entries)
    return True


def remove_entry_from_references_json(filename):
    """Remove entry from references.json by filename."""
    entries = load_references_json()
    original_count = len(entries)
    entries = [e for e in entries if e["filename"] != filename]

    if len(entries) < original_count:
        save_references_json(entries)
        return True
    return False


def update_entry_in_references_json(
    old_filename, new_filename, author_names, year, title, publisher
):
    """Update entry in references.json."""
    entries = load_references_json()

    for entry in entries:
        if entry["filename"] == old_filename:
            entry.update(
                {
                    "author": (
                        ", ".join(author_names)
                        if isinstance(author_names, list)
                        else author_names
                    ),
                    "year": year or "",
                    "title": title,
                    "publisher": publisher or "",
                    "filename": new_filename,
                }
            )
            save_references_json(entries)
            return True

    return False


def get_entry_from_references_json(filename):
    """Get a single entry from references.json by filename."""
    entries = load_references_json()
    for entry in entries:
        if entry["filename"] == filename:
            return entry
    return None


# =============================================================================
# Filename operations
# =============================================================================


def check_duplicate_filename(new_filename, processed_files, target_dir=None):
    """Check if filename already exists, add suffix if needed."""
    if target_dir is None:
        target_dir = config.REFERENCE_DIR

    if new_filename not in processed_files and not (target_dir / new_filename).exists():
        return new_filename

    base, ext = new_filename.rsplit(".", 1)
    counter = 2
    while (
        f"{base}_{counter}.{ext}" in processed_files
        or (target_dir / f"{base}_{counter}.{ext}").exists()
    ):
        counter += 1

    return f"{base}_{counter}.{ext}"


def generate_new_filename(author, title, processed_files=None, target_dir=None):
    """
    Generate a new filename from author and title.
    Returns (new_filename, author_names_list).
    """
    if processed_files is None:
        processed_files = set()
    if target_dir is None:
        target_dir = config.REFERENCE_DIR

    author_filename, author_names = parse_author(author)
    title_filename = sanitize_title(title)

    new_filename = f"{author_filename}_{title_filename}.pdf"

    # Truncate if too long
    if len(new_filename) > 150:
        title_filename = "_".join(title_filename.split("_")[:10])
        new_filename = f"{author_filename}_{title_filename}.pdf"

    new_filename = check_duplicate_filename(new_filename, processed_files, target_dir)

    return new_filename, author_names


def rename_file(old_path, new_path):
    """Rename/move a file. Returns True if successful."""
    if old_path == new_path:
        return True
    if not old_path.exists():
        return False
    shutil.move(str(old_path), str(new_path))
    return True


# =============================================================================
# Duplicate detection utilities
# =============================================================================

SUGGESTED_FIELDS = ("suggested_author", "suggested_title", "suggested_year")
ANNOTATION_FIELDS = ("quarantine",) + SUGGESTED_FIELDS


def add_annotation_fields(entries):
    """Add null annotation fields (quarantine, suggested_*) to entries lacking them."""
    for entry in entries:
        for field in ANNOTATION_FIELDS:
            entry.setdefault(field, None)


def title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity between two titles (0.0 to 1.0)."""
    if not title1 or not title2:
        return 0.0
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio()


def detect_exact_duplicates(entries):
    """
    Find files with identical SHA256 hashes.

    Args:
        entries: List of reference entries from references.json

    Returns:
        List of duplicate groups, each with hash, count, and files list
    """
    from collections import defaultdict

    hash_groups = defaultdict(list)

    for entry in entries:
        file_hash = entry.get("file_hash")
        if file_hash:
            hash_groups[file_hash].append(entry)

    # Keep only groups with more than one file
    duplicates = []
    for file_hash, files in hash_groups.items():
        if len(files) > 1:
            duplicates.append(
                {
                    "hash": file_hash,
                    "count": len(files),
                    "files": [
                        {
                            "filename": f["filename"],
                            "author": f.get("author", ""),
                            "title": f.get("title", ""),
                            "year": f.get("year", ""),
                            "publisher": f.get("publisher", ""),
                            "original_filename": f.get("original_filename", ""),
                        }
                        for f in files
                    ],
                }
            )

    # Sort by count (most duplicates first)
    duplicates.sort(key=lambda x: x["count"], reverse=True)

    return duplicates


def detect_similar_entries(
    entries, similarity_threshold=0.70, include_annotations=False
):
    """
    Find files with same author and similar titles (>= threshold).

    Args:
        entries: List of reference entries from references.json
        similarity_threshold: Minimum title similarity (0.0 to 1.0)
        include_annotations: If True, include quarantine/suggested_* fields for editing

    Returns:
        List of similar pairs sorted by similarity (highest first)
    """
    from collections import defaultdict

    similar_pairs = []

    # Group by author
    by_author = defaultdict(list)
    for entry in entries:
        author = normalize_author_for_comparison(entry.get("author", ""))
        if author and author != "unknown":
            by_author[author].append(entry)

    # Within each author, find similar titles
    for author, docs in by_author.items():
        if len(docs) < 2:
            continue

        for i, doc1 in enumerate(docs):
            for doc2 in docs[i + 1 :]:
                title1 = doc1.get("title", "")
                title2 = doc2.get("title", "")

                if not title1 or not title2:
                    continue

                similarity = title_similarity(title1, title2)

                if similarity >= similarity_threshold:
                    # Skip exact duplicates (same hash)
                    hash1 = doc1.get("file_hash")
                    hash2 = doc2.get("file_hash")
                    if hash1 and hash2 and hash1 == hash2:
                        continue

                    file1_data = {
                        "filename": doc1["filename"],
                        "title": title1,
                        "year": doc1.get("year", ""),
                        "publisher": doc1.get("publisher", ""),
                        "original_filename": doc1.get("original_filename", ""),
                    }
                    file2_data = {
                        "filename": doc2["filename"],
                        "title": title2,
                        "year": doc2.get("year", ""),
                        "publisher": doc2.get("publisher", ""),
                        "original_filename": doc2.get("original_filename", ""),
                    }

                    if include_annotations:
                        add_annotation_fields([file1_data, file2_data])

                    similar_pairs.append(
                        {
                            "similarity": round(similarity, 3),
                            "author": doc1.get("author", ""),
                            "file1": file1_data,
                            "file2": file2_data,
                        }
                    )

    # Sort by similarity (highest first)
    similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)

    return similar_pairs


def flatten_files_from_pairs(pairs):
    """
    Extract all files from similar-pair entries, handling file1, file2, file3, etc.
    Returns a list of unique file entries with merged annotations
    (quarantine True wins; non-null suggested_* values win).
    """
    files_dict = {}

    for pair in pairs:
        for key in pair.keys():
            if not key.startswith("file"):
                continue
            file_entry = pair[key]
            filename = file_entry["filename"]

            if filename in files_dict:
                existing = files_dict[filename]
                if file_entry.get("quarantine") is True:
                    existing["quarantine"] = True
                for field in SUGGESTED_FIELDS:
                    if file_entry.get(field) is not None:
                        existing[field] = file_entry[field]
            else:
                files_dict[filename] = file_entry

    return list(files_dict.values())


def normalize_author_for_comparison(author: str) -> str:
    """Normalize author string for comparison (lowercase, stripped)."""
    if not author:
        return ""
    return author.lower().strip()


def check_hash_conflict(file_hash, references=None):
    """
    Check if file_hash matches any existing entry in references.json.

    Args:
        file_hash: SHA256 hash to check
        references: Optional pre-loaded references list (for performance)

    Returns:
        The matching entry dict if found, None otherwise
    """
    if not file_hash:
        return None

    if references is None:
        references = load_references_json()

    for entry in references:
        if entry.get("file_hash") == file_hash:
            return entry

    return None


def check_filename_conflict(filename, references=None):
    """
    Check if exact filename exists in references.json.

    Args:
        filename: Target filename to check
        references: Optional pre-loaded references list

    Returns:
        The matching entry dict if found, None otherwise
    """
    if references is None:
        references = load_references_json()

    for entry in references:
        if entry["filename"] == filename:
            return entry

    return None


def create_reference_stub(
    file_path, author, title, year, publisher, processed_files=None
):
    """
    Create a reference stub with all fields needed before processing.

    This generates the hash and target filename without moving the file,
    allowing conflict detection before committing to the operation.

    Args:
        file_path: Path to the source PDF file
        author: Author string (may be None)
        title: Title string
        year: Year string (may be None)
        publisher: Publisher string (may be None)
        processed_files: Optional set of already-processed filenames in current batch

    Returns:
        Dict with: file_hash, filename, author, author_names, title, year,
                   publisher, original_filename
    """
    if processed_files is None:
        processed_files = set()

    file_hash = calculate_file_hash(file_path)
    new_filename, author_names = generate_new_filename(
        author, title, processed_files, config.REFERENCE_DIR
    )

    return {
        "file_hash": file_hash,
        "filename": new_filename,
        "author": (
            ", ".join(author_names) if isinstance(author_names, list) else author_names
        ),
        "author_names": author_names,
        "title": title,
        "year": year,
        "publisher": publisher,
        "original_filename": (
            file_path.name if hasattr(file_path, "name") else str(file_path)
        ),
    }


def calculate_file_hash(filepath: Path) -> Optional[str]:
    """Calculate SHA256 hash of file. Returns None on error."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None


# =============================================================================
# Validation utilities
# =============================================================================


def is_unknown_author(author: str) -> bool:
    """Check if author field indicates unknown/missing author."""
    if not author:
        return True
    author_lower = author.strip().lower()
    return author_lower in ["unknown", "---", "null", ""]


def is_suspect_filename(filename: str) -> bool:
    """Check if a filename appears to have bad metadata."""
    # Remove .pdf extension
    name = filename.replace(".pdf", "")

    # Patterns that indicate bad metadata
    suspect_patterns = [
        r"^\d+_\d+_\d+",  # Starts with number_number_number (e.g., 19/56/25)
        r"^\d{5,}_",  # Starts with 5+ digits followed by underscore
        r"^untitled",  # Named "untitled"
        r"^[a-z]{2,10}\d{6,}",  # Short letters followed by many digits
        r"_dvi\.pdf$",  # Ends with _dvi
        r"^[A-Z]{2,4}_\d",  # Starts with 2-4 caps then digits (like VF_092802)
        r"^\d+\.pdf$",  # Just numbers
        r"^[a-z]+\d{6,}$",  # lowercase letters followed by 6+ digits
    ]

    for pattern in suspect_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            return True

    # Very short names (likely bad)
    if len(name) < 10 and "_" not in name:
        return True

    # Names that are mostly numbers
    digit_count = sum(c.isdigit() for c in name)
    if digit_count / len(name) > 0.5:
        return True

    return False


# =============================================================================
# References.md regeneration
# =============================================================================


def regenerate_references_md() -> bool:
    """Regenerate references.md from references.json. Returns success status."""
    # Imported here to avoid a circular import (the generator imports from utils)
    from src.scripts.core.generate_references_md import generate_markdown

    return generate_markdown()
