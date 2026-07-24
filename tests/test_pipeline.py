"""
Integration tests for the file-moving components: UpdateStep and
DocumentProcessor. All paths are redirected to tmp_path so nothing
touches the real collection.
"""

import hashlib
import io
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

import src.lib.config as config
import src.lib.utils as utils
from src.lib.steps import UpdateStep
from src.scripts.core.process_documents import DocumentProcessor

DUMMY_PDF = b"%PDF-1.4 dummy content for hashing\n%%EOF\n"


def make_pdf_bytes(title, author, year=None, pages=1):
    """Build minimal real PDF bytes carrying explicit author/title/year
    metadata, so fixtures don't rely on filename-pattern fallback parsing.
    `pages` lets two fixtures share identical metadata (so they generate the
    same target filename) while differing in byte content (so they hash
    differently)."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    metadata = {"/Title": title, "/Author": author}
    if year:
        metadata["/CreationDate"] = f"D:{year}0101000000"
    writer.add_metadata(metadata)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every configured path to a tmp directory tree."""
    dirs = {
        "reference": tmp_path / "reference",
        "quarantine": tmp_path / "quarantine",
        "todo": tmp_path / "todo",
        "markdown": tmp_path / "markdown",
        "json_output": tmp_path / "json-output",
    }
    for d in dirs.values():
        d.mkdir()

    references_json = tmp_path / "references.json"
    references_md = tmp_path / "references.md"

    # All modules read paths as config.<NAME> at call time, so patching
    # the config module redirects the entire pipeline.
    overrides = {
        "REFERENCE_DIR": dirs["reference"],
        "QUARANTINE_DIR": dirs["quarantine"],
        "TODO_DIR": dirs["todo"],
        "MARKDOWN_DIR": dirs["markdown"],
        "JSON_OUTPUT_DIR": dirs["json_output"],
        "REFERENCES_JSON": references_json,
        "REFERENCES_FILE": references_md,
    }
    for name, value in overrides.items():
        monkeypatch.setattr(config, name, value)

    return {
        **dirs,
        "references_json": references_json,
        "references_md": references_md,
    }


def seed_entry(sandbox, filename, author, title, year="2020", content=DUMMY_PDF):
    """Create a PDF file in reference/ and return its references.json entry."""
    path = sandbox["reference"] / filename
    path.write_bytes(content)
    return {
        "author": author,
        "year": year,
        "title": title,
        "publisher": "",
        "filename": filename,
        "file_hash": utils.calculate_file_hash(path),
    }


class SimpleStep(UpdateStep):
    """Minimal concrete UpdateStep for testing the shared workflow."""

    name = "test entries"
    input_filename = "test_input.json"
    log_filename = "test_update_log.md"
    log_title = "Test Update Log"

    def load_entries(self):
        with open(self.input_file, "r", encoding="utf-8") as f:
            return json.load(f)


class TestUpdateStep:
    def test_quarantine_and_update(self, sandbox):
        entry1 = seed_entry(
            sandbox, "Doe_Old_Title.pdf", "Jane Doe", "Old Title", content=b"pdf-1"
        )
        entry2 = seed_entry(
            sandbox,
            "Roe_Duplicate_Thing.pdf",
            "Rick Roe",
            "Duplicate Thing",
            content=b"pdf-2",
        )
        utils.save_references_json([entry1, entry2])

        annotations = [
            {
                "filename": entry2["filename"],
                "quarantine": True,
                "suggested_author": None,
                "suggested_title": None,
                "suggested_year": None,
            },
            {
                "filename": entry1["filename"],
                "quarantine": None,
                "suggested_author": None,
                "suggested_title": "Shiny New Title",
                "suggested_year": None,
            },
        ]
        input_file = sandbox["json_output"] / SimpleStep.input_filename
        input_file.write_text(json.dumps(annotations))

        result = SimpleStep().run()

        assert result["quarantined"] == 1
        assert result["updated"] == 1
        assert result["quarantine_errors"] == 0
        assert result["update_errors"] == 0

        # Quarantined file moved and removed from references.json
        assert not (sandbox["reference"] / entry2["filename"]).exists()
        assert (sandbox["quarantine"] / entry2["filename"]).exists()
        remaining = utils.load_references_json()
        assert len(remaining) == 1

        # Updated file renamed on disk and in references.json
        assert remaining[0]["title"] == "Shiny New Title"
        new_filename = remaining[0]["filename"]
        assert new_filename != entry1["filename"]
        assert (sandbox["reference"] / new_filename).exists()
        assert not (sandbox["reference"] / entry1["filename"]).exists()

        # references.md regenerated with the new metadata
        md = sandbox["references_md"].read_text()
        assert "Shiny New Title" in md
        assert new_filename in md
        assert entry2["filename"] not in md

    def test_error_entries_excluded_from_log_success_sections(self, sandbox):
        entry = seed_entry(sandbox, "Doe_Real.pdf", "Jane Doe", "Real", content=b"a")
        utils.save_references_json([entry])

        annotations = [
            {"filename": "Missing_File.pdf", "quarantine": True},
            {
                "filename": entry["filename"],
                "quarantine": True,
            },
        ]
        input_file = sandbox["json_output"] / SimpleStep.input_filename
        input_file.write_text(json.dumps(annotations))

        result = SimpleStep().run()

        assert result["quarantined"] == 1
        assert result["quarantine_errors"] == 1
        log = (sandbox["markdown"] / SimpleStep.log_filename).read_text()
        quarantined_section = log.split("## Quarantined Files")[1].split("##")[0]
        assert "Missing_File.pdf" not in quarantined_section
        assert entry["filename"] in quarantined_section


