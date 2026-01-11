#!/usr/bin/env python3
"""
Extract metadata from PDFs without fully rendering them.
Uses PyPDF2 for safe metadata extraction.
"""

import PyPDF2
import sys
import json
from pathlib import Path


def extract_metadata_safe(pdf_path):
    """Extract metadata and first page text from PDF without rendering."""
    try:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)

            # Get metadata
            metadata = reader.metadata

            # Get first page text (limited extraction)
            first_page_text = ""
            if len(reader.pages) > 0:
                try:
                    first_page_text = reader.pages[0].extract_text()[
                        :1000
                    ]  # Limit to first 1000 chars
                except:
                    first_page_text = "[Could not extract text]"

            result = {
                "filename": Path(pdf_path).name,
                "success": True,
                "metadata": {},
                "first_page_preview": first_page_text,
                "num_pages": len(reader.pages),
            }

            # Extract metadata fields if available
            if metadata:
                for key in [
                    "/Title",
                    "/Author",
                    "/Subject",
                    "/Creator",
                    "/Producer",
                    "/CreationDate",
                ]:
                    if key in metadata:
                        result["metadata"][key.replace("/", "")] = str(metadata[key])

            return result

    except Exception as e:
        return {"filename": Path(pdf_path).name, "success": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_metadata.py <pdf_file>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    result = extract_metadata_safe(pdf_path)
    print(json.dumps(result, indent=2))
