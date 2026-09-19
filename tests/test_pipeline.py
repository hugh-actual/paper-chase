"""
Integration tests for the file-moving components: UpdateStep and
DocumentProcessor. All paths are redirected to tmp_path so nothing
touches the real collection.
"""

import hashlib
import importlib
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
        "HISTORY_FILE": tmp_path / "history.jsonl",
    }
    for name, value in overrides.items():
        monkeypatch.setattr(config, name, value)

    return {
        **dirs,
        "references_json": references_json,
        "references_md": references_md,
        "history": tmp_path / "history.jsonl",
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

    def test_missing_file_is_non_fatal(self, sandbox):
        """A 'file not found' error is routine on reruns over stale
        annotations (already applied, or overlapping with another update
        step) and must not be treated as a fatal failure."""
        annotations = [{"filename": "Already_Handled.pdf", "quarantine": True}]
        input_file = sandbox["json_output"] / SimpleStep.input_filename
        input_file.write_text(json.dumps(annotations))
        utils.save_references_json([])

        result = SimpleStep().run()

        assert result["quarantine_errors"] == 1
        assert result["fatal_errors"] == 0

    def test_rename_failure_is_fatal(self, sandbox, monkeypatch):
        """A genuine failure while applying an update (e.g. the rename
        itself raising) must be reported as fatal, unlike a routine
        'not found' skip."""
        entry = seed_entry(sandbox, "Doe_Real.pdf", "Jane Doe", "Real", content=b"a")
        utils.save_references_json([entry])

        annotations = [
            {
                "filename": entry["filename"],
                "quarantine": None,
                "suggested_author": None,
                "suggested_title": "New Title",
                "suggested_year": None,
            }
        ]
        input_file = sandbox["json_output"] / SimpleStep.input_filename
        input_file.write_text(json.dumps(annotations))

        def boom(old_path, new_path):
            raise OSError("simulated rename failure")

        monkeypatch.setattr("src.lib.steps.rename_file", boom)

        result = SimpleStep().run()

        assert result["update_errors"] == 1
        assert result["fatal_errors"] == 1

    def test_failed_md_regeneration_is_fatal(self, sandbox, monkeypatch):
        """references.json is already saved by the time references.md is
        regenerated, so a failure there leaves the two out of sync --
        and `verify` won't catch it, because it compares the filesystem
        against references.json and never reads references.md."""
        entry = seed_entry(sandbox, "Doe_Real.pdf", "Jane Doe", "Real", content=b"a")
        utils.save_references_json([entry])

        annotations = [{"filename": entry["filename"], "quarantine": True}]
        input_file = sandbox["json_output"] / SimpleStep.input_filename
        input_file.write_text(json.dumps(annotations))

        monkeypatch.setattr("src.lib.steps.regenerate_references_md", lambda: False)

        result = SimpleStep().run()

        assert result["quarantined"] == 1
        assert result["quarantine_errors"] == 0
        assert result["fatal_errors"] == 1

    def test_log_separates_failures_from_skips(self, sandbox, monkeypatch):
        """The log must let a reader tell a genuine failure from an
        'already applied' skip -- the printed detail scrolls off, so the
        log is where a partially-applied run gets diagnosed."""
        entry = seed_entry(sandbox, "Doe_Real.pdf", "Jane Doe", "Real", content=b"a")
        utils.save_references_json([entry])

        annotations = [
            # Genuine failure: the rename raises.
            {"filename": entry["filename"], "suggested_title": "New Title"},
            # Routine skip: annotation left over from an earlier run.
            {"filename": "Already_Handled.pdf", "quarantine": True},
        ]
        input_file = sandbox["json_output"] / SimpleStep.input_filename
        input_file.write_text(json.dumps(annotations))

        def boom(old_path, new_path):
            raise OSError("simulated rename failure")

        monkeypatch.setattr("src.lib.steps.rename_file", boom)

        step = SimpleStep()
        result = step.run()

        assert result["fatal_errors"] == 1
        log = step.log_file.read_text()
        failures = log.split("## Failures")[1].split("## Skipped")[0]
        skipped = log.split("## Skipped")[1]

        assert "simulated rename failure" in failures
        assert "Already_Handled.pdf" not in failures
        assert "Already_Handled.pdf" in skipped
        assert "simulated rename failure" not in skipped


UPDATE_MODULES = [
    "src.scripts.updates.update_broken_titles",
    "src.scripts.updates.update_unknown_authors",
    "src.scripts.updates.update_exact_duplicates",
    "src.scripts.updates.update_similar_pairs",
]


class TestMainExitCodes:
    """Each update script's main() must translate fatal errors into an
    exit code, so `make update-all` halts on real breakage. The steps.py
    branch is covered above; this covers the four call sites."""

    @pytest.mark.parametrize("module_path", UPDATE_MODULES)
    @pytest.mark.parametrize("fatal_count, expected_exit", [(0, 0), (1, 1), (3, 1)])
    def test_main_returns_exit_code(
        self, sandbox, monkeypatch, module_path, fatal_count, expected_exit
    ):
        module = importlib.import_module(module_path)

        # No subclass overrides run(), so patching the base covers all four.
        monkeypatch.setattr(
            UpdateStep,
            "run",
            lambda self: {
                "total": 0,
                "quarantined": 0,
                "updated": 0,
                "quarantine_errors": 0,
                "update_errors": 0,
                "fatal_errors": fatal_count,
            },
        )

        assert module.main() == expected_exit


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

    def test_interrupt_mid_batch_keeps_progress(self, sandbox, monkeypatch):
        """Ctrl-C partway through a batch used to leave already-moved files
        renamed in reference/ with no references.json entry and no log --
        their original names were gone. Now each file is journalled before
        its move and saved after it, and the log is still written."""
        utils.save_references_json([])
        for i in range(1, 6):
            (sandbox["todo"] / f"file{i}.pdf").write_bytes(
                make_pdf_bytes(f"Paper Number {i}", "Jane Smith", "2020")
            )

        import src.scripts.core.process_documents as pd

        real_move = pd.shutil.move
        calls = {"n": 0}

        def move_then_interrupt(src, dst):
            calls["n"] += 1
            if calls["n"] == 3:
                raise KeyboardInterrupt
            return real_move(src, dst)

        monkeypatch.setattr(
            "src.scripts.core.process_documents.shutil.move", move_then_interrupt
        )

        with pytest.raises(KeyboardInterrupt):
            DocumentProcessor().run()

        entries = utils.load_references_json()
        assert [e["original_filename"] for e in entries] == ["file1.pdf", "file2.pdf"]
        assert all(e["file_hash"] for e in entries)
        for e in entries:
            assert (sandbox["reference"] / e["filename"]).exists()
        for i in range(3, 6):
            assert (sandbox["todo"] / f"file{i}.pdf").exists()

        log = (sandbox["markdown"] / "log.md").read_text()
        assert "Interrupted" in log
        assert "file1.pdf → " in log and "file2.pdf → " in log

        # Every attempted move is journalled, including the one interrupted
        # (its intent is recorded before the move, its failure after).
        history = utils.load_history()
        ingests = [h for h in history if h["event"] == "ingest"]
        assert [h["original_filename"] for h in ingests] == [
            "file1.pdf",
            "file2.pdf",
            "file3.pdf",
        ]
        failed = [h for h in history if h["event"] == "ingest_failed"]
        assert [h["original_filename"] for h in failed] == ["file3.pdf"]
        assert failed[0]["error"] == "KeyboardInterrupt"

    def test_ingest_event_carries_the_full_entry(self, sandbox):
        """The journalled ingest event holds exactly the references.json
        entry, so a lost entry can be rebuilt from the event alone."""
        utils.save_references_json([])
        (sandbox["todo"] / "download.pdf").write_bytes(
            make_pdf_bytes("Great Findings", "Jane Smith", "2020")
        )

        DocumentProcessor().run()

        [entry] = utils.load_references_json()
        [event] = utils.load_history()
        assert event["event"] == "ingest"
        assert {k: event[k] for k in entry} == entry

    def test_move_failure_is_fatal(self, sandbox, monkeypatch):
        """A genuine failure ingesting a file (the move raising) is fatal,
        unlike a conflict, and leaves the file in todo/ with its failure
        journalled."""
        utils.save_references_json([])
        incoming = sandbox["todo"] / "download.pdf"
        incoming.write_bytes(make_pdf_bytes("Great Findings", "Jane Smith", "2020"))

        def boom(src, dst):
            raise OSError("simulated move failure")

        monkeypatch.setattr("src.scripts.core.process_documents.shutil.move", boom)

        processor = DocumentProcessor()
        result = processor.run()

        assert result["fatal_errors"] == 1
        assert result["processed"] == 0
        assert incoming.exists()
        [err] = processor.fatal_errors
        assert err.phase == "ingest" and err.filename == "download.pdf"
        assert [h["event"] for h in utils.load_history()] == ["ingest", "ingest_failed"]

    def test_failed_md_regeneration_is_fatal(self, sandbox, monkeypatch):
        """references.json is saved by the time references.md is
        regenerated, so a failure there leaves the two out of sync -- and
        `verify` never reads references.md, so nothing else catches it."""
        utils.save_references_json([])
        (sandbox["todo"] / "download.pdf").write_bytes(
            make_pdf_bytes("Great Findings", "Jane Smith", "2020")
        )

        monkeypatch.setattr(
            "src.scripts.core.process_documents.regenerate_references_md",
            lambda: False,
        )

        result = DocumentProcessor().run()

        assert result["processed"] == 1
        assert result["fatal_errors"] == 1

    def test_failed_json_save_is_fatal(self, sandbox, monkeypatch):
        utils.save_references_json([])
        (sandbox["todo"] / "download.pdf").write_bytes(
            make_pdf_bytes("Great Findings", "Jane Smith", "2020")
        )

        def boom(entries):
            raise OSError("simulated disk full")

        monkeypatch.setattr(
            "src.scripts.core.process_documents.save_references_json", boom
        )

        processor = DocumentProcessor()
        result = processor.run()

        assert result["fatal_errors"] >= 1
        assert all(e.phase == "output" for e in processor.fatal_errors)

    def test_conflicts_and_skips_are_routine(self, sandbox):
        """Conflicts and large/non-PDF skips are expected outcomes: they are
        listed under Skipped in the log, not Failures, and exit 0."""
        existing = seed_entry(
            sandbox, "Doe_Existing_Paper.pdf", "Jane Doe", "Existing Paper"
        )
        utils.save_references_json([existing])
        (sandbox["todo"] / "dup.pdf").write_bytes(DUMMY_PDF)  # hash conflict
        (sandbox["todo"] / "notes.txt").write_text("not a pdf")

        processor = DocumentProcessor()
        result = processor.run()

        assert result["fatal_errors"] == 0
        assert result["skipped"] == 2
        log = (sandbox["markdown"] / "log.md").read_text()
        assert "## Failures" not in log
        skipped = log.split("## Skipped")[1]
        assert "dup.pdf" in skipped and "notes.txt" in skipped

    def test_log_separates_failures_from_skips(self, sandbox, monkeypatch):
        utils.save_references_json([])
        (sandbox["todo"] / "download.pdf").write_bytes(
            make_pdf_bytes("Great Findings", "Jane Smith", "2020")
        )
        (sandbox["todo"] / "notes.txt").write_text("not a pdf")

        def boom(src, dst):
            raise OSError("simulated move failure")

        monkeypatch.setattr("src.scripts.core.process_documents.shutil.move", boom)

        DocumentProcessor().run()

        log = (sandbox["markdown"] / "log.md").read_text()
        failures = log.split("## Failures")[1].split("## Skipped")[0]
        skipped = log.split("## Skipped")[1]
        assert "simulated move failure" in failures
        assert "notes.txt" not in failures
        assert "notes.txt" in skipped
        assert "simulated move failure" not in skipped

    @pytest.mark.parametrize("fatal_count, expected_exit", [(0, 0), (1, 1), (3, 1)])
    def test_main_returns_exit_code(
        self, sandbox, monkeypatch, fatal_count, expected_exit
    ):
        """`make ingest` runs `verify` after `process`; a genuine ingest
        failure must exit nonzero so the chain stops."""
        module = importlib.import_module("src.scripts.core.process_documents")
        monkeypatch.setattr(
            DocumentProcessor,
            "run",
            lambda self: {
                "processed": 0,
                "conflicts": 0,
                "skipped": 0,
                "fatal_errors": fatal_count,
            },
        )

        assert module.main() == expected_exit

    def test_failed_log_write_does_not_mask_interrupt(self, sandbox, monkeypatch):
        """The log is written inside the finally; if that write fails it
        must be recorded, not raised over the propagating interrupt."""
        utils.save_references_json([])
        (sandbox["todo"] / "download.pdf").write_bytes(
            make_pdf_bytes("Great Findings", "Jane Smith", "2020")
        )
        monkeypatch.setattr(config, "MARKDOWN_DIR", sandbox["markdown"] / "missing")

        def interrupt(src, dst):
            raise KeyboardInterrupt

        monkeypatch.setattr("src.scripts.core.process_documents.shutil.move", interrupt)

        processor = DocumentProcessor()
        with pytest.raises(KeyboardInterrupt):
            processor.run()
        assert any("log.md" in e.message for e in processor.fatal_errors)