class TestDocumentProcessor:
    def test_hash_conflict_keeps_file_in_todo_and_writes_report(self, sandbox):
        existing = seed_entry(
            sandbox, "Doe_Existing_Paper.pdf", "Jane Doe", "Existing Paper"
        )
        utils.save_references_json([existing])

        # Identical content dropped into todo/ -> hash conflict
        incoming = sandbox["todo"] / "some_download.pdf"
        incoming.write_bytes(DUMMY_PDF)

        processor = DocumentProcessor()
        processor.run()

        assert incoming.exists(), "conflicting file must stay in todo/"
        assert len(processor.conflicts) == 1
        assert processor.conflicts[0]["conflicts"][0]["type"] == "hash_duplicate"
        assert len(utils.load_references_json()) == 1

        report_file = sandbox["json_output"] / "ingestion_conflicts.json"
        assert report_file.exists()
        report = json.loads(report_file.read_text())
        assert report["conflicts"][0]["original_filename"] == "some_download.pdf"

    def test_new_file_is_ingested_and_references_regenerated(self, sandbox):
        utils.save_references_json([])

        incoming = sandbox["todo"] / "2019-Smith-Great Findings.pdf"
        incoming.write_bytes(b"%PDF-1.4 unique content\n%%EOF\n")

        processor = DocumentProcessor()
        processor.run()

        assert not incoming.exists(), "ingested file must leave todo/"
        entries = utils.load_references_json()
        assert len(entries) == 1
        entry = entries[0]
        assert (sandbox["reference"] / entry["filename"]).exists()
        assert entry["file_hash"]

        # references.md regenerated from JSON
        md = sandbox["references_md"].read_text()
        assert entry["filename"] in md

    def test_within_batch_hash_duplicate_does_not_burn_suffix(self, sandbox):
        """Regression test: two byte-identical PDFs arriving in the same
        batch used to both get ingested (the second under a `_2` suffix)
        because self.existing_references was never updated mid-run. The
        duplicate must now be rejected -- and, critically, rejecting it must
        not reserve a filename suffix slot: a *third*, legitimate file that
        arrives after the rejected duplicate must land on `_2`, not `_3`.
        A two-file batch can't distinguish "rejection burns a slot" from
        "rejection doesn't burn a slot", so this uses three files, with the
        duplicate sorted in the middle."""
        utils.save_references_json([])
        content_a = make_pdf_bytes("Great Findings", "Jane Smith", "2020", pages=1)
        content_c = make_pdf_bytes("Great Findings", "Jane Smith", "2020", pages=2)

        first = sandbox["todo"] / "aaa_download.pdf"
        first.write_bytes(content_a)
        duplicate = sandbox["todo"] / "bbb_download.pdf"
        duplicate.write_bytes(content_a)  # byte-identical to "first" -> same hash
        third = sandbox["todo"] / "ccc_download.pdf"
        third.write_bytes(content_c)  # same generated name, distinct content

        processor = DocumentProcessor()
        processor.run()

        assert len(processor.conflicts) == 1
        assert processor.conflicts[0]["conflicts"][0]["type"] == "hash_duplicate"

        # Sorted glob order: "aaa" ingested, "bbb" rejected (same hash as
        # "aaa"), "ccc" ingested (distinct hash, same generated name).
        assert not first.exists()
        assert duplicate.exists(), "rejected duplicate must remain in todo/"
        assert not third.exists()
        assert processor.conflicts[0]["original_filename"] == "bbb_download.pdf"

        entries = utils.load_references_json()
        assert len(entries) == 2
        filenames = {e["filename"] for e in entries}
        # Must be "_2", not "_3" -- the rejected duplicate must never burn
        # a filename suffix slot that a later legitimate file then skips.
        assert filenames == {"Smith_Great_Findings.pdf", "Smith_Great_Findings_2.pdf"}

        report_file = sandbox["json_output"] / "ingestion_conflicts.json"
        assert report_file.exists()

    def test_within_batch_filename_collision_different_content(self, sandbox):
        """Two distinct PDFs (different hash) that generate the same target
        filename must both be ingested, the second one suffixed."""
        utils.save_references_json([])
        content_a = make_pdf_bytes("Great Findings", "Jane Smith", "2020", pages=1)
        content_b = make_pdf_bytes("Great Findings", "Jane Smith", "2020", pages=2)
        assert content_a != content_b

        (sandbox["todo"] / "aaa_download.pdf").write_bytes(content_a)
        (sandbox["todo"] / "bbb_download.pdf").write_bytes(content_b)

        processor = DocumentProcessor()
        processor.run()

        assert len(processor.conflicts) == 0
        entries = utils.load_references_json()
        assert len(entries) == 2
        filenames = {e["filename"] for e in entries}
        assert filenames == {"Smith_Great_Findings.pdf", "Smith_Great_Findings_2.pdf"}
        assert (sandbox["reference"] / "Smith_Great_Findings.pdf").exists()
        assert (sandbox["reference"] / "Smith_Great_Findings_2.pdf").exists()

    def test_deterministic_ordering_alphabetically_first_wins_clean_name(
        self, sandbox, monkeypatch
    ):
        """`TODO_DIR.glob()` order is filesystem-dependent; the scan must be
        sorted so the alphabetically-first source filename deterministically
        keeps the clean (unsuffixed) name -- not merely "whichever the
        filesystem returns first".

        Writing the files in reverse order is not enough to prove this: on
        many filesystems (APFS included) `glob` already returns entries
        alphabetically, so an unsorted scan would pass by luck. Force glob to
        yield reverse-alphabetical order so the assertion can only hold if
        the scan is genuinely sorted."""
        utils.save_references_json([])
        content_a = make_pdf_bytes("Great Findings", "Jane Smith", "2020", pages=1)
        content_b = make_pdf_bytes("Great Findings", "Jane Smith", "2020", pages=2)

        (sandbox["todo"] / "zzz_download.pdf").write_bytes(content_b)
        (sandbox["todo"] / "aaa_download.pdf").write_bytes(content_a)

        real_glob = Path.glob

        def reversed_glob(self, pattern):
            return iter(sorted(real_glob(self, pattern), reverse=True))

        monkeypatch.setattr(Path, "glob", reversed_glob)

        processor = DocumentProcessor()
        processor.run()

        entries = utils.load_references_json()
        assert len(entries) == 2
        clean = next(e for e in entries if e["filename"] == "Smith_Great_Findings.pdf")
        suffixed = next(
            e for e in entries if e["filename"] == "Smith_Great_Findings_2.pdf"
        )

        assert clean["file_hash"] == hashlib.sha256(content_a).hexdigest()
        assert suffixed["file_hash"] == hashlib.sha256(content_b).hexdigest()

    def test_orphaned_reference_entry_reserves_filename(self, sandbox):
        """A references.json entry whose file is missing from reference/
        (an orphan) must still reserve its filename, so a new colliding
        file is suffixed rather than reusing that name."""
        orphan_hash = hashlib.sha256(b"orphaned-content-not-on-disk").hexdigest()
        utils.save_references_json(
            [
                {
                    "author": "Jane Smith",
                    "year": "2020",
                    "title": "Great Findings",
                    "publisher": "",
                    "filename": "Smith_Great_Findings.pdf",
                    "file_hash": orphan_hash,
                }
            ]
        )
        assert not (sandbox["reference"] / "Smith_Great_Findings.pdf").exists()

        incoming_content = make_pdf_bytes(
            "Great Findings", "Jane Smith", "2020", pages=3
        )
        (sandbox["todo"] / "download.pdf").write_bytes(incoming_content)

        processor = DocumentProcessor()
        processor.run()

        assert len(processor.conflicts) == 0
        entries = utils.load_references_json()
        assert len(entries) == 2
        filenames = {e["filename"] for e in entries}
        assert filenames == {"Smith_Great_Findings.pdf", "Smith_Great_Findings_2.pdf"}

        new_entry = next(
            e for e in entries if e["filename"] == "Smith_Great_Findings_2.pdf"
        )
        assert new_entry["file_hash"] == hashlib.sha256(incoming_content).hexdigest()
        assert (sandbox["reference"] / "Smith_Great_Findings_2.pdf").exists()
        assert not (sandbox["reference"] / "Smith_Great_Findings.pdf").exists()
