"""
Integration tests for the file-moving components: UpdateStep and
DocumentProcessor. All paths are redirected to tmp_path so nothing
touches the real collection.
"""

import hashlib
import importlib
import io
import json
import unicodedata
from pathlib import Path

import pytest
from pypdf import PdfWriter

import src.lib.config as config
import src.lib.utils as utils
from src.lib.steps import UpdateStep
from src.scripts.core.process_documents import DocumentProcessor, choose_metadata

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


def write_annotations(sandbox, annotations):
    input_file = sandbox["json_output"] / SimpleStep.input_filename
    input_file.write_text(json.dumps(annotations))


class TestUpdateStepJournal:
    """Quarantines and renames are journalled before the file moves, never
    overwrite anything, and an interrupted run still saves its progress."""

    def test_quarantine_never_overwrites_and_journals_the_entry(self, sandbox):
        # A file of the same name is already in quarantine/ from earlier
        seeded = sandbox["quarantine"] / "Doe_Thing.pdf"
        seeded.write_bytes(b"seeded")

        quarantined_names = []
        for content in (b"first", b"second"):
            entry = seed_entry(
                sandbox, "Doe_Thing.pdf", "Jane Doe", "Thing", content=content
            )
            entry["original_filename"] = "download.pdf"
            utils.save_references_json([entry])
            write_annotations(
                sandbox, [{"filename": entry["filename"], "quarantine": True}]
            )

            result = SimpleStep().run()

            assert result["quarantined"] == 1
            assert result["fatal_errors"] == 0
            assert utils.load_references_json() == []

            event = utils.load_history()[-1]
            assert event["event"] == "quarantine"
            # The full removed entry survives in the journal
            assert {k: event[k] for k in entry} == entry
            target = sandbox["quarantine"] / event["quarantine_filename"]
            assert target.read_bytes() == content
            quarantined_names.append(event["quarantine_filename"])

        # Nothing was overwritten: seeded file intact, three distinct files
        assert seeded.read_bytes() == b"seeded"
        assert quarantined_names[0] == "Doe_Thing_2.pdf"
        assert len({"Doe_Thing.pdf", *quarantined_names}) == 3
        assert len(list(sandbox["quarantine"].iterdir())) == 3

    def test_unlisted_file_is_quarantined_and_journalled_by_hash(self, sandbox):
        """A file with no references.json entry is still moved (a routine
        skip, as before), and journalled with what is known about it."""
        path = sandbox["reference"] / "Stray.pdf"
        path.write_bytes(b"stray")
        utils.save_references_json([])
        write_annotations(sandbox, [{"filename": "Stray.pdf", "quarantine": True}])

        result = SimpleStep().run()

        assert result["quarantine_errors"] == 1
        assert result["fatal_errors"] == 0
        assert (sandbox["quarantine"] / "Stray.pdf").exists()
        [event] = utils.load_history()
        assert event["event"] == "quarantine"
        assert event["filename"] == "Stray.pdf"
        assert event["quarantine_filename"] == "Stray.pdf"
        assert event["file_hash"] == hashlib.sha256(b"stray").hexdigest()

    def test_rename_event_holds_old_name_new_entry_and_previous(self, sandbox):
        entry = seed_entry(
            sandbox, "Doe_Old_Title.pdf", "Jane Doe", "Old Title", content=b"a"
        )
        entry["original_filename"] = "download.pdf"
        entry["publisher"] = "Some Press"
        utils.save_references_json([entry])
        write_annotations(
            sandbox,
            [
                {
                    "filename": entry["filename"],
                    "suggested_title": "New Title",
                    "suggested_year": "n.d.",
                }
            ],
        )

        SimpleStep().run()

        [stored] = utils.load_references_json()
        [event] = utils.load_history()
        assert event["event"] == "rename"
        assert event["old_filename"] == "Doe_Old_Title.pdf"
        # Recorded exactly as stored -- "n.d." is stored as ""
        for key in ("filename", "author", "title", "year", "publisher"):
            assert event[key] == stored[key]
        assert event["year"] == ""
        assert event["file_hash"] == entry["file_hash"]
        assert event["original_filename"] == "download.pdf"
        assert event["previous"] == {
            "author": "Jane Doe",
            "title": "Old Title",
            "year": "2020",
            "publisher": "Some Press",
        }
        assert (sandbox["reference"] / stored["filename"]).exists()

    def test_history_failure_is_fatal_and_nothing_moves(self, sandbox, monkeypatch):
        """No journal, no move: a file must never move without a durable
        record of where it went."""
        keep = seed_entry(sandbox, "Doe_Keep.pdf", "Jane Doe", "Keep", content=b"a")
        drop = seed_entry(sandbox, "Roe_Drop.pdf", "Rick Roe", "Drop", content=b"b")
        utils.save_references_json([keep, drop])
        before = sandbox["references_json"].read_text()
        write_annotations(
            sandbox,
            [
                {"filename": drop["filename"], "quarantine": True},
                {"filename": keep["filename"], "suggested_title": "New Title"},
            ],
        )

        def boom(event, **fields):
            raise OSError("simulated history failure")

        monkeypatch.setattr("src.lib.steps.append_history", boom)

        result = SimpleStep().run()

        assert result["fatal_errors"] == 2
        assert result["quarantined"] == 0
        assert result["updated"] == 0
        assert (sandbox["reference"] / "Doe_Keep.pdf").exists()
        assert (sandbox["reference"] / "Roe_Drop.pdf").exists()
        assert list(sandbox["quarantine"].iterdir()) == []
        assert len(list(sandbox["reference"].iterdir())) == 2
        assert sandbox["references_json"].read_text() == before

    def test_interrupt_mid_run_saves_progress(self, sandbox, monkeypatch):
        """Ctrl-C partway through used to leave moved/renamed files whose
        entries still pointed at their old names (references.json was only
        saved at the end). Now the finally saves what was done."""
        gone = seed_entry(sandbox, "Poe_Gone.pdf", "Ann Poe", "Gone", content=b"q")
        entries = [
            seed_entry(sandbox, "Doe_One.pdf", "Jane Doe", "One", content=b"1"),
            seed_entry(sandbox, "Roe_Two.pdf", "Rick Roe", "Two", content=b"2"),
            seed_entry(sandbox, "Moe_Three.pdf", "Mo Moe", "Three", content=b"3"),
        ]
        utils.save_references_json([gone, *entries])
        write_annotations(
            sandbox,
            [{"filename": gone["filename"], "quarantine": True}]
            + [
                {"filename": e["filename"], "suggested_title": f"New {e['title']}"}
                for e in entries
            ],
        )

        real_rename = utils.rename_file
        calls = {"n": 0}

        def rename_then_interrupt(old_path, new_path):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt
            return real_rename(old_path, new_path)

        monkeypatch.setattr("src.lib.steps.rename_file", rename_then_interrupt)

        with pytest.raises(KeyboardInterrupt):
            SimpleStep().run()

        # references.json on disk matches the files on disk
        saved = utils.load_references_json()
        assert "Poe_Gone.pdf" not in [e["filename"] for e in saved]
        assert (sandbox["quarantine"] / "Poe_Gone.pdf").exists()
        by_hash = {e["file_hash"]: e for e in saved}
        first = by_hash[entries[0]["file_hash"]]
        assert first["title"] == "New One"
        assert first["filename"] != "Doe_One.pdf"
        assert by_hash[entries[1]["file_hash"]]["filename"] == "Roe_Two.pdf"
        assert by_hash[entries[2]["file_hash"]]["filename"] == "Moe_Three.pdf"
        for e in saved:
            assert (sandbox["reference"] / e["filename"]).exists()
        assert "New One" in sandbox["references_md"].read_text()

        log = (sandbox["markdown"] / SimpleStep.log_filename).read_text()
        assert "interrupted" in log

        history = utils.load_history()
        renames = [h for h in history if h["event"] == "rename"]
        assert [h["old_filename"] for h in renames] == ["Doe_One.pdf", "Roe_Two.pdf"]
        failed = [h for h in history if h["event"] == "rename_failed"]
        assert [h["old_filename"] for h in failed] == ["Roe_Two.pdf"]
        assert failed[0]["error"] == "KeyboardInterrupt"

    def test_failed_log_write_does_not_mask_interrupt(self, sandbox, monkeypatch):
        """The log is written inside the finally; if that write fails it
        must be recorded, not raised over the propagating interrupt."""
        entry = seed_entry(sandbox, "Doe_Real.pdf", "Jane Doe", "Real", content=b"a")
        utils.save_references_json([entry])
        write_annotations(
            sandbox, [{"filename": entry["filename"], "quarantine": True}]
        )
        monkeypatch.setattr(config, "MARKDOWN_DIR", sandbox["markdown"] / "missing")

        def interrupt(src, dst):
            raise KeyboardInterrupt

        monkeypatch.setattr("src.lib.steps.shutil.move", interrupt)

        step = SimpleStep()
        with pytest.raises(KeyboardInterrupt):
            step.run()
        assert any(SimpleStep.log_filename in e.message for e in step.fatal_errors)
        assert (sandbox["reference"] / "Doe_Real.pdf").exists()
        failed = [h for h in utils.load_history() if h["event"] == "quarantine_failed"]
        assert [h["filename"] for h in failed] == ["Doe_Real.pdf"]


class TestUpdateStepFilenames:
    """A file's own current name is never treated as taken by another file,
    so updates that don't change the name don't suffix or shuffle it."""

    def test_year_only_update_keeps_the_name(self, sandbox):
        entry = seed_entry(
            sandbox, "Doe_Old_Title.pdf", "Jane Doe", "Old Title", content=b"a"
        )
        utils.save_references_json([entry])
        write_annotations(
            sandbox, [{"filename": entry["filename"], "suggested_year": "1999"}]
        )

        result = SimpleStep().run()

        assert result["updated"] == 1
        assert result["fatal_errors"] == 0
        [stored] = utils.load_references_json()
        assert stored["filename"] == "Doe_Old_Title.pdf"
        assert stored["year"] == "1999"
        assert [p.name for p in sandbox["reference"].iterdir()] == ["Doe_Old_Title.pdf"]

        # Metadata-only updates are journalled with old_filename == filename
        [event] = utils.load_history()
        assert event["event"] == "rename"
        assert event["old_filename"] == event["filename"] == "Doe_Old_Title.pdf"
        assert event["year"] == "1999"
        assert event["previous"]["year"] == "2020"

    def test_title_update_onto_another_files_name_still_suffixes(self, sandbox):
        other = seed_entry(
            sandbox, "Doe_Other_Work.pdf", "Jane Doe", "Other Work", content=b"o"
        )
        entry = seed_entry(
            sandbox, "Doe_Old_Title.pdf", "Jane Doe", "Old Title", content=b"a"
        )
        utils.save_references_json([other, entry])
        write_annotations(
            sandbox,
            [{"filename": entry["filename"], "suggested_title": "Other Work"}],
        )

        SimpleStep().run()

        by_hash = {e["file_hash"]: e for e in utils.load_references_json()}
        assert by_hash[other["file_hash"]]["filename"] == "Doe_Other_Work.pdf"
        assert by_hash[entry["file_hash"]]["filename"] == "Doe_Other_Work_2.pdf"
        assert (sandbox["reference"] / "Doe_Other_Work.pdf").read_bytes() == b"o"
        assert (sandbox["reference"] / "Doe_Other_Work_2.pdf").read_bytes() == b"a"

    def test_suffixed_file_is_not_shuffled(self, sandbox):
        """`X_2.pdf` regenerating base `X.pdf` while another `X.pdf` exists
        stays `X_2.pdf` -- not `X_3.pdf`."""
        base = seed_entry(
            sandbox, "Doe_Old_Title.pdf", "Jane Doe", "Old Title", content=b"a"
        )
        second = seed_entry(
            sandbox, "Doe_Old_Title_2.pdf", "Jane Doe", "Old Title", content=b"b"
        )
        utils.save_references_json([base, second])
        write_annotations(
            sandbox, [{"filename": second["filename"], "suggested_year": "1999"}]
        )

        SimpleStep().run()

        by_hash = {e["file_hash"]: e for e in utils.load_references_json()}
        assert by_hash[base["file_hash"]]["filename"] == "Doe_Old_Title.pdf"
        assert by_hash[second["file_hash"]]["filename"] == "Doe_Old_Title_2.pdf"
        assert by_hash[second["file_hash"]]["year"] == "1999"
        assert sorted(p.name for p in sandbox["reference"].iterdir()) == [
            "Doe_Old_Title.pdf",
            "Doe_Old_Title_2.pdf",
        ]


class TestSuggestedPublisher:
    """suggested_publisher: None keeps, any string (including "") sets.
    Publisher isn't part of the filename, so it alone never renames."""

    def seed(self, sandbox, publisher="PDF Software 1.0"):
        entry = seed_entry(
            sandbox, "Doe_Old_Title.pdf", "Jane Doe", "Old Title", content=b"a"
        )
        entry["publisher"] = publisher
        utils.save_references_json([entry])
        return entry

    def test_empty_string_clears_publisher_without_renaming(self, sandbox):
        self.seed(sandbox)
        write_annotations(
            sandbox,
            [{"filename": "Doe_Old_Title.pdf", "suggested_publisher": ""}],
        )

        result = SimpleStep().run()

        assert result["updated"] == 1
        [stored] = utils.load_references_json()
        assert stored["publisher"] == ""
        assert stored["filename"] == "Doe_Old_Title.pdf"
        assert (stored["author"], stored["title"], stored["year"]) == (
            "Jane Doe",
            "Old Title",
            "2020",
        )
        assert [p.name for p in sandbox["reference"].iterdir()] == ["Doe_Old_Title.pdf"]

        [event] = utils.load_history()
        assert event["event"] == "rename"
        assert event["old_filename"] == event["filename"] == "Doe_Old_Title.pdf"
        assert event["publisher"] == ""
        assert event["previous"]["publisher"] == "PDF Software 1.0"

        log = (sandbox["markdown"] / SimpleStep.log_filename).read_text()
        assert "publisher → (cleared)" in log

    def test_null_publisher_is_kept(self, sandbox):
        self.seed(sandbox, publisher="Some Press")
        write_annotations(
            sandbox,
            [
                {
                    "filename": "Doe_Old_Title.pdf",
                    "suggested_year": "1999",
                    "suggested_publisher": None,
                }
            ],
        )

        SimpleStep().run()

        [stored] = utils.load_references_json()
        assert stored["publisher"] == "Some Press"
        assert stored["year"] == "1999"

    def test_publisher_only_null_annotation_is_not_an_update(self, sandbox):
        self.seed(sandbox)
        write_annotations(
            sandbox,
            [{"filename": "Doe_Old_Title.pdf", "suggested_publisher": None}],
        )

        result = SimpleStep().run()

        assert result["updated"] == 0
        assert utils.load_history() == []

    def test_title_and_publisher_update_together(self, sandbox):
        self.seed(sandbox)
        write_annotations(
            sandbox,
            [
                {
                    "filename": "Doe_Old_Title.pdf",
                    "suggested_title": "New Title",
                    "suggested_publisher": "Some Press",
                }
            ],
        )

        SimpleStep().run()

        [stored] = utils.load_references_json()
        assert stored["title"] == "New Title"
        assert stored["publisher"] == "Some Press"
        assert stored["filename"] == "Doe_New_Title.pdf"
        assert (sandbox["reference"] / "Doe_New_Title.pdf").exists()
        [event] = utils.load_history()
        assert event["filename"] == "Doe_New_Title.pdf"
        assert event["publisher"] == "Some Press"
        assert event["previous"] == {
            "author": "Jane Doe",
            "title": "Old Title",
            "year": "2020",
            "publisher": "PDF Software 1.0",
        }


UPDATE_MODULES = [
    "src.scripts.updates.update_broken_titles",
    "src.scripts.updates.update_unknown_authors",
    "src.scripts.updates.update_exact_duplicates",
    "src.scripts.updates.update_similar_pairs",
    "src.scripts.updates.update_metadata_mismatches",
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


class TestExtractFromFilename:
    """Table test for DocumentProcessor.extract_from_filename's pattern
    matching: existing patterns (regression) plus the T8 fixes -- the
    YYYY-Author-Title pattern now requires a letter in the author segment,
    a new "Author et al - Title" pattern, and plausible-years-only
    extraction in the default branch -- plus the T7 follow-up: patterns 1
    and 4 (which have no explicit year field) also take a plausible year
    from the title itself, not just the default branch."""

    @pytest.mark.parametrize(
        "filename, expected_author, expected_title, expected_year",
        [
            # Pattern 1: [Author]Title
            (
                "[Hastie]Elements of Statistical Learning.pdf",
                "Hastie",
                "Elements of Statistical Learning",
                None,
            ),
            # Pattern 1 takes a plausible year from the title when present
            (
                "[Hastie]Elements of Statistical Learning 2009.pdf",
                "Hastie",
                "Elements of Statistical Learning 2009",
                "2009",
            ),
            # ... but not an implausible one (< 1500), like a book-count title
            ("[Smith]Top 1000 Words.pdf", "Smith", "Top 1000 Words", None),
            # Pattern 2: YYYY-Author-Title (regression)
            ("2019-Smith-Great Findings.pdf", "Smith", "Great Findings", "2019"),
            # Pattern 2 must not match when the author segment has no letter
            # -- falls through to the default branch instead.
            ("2019-2020-Annual-Report.pdf", None, "2019-2020-Annual-Report", "2019"),
            # Pattern 3: YYYY_Book_Title (regression)
            ("2015_Book_Deep Learning.pdf", None, "Deep Learning", "2015"),
            ("2015_Article_A Survey.pdf", None, "A Survey", "2015"),
            # Pattern 4 (new): Author et al - Title
            (
                "Smith et al - A Survey of Methods.pdf",
                "Smith et al",
                "A Survey of Methods",
                None,
            ),
            ("Jones et al. - Another Paper.pdf", "Jones et al.", "Another Paper", None),
            # Pattern 4 takes a plausible year from the title when present
            (
                "Smith et al - Survey 2015 Edition.pdf",
                "Smith et al",
                "Survey 2015 Edition",
                "2015",
            ),
            # Pattern 5: arxiv number + title (regression)
            (
                "1706.03762 Attention Is All You Need.pdf",
                None,
                "Attention Is All You Need",
                None,
            ),
            # Default branch: plausible year only, not part of a longer run
            ("ISBN9780387848570.pdf", None, "ISBN9780387848570", None),
            ("Paper 1999 final.pdf", None, "Paper 1999 final", "1999"),
            ("Untitled Notes.pdf", None, "Untitled Notes", None),
        ],
    )
    def test_pattern_table(
        self, filename, expected_author, expected_title, expected_year
    ):
        info = DocumentProcessor().extract_from_filename(filename)
        assert info["author"] == expected_author
        assert info["title"] == expected_title
        assert info["year"] == expected_year

    def test_nfd_filename_normalised_to_nfc(self):
        """A macOS-decomposed (NFD) filename must yield NFC author/title,
        so accented letters survive sanitize_title's character filtering
        later in the pipeline instead of being silently dropped."""
        nfd_filename = unicodedata.normalize(
            "NFD", "[Gödel]Über formal unentscheidbare Sätze.pdf"
        )
        info = DocumentProcessor().extract_from_filename(nfd_filename)
        assert info["author"] == "Gödel"
        assert info["title"] == "Über formal unentscheidbare Sätze"
        assert unicodedata.is_normalized("NFC", info["author"])
        assert unicodedata.is_normalized("NFC", info["title"])


class TestChooseMetadata:
    """Unit tests for choose_metadata()'s precedence rules (plan task T7)."""

    def test_structured_filename_wins_over_junk_metadata(self):
        pdf_meta = {
            "title": "Microsoft Word - draft3.doc",
            "author": "Administrator",
            "year": None,
            "publisher": None,
        }
        filename_info = {
            "author": "Knuth",
            "title": "Art of Computer Programming",
            "year": "1975",
            "structured": True,
        }
        chosen = choose_metadata(pdf_meta, filename_info)
        assert chosen["author"] == "Knuth"
        assert chosen["title"] == "Art of Computer Programming"
        assert chosen["year"] == "1975"
        assert chosen["publisher"] is None

    def test_structured_filename_gap_filled_by_non_junk_metadata(self):
        """A structured pattern that doesn't produce an author (e.g.
        YYYY_Book_Title) still gets one from non-junk metadata."""
        pdf_meta = {
            "title": "irrelevant",
            "author": "Jane Doe",
            "year": None,
            "publisher": None,
        }
        filename_info = {
            "author": None,
            "title": "Deep Learning",
            "year": "2015",
            "structured": True,
        }
        chosen = choose_metadata(pdf_meta, filename_info)
        assert chosen["author"] == "Jane Doe"
        assert chosen["title"] == "Deep Learning"

    def test_unstructured_filename_non_junk_metadata_wins(self):
        pdf_meta = {
            "title": "Great Findings",
            "author": "Jane Smith",
            "year": None,
            "publisher": None,
        }
        filename_info = {
            "author": None,
            "title": "download",
            "year": None,
            "structured": False,
        }
        chosen = choose_metadata(pdf_meta, filename_info)
        assert chosen["author"] == "Jane Smith"
        assert chosen["title"] == "Great Findings"

    def test_unstructured_filename_junk_metadata_falls_back_to_filename(self):
        pdf_meta = {
            "title": "Microsoft Word - x.doc",
            "author": "Administrator",
            "year": None,
            "publisher": None,
        }
        filename_info = {
            "author": None,
            "title": "download",
            "year": None,
            "structured": False,
        }
        chosen = choose_metadata(pdf_meta, filename_info)
        assert chosen["title"] == "download"
        assert chosen["author"] is None

    def test_year_never_from_pdf_metadata(self):
        """Even if pdf_meta somehow carried a year, choose_metadata must
        never use it -- only the filename or 'n.d.'"""
        pdf_meta = {"title": None, "author": None, "year": "2021", "publisher": None}
        filename_info = {
            "author": None,
            "title": "x",
            "year": None,
            "structured": True,
        }
        chosen = choose_metadata(pdf_meta, filename_info)
        assert chosen["year"] == "n.d."

    def test_publisher_passthrough(self):
        """publisher always comes straight from pdf_meta (never the
        filename); extract_pdf_metadata itself always hands back None."""
        chosen = choose_metadata(
            {"title": None, "author": None, "year": None, "publisher": None},
            {"author": None, "title": "x", "year": None, "structured": False},
        )
        assert chosen["publisher"] is None


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

    def test_metadata_precedence_structured_filename_wins_over_junk_metadata(
        self, sandbox
    ):
        """Plan T7 scenario (a): a curated, structured filename beats junk
        embedded metadata (a Microsoft Word placeholder title, an
        "Administrator" author, and a CreationDate that must not leak into
        the year)."""
        utils.save_references_json([])
        content = make_pdf_bytes(
            "Microsoft Word - draft3.doc", "Administrator", year="2019"
        )
        incoming = sandbox["todo"] / "1975-Knuth-Art of Computer Programming.pdf"
        incoming.write_bytes(content)

        processor = DocumentProcessor()
        processor.run()

        entries = utils.load_references_json()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["author"] == "Knuth"
        assert entry["title"] == "Art of Computer Programming"
        assert entry["year"] == "1975"
        assert entry["publisher"] == ""

    def test_metadata_precedence_unstructured_filename_uses_good_metadata(
        self, sandbox
    ):
        """Plan T7 scenario (b): an unstructured filename with good
        embedded metadata still uses that metadata -- existing tests
        (e.g. test_orphaned_reference_entry_reserves_filename) already
        depend on this precedence via similar "download.pdf" fixtures."""
        utils.save_references_json([])
        content = make_pdf_bytes("Great Findings", "Jane Smith", year="2020")
        incoming = sandbox["todo"] / "download.pdf"
        incoming.write_bytes(content)

        processor = DocumentProcessor()
        processor.run()

        entries = utils.load_references_json()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["author"] == "Jane Smith"
        assert entry["title"] == "Great Findings"

    def test_metadata_precedence_creation_date_never_used_for_year(self, sandbox):
        """Plan T7 scenario (c), updated per review follow-up: the bracket
        pattern is structured and has no explicit year field, but does
        take a plausible year from the title itself (2009) -- the PDF's
        CreationDate (2021) must never be used, whether or not the title
        supplies a year of its own."""
        utils.save_references_json([])
        content = make_pdf_bytes("irrelevant", "irrelevant", year="2021")
        incoming = sandbox["todo"] / "[Hastie]Elements of Statistical Learning 2009.pdf"
        incoming.write_bytes(content)

        processor = DocumentProcessor()
        processor.run()

        entries = utils.load_references_json()
        assert len(entries) == 1
        assert entries[0]["year"] == "2009"

    def test_metadata_precedence_bracket_pattern_without_year_gives_nd(self, sandbox):
        """Companion to the case above: when the title carries no
        plausible year either, the entry falls back to "n.d." (stored as
        an empty year field) -- the CreationDate still must not fill it
        in."""
        utils.save_references_json([])
        content = make_pdf_bytes("irrelevant", "irrelevant", year="2021")
        incoming = sandbox["todo"] / "[Hastie]Elements of Statistical Learning.pdf"
        incoming.write_bytes(content)

        processor = DocumentProcessor()
        processor.run()

        entries = utils.load_references_json()
        assert len(entries) == 1
        assert entries[0]["year"] == ""

    def test_metadata_precedence_unstructured_junk_metadata_uses_filename_stem(
        self, sandbox
    ):
        """Plan T7 scenario (d): an unstructured filename with junk
        embedded title metadata falls back to the filename stem."""
        utils.save_references_json([])
        content = make_pdf_bytes(
            "Microsoft Word - draft.doc", "Administrator", year="2020"
        )
        incoming = sandbox["todo"] / "somefile.pdf"
        incoming.write_bytes(content)

        processor = DocumentProcessor()
        processor.run()

        entries = utils.load_references_json()
        assert len(entries) == 1
        assert entries[0]["title"] == "somefile"


class TestVerifyFilesAndMetadata:
    """Tests for verify_files_and_metadata.py exit codes.

    The bug: main() returned the discrepancy count directly as the exit code,
    so 256 discrepancies wrapped to 0 (success). Fixed to return 1 if count > 0.
    """

    def test_verify_returns_zero_for_clean_collection(self, sandbox):
        """Clean sandbox with no discrepancies should return exit code 0."""
        # Create empty references.json
        utils.save_references_json([])

        # Import and call verify's main function
        from src.scripts.core.verify_files_and_metadata import main

        exit_code = main()
        assert exit_code == 0

    def test_verify_returns_one_for_missing_files(self, sandbox):
        """When references.json has entries but files don't exist, exit code is 1."""
        # Create 256 references.json entries with missing files
        entries = [
            {
                "author": f"Author {i}",
                "year": "2020",
                "title": f"Title {i}",
                "publisher": "",
                "filename": f"Author_{i}_Title_{i}.pdf",
                "file_hash": hashlib.sha256(f"content-{i}".encode()).hexdigest(),
            }
            for i in range(256)
        ]
        utils.save_references_json(entries)

        # Import and call verify's main function
        from src.scripts.core.verify_files_and_metadata import main

        exit_code = main()
        # 256 discrepancies: should return 1, not 0 (mod 256 wrap bug)
        assert exit_code == 1

    def test_verify_returns_one_for_small_discrepancy(self, sandbox):
        """Any discrepancy count > 0 should return exit code 1."""
        # Create 1 reference.json entry with missing file
        entries = [
            {
                "author": "John Doe",
                "year": "2020",
                "title": "Sample Paper",
                "publisher": "",
                "filename": "Doe_Sample_Paper.pdf",
                "file_hash": hashlib.sha256(b"content").hexdigest(),
            }
        ]
        utils.save_references_json(entries)

        # Import and call verify's main function
        from src.scripts.core.verify_files_and_metadata import main

        exit_code = main()
        assert exit_code == 1

    def test_backup_holds_pre_run_state(self, sandbox):
        """references.json is saved after every file, but only the first
        save of a run backs up -- so .bak is the state before the batch,
        not the state one file ago."""
        existing = seed_entry(
            sandbox, "Doe_Existing_Paper.pdf", "Jane Doe", "Existing Paper"
        )
        utils.save_references_json([existing])
        pre_run = sandbox["references_json"].read_bytes()
        for i in range(1, 4):
            (sandbox["todo"] / f"file{i}.pdf").write_bytes(
                make_pdf_bytes(f"Paper Number {i}", "Jane Smith", "2020")
            )

        DocumentProcessor().run()

        assert len(utils.load_references_json()) == 4
        backup = sandbox["references_json"].with_name("references.json.bak")
        assert backup.read_bytes() == pre_run


def write_history(sandbox, *events):
    """Append hand-written history events (for event types other scripts
    produce), one JSON line each."""
    with open(sandbox["history"], "a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


class TestRecoverOrphans:
    def _ingest(self, sandbox, count):
        utils.save_references_json([])
        for i in range(1, count + 1):
            (sandbox["todo"] / f"file{i}.pdf").write_bytes(
                make_pdf_bytes(f"Paper Number {i}", "Jane Smith", "2020")
            )
        DocumentProcessor().run()
        return utils.load_references_json()

    def test_restores_entries_lost_by_interrupted_batch(self, sandbox):
        """Files moved into reference/ whose entries never reached
        references.json are rebuilt exactly from their ingest events."""
        from src.scripts.utilities import recover_orphans

        entries = self._ingest(sandbox, 2)
        assert len(entries) == 2
        # The crash: files are in reference/, references.json is pre-run.
        utils.save_references_json([])

        assert recover_orphans.main([]) == 0  # dry run
        assert utils.load_references_json() == []

        assert recover_orphans.main(["--apply"]) == 0
        recovered = utils.load_references_json()
        key = lambda e: e["filename"]  # noqa: E731
        assert sorted(recovered, key=key) == sorted(entries, key=key)
        assert all(e["original_filename"].startswith("file") for e in recovered)
        assert entries[0]["filename"] in sandbox["references_md"].read_text()

    def test_hash_must_match(self, sandbox):
        """A file sitting at a journalled name but with different content
        is not the file the event describes -- leave it unresolved."""
        from src.scripts.utilities import recover_orphans

        [entry] = self._ingest(sandbox, 1)
        utils.save_references_json([])
        (sandbox["reference"] / entry["filename"]).write_bytes(b"other content")

        plan = recover_orphans.plan_recovery([], utils.load_history())
        assert plan["restored"] == []
        assert plan["unresolved"] == [entry["filename"]]

    def test_latest_matching_event_wins(self, sandbox):
        from src.scripts.utilities import recover_orphans

        path = sandbox["reference"] / "Smith_Paper.pdf"
        path.write_bytes(b"content")
        file_hash = utils.calculate_file_hash(path)
        base = {"filename": "Smith_Paper.pdf", "file_hash": file_hash}
        write_history(
            sandbox,
            {
                "event": "ingest",
                **base,
                "author": "J Smith",
                "title": "Old",
                "year": "2020",
                "publisher": "",
                "original_filename": "dl.pdf",
            },
            {
                "event": "rename",
                "old_filename": "Smith_Paper.pdf",
                **base,
                "author": "Jane Smith",
                "title": "Paper",
                "year": "2021",
            },
        )

        plan = recover_orphans.plan_recovery([], utils.load_history())
        [entry] = plan["restored"]
        assert entry["author"] == "Jane Smith"
        assert entry["year"] == "2021"
        # Not in the rename event: inherited from the earlier ingest
        assert entry["original_filename"] == "dl.pdf"

    def test_missing_file_explained_by_rename(self, sandbox):
        """An update step renamed the file but died before saving
        references.json: the entry is pointed at the new name, and the
        renamed file isn't also restored as a second entry."""
        from src.scripts.utilities import recover_orphans

        new = sandbox["reference"] / "Smith_New_Title.pdf"
        new.write_bytes(b"content")
        file_hash = utils.calculate_file_hash(new)
        entry = {
            "author": "Jane Smith",
            "year": "2020",
            "title": "Old Title",
            "publisher": "",
            "filename": "Smith_Old_Title.pdf",
            "original_filename": "dl.pdf",
            "file_hash": file_hash,
        }
        utils.save_references_json([entry])
        write_history(
            sandbox,
            {
                "event": "rename",
                "old_filename": "Smith_Old_Title.pdf",
                "filename": "Smith_New_Title.pdf",
                "file_hash": file_hash,
                "author": "Jane Smith",
                "title": "New Title",
                "year": "2020",
            },
        )

        assert recover_orphans.main(["--apply"]) == 0

        [fixed] = utils.load_references_json()
        assert fixed["filename"] == "Smith_New_Title.pdf"
        assert fixed["title"] == "New Title"
        assert fixed["original_filename"] == "dl.pdf"

    def test_missing_file_explained_by_quarantine(self, sandbox):
        from src.scripts.utilities import recover_orphans

        entry = {
            "author": "Jane Smith",
            "year": "2020",
            "title": "Dup",
            "publisher": "",
            "filename": "Smith_Dup.pdf",
            "file_hash": "abc",
        }
        utils.save_references_json([entry])
        (sandbox["quarantine"] / "Smith_Dup_2.pdf").write_bytes(b"x")
        write_history(
            sandbox,
            {"event": "quarantine", **entry, "quarantine_filename": "Smith_Dup_2.pdf"},
        )

        assert recover_orphans.main(["--apply"]) == 0
        assert utils.load_references_json() == []

    def test_unexplained_missing_file_is_left_alone(self, sandbox):
        from src.scripts.utilities import recover_orphans

        entry = {
            "author": "Jane Smith",
            "year": "2020",
            "title": "Gone",
            "publisher": "",
            "filename": "Smith_Gone.pdf",
            "file_hash": "abc",
        }
        utils.save_references_json([entry])

        assert recover_orphans.main(["--apply"]) == 0
        assert utils.load_references_json() == [entry]

    def test_tolerates_malformed_history_lines(self, sandbox):
        from src.scripts.utilities import recover_orphans

        [entry] = self._ingest(sandbox, 1)
        utils.save_references_json([])
        with open(sandbox["history"], "a", encoding="utf-8") as f:
            f.write('{"event": "ing\n')

        assert recover_orphans.main(["--apply"]) == 0
        assert utils.load_references_json() == [entry]

    def test_failed_save_exits_nonzero(self, sandbox, monkeypatch):
        from src.scripts.utilities import recover_orphans

        self._ingest(sandbox, 1)
        utils.save_references_json([])

        def boom(entries):
            raise OSError("simulated disk full")

        monkeypatch.setattr(recover_orphans, "save_references_json", boom)
        assert recover_orphans.main(["--apply"]) == 1

    def test_verify_names_original_and_suggests_recover(self, sandbox, capsys):
        from src.scripts.core import verify_files_and_metadata

        self._ingest(sandbox, 1)
        utils.save_references_json([])
        capsys.readouterr()

        assert verify_files_and_metadata.main() == 1
        out = capsys.readouterr().out
        assert "(originally: file1.pdf)" in out
        assert "make recover" in out


class TestOrphanAwareHashConflicts:
    def _orphan_entry(self, content):
        return {
            "author": "Jane Smith",
            "year": "2020",
            "title": "Great Findings",
            "publisher": "",
            "filename": "Smith_Great_Findings.pdf",
            "original_filename": "first_download.pdf",
            "file_hash": hashlib.sha256(content).hexdigest(),
        }

    def test_present_duplicate_reports_file_present(self, sandbox):
        existing = seed_entry(
            sandbox, "Doe_Existing_Paper.pdf", "Jane Doe", "Existing Paper"
        )
        utils.save_references_json([existing])
        (sandbox["todo"] / "dup.pdf").write_bytes(DUMMY_PDF)

        processor = DocumentProcessor()
        processor.run()

        [conflict] = processor.conflicts[0]["conflicts"]
        assert conflict["type"] == "hash_duplicate"
        assert conflict["existing_file_present"] is True

    def test_identical_file_restores_missing_entry_file(self, sandbox):
        """The entry's file is gone; the documented workflow used to call
        the incoming copy a duplicate and tell the user to delete it -- the
        only surviving copy. It must be relinked under the entry's name."""
        content = make_pdf_bytes("Some Other Title", "Someone Else", "1999")
        entry = self._orphan_entry(content)
        utils.save_references_json([entry])
        incoming = sandbox["todo"] / "second_download.pdf"
        incoming.write_bytes(content)

        processor = DocumentProcessor()
        result = processor.run()

        assert result["fatal_errors"] == 0
        assert result["relinked"] == 1
        assert processor.conflicts == []
        assert not incoming.exists()
        restored = sandbox["reference"] / "Smith_Great_Findings.pdf"
        assert restored.read_bytes() == content
        # Metadata is the entry's, not re-derived from the incoming file
        assert utils.load_references_json() == [entry]

        [event] = utils.load_history()
        assert event["event"] == "relink"
        assert event["incoming_filename"] == "second_download.pdf"
        assert event["filename"] == "Smith_Great_Findings.pdf"
        assert (
            "second_download.pdf → Smith_Great_Findings.pdf"
            in (sandbox["markdown"] / "log.md").read_text()
        )

    def test_occupied_name_is_held(self, sandbox):
        """If different content now sits at the entry's filename, restoring
        would overwrite it -- hold the incoming file instead."""
        content = make_pdf_bytes("Some Other Title", "Someone Else", "1999")
        entry = self._orphan_entry(content)
        utils.save_references_json([entry])
        occupant = sandbox["reference"] / "Smith_Great_Findings.pdf"
        occupant.write_bytes(b"different content")
        incoming = sandbox["todo"] / "second_download.pdf"
        incoming.write_bytes(content)

        processor = DocumentProcessor()
        result = processor.run()

        assert result["fatal_errors"] == 0
        assert incoming.exists()
        assert occupant.read_bytes() == b"different content"
        [conflict] = processor.conflicts[0]["conflicts"]
        assert conflict["type"] == "hash_matches_missing_file"
        assert conflict["existing_file_present"] is False


class TestHeldConflicts:
    def _hold_duplicate(self, sandbox, name="dup.pdf"):
        existing = seed_entry(
            sandbox, "Doe_Existing_Paper.pdf", "Jane Doe", "Existing Paper"
        )
        utils.save_references_json([existing])
        held = sandbox["todo"] / name
        held.write_bytes(DUMMY_PDF)
        DocumentProcessor().run()
        assert held.exists()
        return held

    def test_clean_run_replaces_stale_report(self, sandbox):
        held = self._hold_duplicate(sandbox)
        report_file = sandbox["json_output"] / "ingestion_conflicts.json"
        assert len(json.loads(report_file.read_text())["conflicts"]) == 1

        held.unlink()
        DocumentProcessor().run()

        assert json.loads(report_file.read_text())["conflicts"] == []

    def test_quarantine_held_dry_run_then_apply(self, sandbox):
        from src.scripts.utilities import quarantine_held

        held = self._hold_duplicate(sandbox)
        # A same-named file already in quarantine/ must not be overwritten
        (sandbox["quarantine"] / "dup.pdf").write_bytes(b"earlier")

        assert quarantine_held.main([]) == 0
        assert held.exists(), "dry run must not move anything"

        assert quarantine_held.main(["--apply"]) == 0
        assert not held.exists()
        assert (sandbox["quarantine"] / "dup.pdf").read_bytes() == b"earlier"
        assert (sandbox["quarantine"] / "dup_2.pdf").read_bytes() == DUMMY_PDF
        assert (sandbox["reference"] / "Doe_Existing_Paper.pdf").exists()

        event = utils.load_history()[-1]
        assert event["event"] == "quarantine_held"
        assert event["original_filename"] == "dup.pdf"
        assert event["quarantine_filename"] == "dup_2.pdf"

    def test_refuses_when_existing_copy_missing(self, sandbox):
        from src.scripts.utilities import quarantine_held

        held = self._hold_duplicate(sandbox)
        (sandbox["reference"] / "Doe_Existing_Paper.pdf").unlink()

        assert quarantine_held.main(["--apply"]) == 0
        assert held.exists()
        assert list(sandbox["quarantine"].iterdir()) == []

    def test_refuses_when_existing_copy_differs(self, sandbox):
        from src.scripts.utilities import quarantine_held

        held = self._hold_duplicate(sandbox)
        (sandbox["reference"] / "Doe_Existing_Paper.pdf").write_bytes(b"changed")

        assert quarantine_held.main(["--apply"]) == 0
        assert held.exists()
        assert list(sandbox["quarantine"].iterdir()) == []

    def test_move_failure_exits_nonzero(self, sandbox, monkeypatch):
        from src.scripts.utilities import quarantine_held

        held = self._hold_duplicate(sandbox)

        def boom(src, dst):
            raise OSError("simulated move failure")

        monkeypatch.setattr(quarantine_held.shutil, "move", boom)

        assert quarantine_held.main(["--apply"]) == 1
        assert held.exists()

    def test_status_reports_todo_and_held(self, sandbox, capsys):
        from src.scripts.utilities import status

        self._hold_duplicate(sandbox)
        (sandbox["todo"] / "new.pdf").write_bytes(b"%PDF-1.4 new\n%%EOF\n")

        assert status.check_todo() == {
            "todo": 2,
            "held_duplicates": 1,
            "held_other": 0,
            "report_timestamp": "today",
        }
        status.main()
        out = capsys.readouterr().out
        assert "make ingest" in out
        assert "make quarantine-held" in out


class TestPreviouslyQuarantined:
    CONTENT = b"%PDF-1.4 quarantined content\n%%EOF\n"

    def _quarantine_event(self, sandbox, file_hash, copy=True):
        if copy:
            (sandbox["quarantine"] / "Smith_Dup.pdf").write_bytes(self.CONTENT)
        write_history(
            sandbox,
            {
                "event": "quarantine",
                "ts": "2026-01-02T03:04:05+00:00",
                "author": "Jane Smith",
                "year": "2020",
                "title": "Dup",
                "publisher": "",
                "filename": "Smith_Dup.pdf",
                "file_hash": file_hash,
                "quarantine_filename": "Smith_Dup.pdf",
            },
        )

    def test_held_while_quarantined_copy_exists(self, sandbox):
        utils.save_references_json([])
        self._quarantine_event(sandbox, hashlib.sha256(self.CONTENT).hexdigest())
        incoming = sandbox["todo"] / "again.pdf"
        incoming.write_bytes(self.CONTENT)

        processor = DocumentProcessor()
        result = processor.run()

        assert result["fatal_errors"] == 0
        assert incoming.exists()
        assert utils.load_references_json() == []
        [conflict] = processor.conflicts[0]["conflicts"]
        assert conflict["type"] == "previously_quarantined"
        assert conflict["quarantine_filename"] == "Smith_Dup.pdf"
        assert conflict["quarantined_at"] == "2026-01-02T03:04:05+00:00"
        assert conflict["existing_file_present"] is True

    def test_ingested_with_warning_when_quarantined_copy_gone(self, sandbox):
        utils.save_references_json([])
        self._quarantine_event(
            sandbox, hashlib.sha256(self.CONTENT).hexdigest(), copy=False
        )
        incoming = sandbox["todo"] / "again.pdf"
        incoming.write_bytes(self.CONTENT)

        processor = DocumentProcessor()
        processor.run()

        assert not incoming.exists()
        assert processor.conflicts == []
        assert len(utils.load_references_json()) == 1
        log = (sandbox["markdown"] / "log.md").read_text()
        assert "quarantine/Smith_Dup.pdf" in log

    def test_ingested_when_quarantined_copy_differs(self, sandbox):
        utils.save_references_json([])
        self._quarantine_event(sandbox, hashlib.sha256(self.CONTENT).hexdigest())
        (sandbox["quarantine"] / "Smith_Dup.pdf").write_bytes(b"replaced")
        (sandbox["todo"] / "again.pdf").write_bytes(self.CONTENT)

        processor = DocumentProcessor()
        processor.run()

        assert processor.conflicts == []
        assert len(utils.load_references_json()) == 1

    def test_none_hash_quarantine_event_never_matches(self, sandbox):
        """An unlisted file quarantined without a hash must not hold
        anything -- in particular not a file whose hash failed to compute."""
        utils.save_references_json([])
        self._quarantine_event(sandbox, None)
        (sandbox["todo"] / "again.pdf").write_bytes(self.CONTENT)

        processor = DocumentProcessor()
        processor.run()
        assert processor.conflicts == []
        assert len(utils.load_references_json()) == 1

        # And directly: a None hash is never looked up
        assert processor._check_conflicts({"file_hash": None}) == ([], None)

    def test_quarantine_held_ignores_previously_quarantined(self, sandbox):
        from src.scripts.utilities import quarantine_held

        utils.save_references_json([])
        self._quarantine_event(sandbox, hashlib.sha256(self.CONTENT).hexdigest())
        incoming = sandbox["todo"] / "again.pdf"
        incoming.write_bytes(self.CONTENT)
        DocumentProcessor().run()

        assert quarantine_held.load_held_duplicates() == []
        assert quarantine_held.main(["--apply"]) == 0
        assert incoming.exists()
        assert sorted(p.name for p in sandbox["quarantine"].iterdir()) == [
            "Smith_Dup.pdf"
        ]


class TestVerifyHistoryHints:
    def test_no_recover_hint_without_history(self, sandbox, capsys):
        from src.scripts.core import verify_files_and_metadata

        (sandbox["reference"] / "Stray_File.pdf").write_bytes(b"stray")
        utils.save_references_json(
            [
                {
                    "author": "A",
                    "year": "",
                    "title": "Gone",
                    "publisher": "",
                    "filename": "A_Gone.pdf",
                    "file_hash": "abc",
                }
            ]
        )

        assert verify_files_and_metadata.main() == 1
        assert "make recover" not in capsys.readouterr().out

    def test_missing_file_explained_by_rename(self, sandbox, capsys):
        from src.scripts.core import verify_files_and_metadata

        new = sandbox["reference"] / "Smith_New.pdf"
        new.write_bytes(b"content")
        file_hash = utils.calculate_file_hash(new)
        utils.save_references_json(
            [
                {
                    "author": "Jane Smith",
                    "year": "",
                    "title": "Old",
                    "publisher": "",
                    "filename": "Smith_Old.pdf",
                    "file_hash": file_hash,
                }
            ]
        )
        write_history(
            sandbox,
            {
                "event": "rename",
                "old_filename": "Smith_Old.pdf",
                "filename": "Smith_New.pdf",
                "file_hash": file_hash,
                "original_filename": None,
                "title": "New",
            },
        )

        assert verify_files_and_metadata.main() == 1
        out = capsys.readouterr().out
        assert "Smith_Old.pdf  (renamed to: Smith_New.pdf)" in out
        assert "make recover" in out


def test_recover_ignores_none_fields_in_later_events(sandbox):
    """steps.py records original_filename=None on a rename of an entry that
    had none; that must not wipe the value an earlier ingest recorded."""
    from src.scripts.utilities import recover_orphans

    path = sandbox["reference"] / "Smith_Paper.pdf"
    path.write_bytes(b"content")
    file_hash = utils.calculate_file_hash(path)
    write_history(
        sandbox,
        {
            "event": "ingest",
            "filename": "Smith_Old.pdf",
            "file_hash": file_hash,
            "author": "Jane Smith",
            "title": "Old",
            "year": "2020",
            "publisher": "",
            "original_filename": "dl.pdf",
        },
        {
            "event": "rename",
            "old_filename": "Smith_Old.pdf",
            "filename": "Smith_Paper.pdf",
            "file_hash": file_hash,
            "original_filename": None,
            "author": "Jane Smith",
            "title": "Paper",
            "year": "2020",
        },
    )

    [entry] = recover_orphans.plan_recovery([], utils.load_history())["restored"]
    assert entry["original_filename"] == "dl.pdf"
    assert entry["title"] == "Paper"


class TestFindMetadataMismatches:
    """find_metadata_mismatches.py: publisher-software detection and
    filename-derived corrections (T13). Read-only w.r.t. references.json."""

    def _entry(self, **overrides):
        base = {
            "author": "Jane Smith",
            "year": "2020",
            "title": "A Paper",
            "publisher": "Springer",
            "filename": "Smith_A_Paper.pdf",
        }
        base.update(overrides)
        return base

    def test_pdf_software_publisher_is_flagged(self, sandbox):
        from src.scripts.detection import find_metadata_mismatches

        utils.save_references_json([self._entry(publisher="pdfTeX-1.40.21")])

        [result] = find_metadata_mismatches.find_metadata_mismatches()
        assert result["suggested_publisher"] == ""
        assert "publisher looks like PDF-generating software" in result["reasons"]

    def test_real_publisher_is_not_flagged(self, sandbox):
        from src.scripts.detection import find_metadata_mismatches

        utils.save_references_json([self._entry(publisher="Springer")])

        assert find_metadata_mismatches.find_metadata_mismatches() == []

    def test_structured_filename_mismatch_suggests_author_title_year(self, sandbox):
        from src.scripts.detection import find_metadata_mismatches

        utils.save_references_json(
            [
                self._entry(
                    author="Administrator",
                    title="Microsoft Word - draft3.doc",
                    year="2019",
                    publisher="Springer",
                    filename="Administrator_draft3.pdf",
                    original_filename="1975-Knuth-Art of Computer Programming.pdf",
                )
            ]
        )

        [result] = find_metadata_mismatches.find_metadata_mismatches()
        assert result["suggested_author"] == "Knuth"
        assert result["suggested_title"] == "Art of Computer Programming"
        assert result["suggested_year"] == "1975"
        assert result["suggested_publisher"] is None
        assert set(result["reasons"]) == {
            "original filename suggests a different author",
            "original filename suggests a different title",
            "original filename suggests a different year",
        }

    def test_no_original_filename_is_not_reported(self, sandbox):
        """Nothing wrong except there's no original_filename to compare
        against -- the entry isn't reported at all."""
        from src.scripts.detection import find_metadata_mismatches

        utils.save_references_json([self._entry()])

        assert find_metadata_mismatches.find_metadata_mismatches() == []

    def test_unstructured_original_filename_is_not_suggested(self, sandbox):
        from src.scripts.detection import find_metadata_mismatches

        utils.save_references_json(
            [
                self._entry(
                    publisher="pdfTeX-1.40.21",
                    original_filename="random_scan_0042.pdf",
                )
            ]
        )

        [result] = find_metadata_mismatches.find_metadata_mismatches()
        assert result["suggested_publisher"] == ""
        assert result["suggested_author"] is None
        assert result["suggested_title"] is None
        assert result["suggested_year"] is None

    def test_filename_surname_form_matches_full_stored_name(self, sandbox):
        """ "Jane Smith" (stored) vs "Smith" (filename surname) is not a
        mismatch -- compared on parse_author's surname form."""
        from src.scripts.detection import find_metadata_mismatches

        utils.save_references_json(
            [
                self._entry(
                    author="Jane Smith",
                    title="A Paper",
                    year="2020",
                    original_filename="[Smith]A Paper.pdf",
                )
            ]
        )

        assert find_metadata_mismatches.find_metadata_mismatches() == []

    def test_does_not_modify_references_json(self, sandbox):
        from src.scripts.detection import find_metadata_mismatches

        utils.save_references_json(
            [
                self._entry(
                    publisher="pdfTeX-1.40.21",
                    original_filename="1975-Knuth-Art of Computer Programming.pdf",
                )
            ]
        )
        before = sandbox["references_json"].read_bytes()

        find_metadata_mismatches.find_metadata_mismatches()

        assert sandbox["references_json"].read_bytes() == before


class TestMetadataMismatchesEndToEnd:
    """detect -> annotate (as find_metadata_mismatches would produce) ->
    update: a publisher-only fix doesn't rename, a filename-derived fix
    does and is journalled, and references.md is regenerated."""

    def test_detect_annotate_update_flow(self, sandbox):
        from src.scripts.detection import find_metadata_mismatches
        from src.scripts.updates import update_metadata_mismatches

        # Entry A: publisher-only issue -- clearing it must not rename it.
        path_a = sandbox["reference"] / "Doe_A_Paper.pdf"
        path_a.write_bytes(DUMMY_PDF)
        entry_a = {
            "author": "Jane Doe",
            "year": "2020",
            "title": "A Paper",
            "publisher": "pdfTeX-1.40.21",
            "filename": "Doe_A_Paper.pdf",
            "file_hash": utils.calculate_file_hash(path_a),
        }

        # Entry B: filename-derived mismatch -- correcting it must rename.
        path_b = sandbox["reference"] / "Administrator_draft3.pdf"
        path_b.write_bytes(b"different content so the hash differs")
        entry_b = {
            "author": "Administrator",
            "year": "2019",
            "title": "Microsoft Word - draft3.doc",
            "publisher": "Springer",
            "filename": "Administrator_draft3.pdf",
            "original_filename": "1975-Knuth-Art of Computer Programming.pdf",
            "file_hash": utils.calculate_file_hash(path_b),
        }
        utils.save_references_json([entry_a, entry_b])

        results = find_metadata_mismatches.find_metadata_mismatches()
        assert len(results) == 2
        on_disk = json.loads(
            (sandbox["json_output"] / "metadata_mismatches.json").read_text()
        )
        assert on_disk == results

        assert update_metadata_mismatches.main() == 0

        by_hash = {e["file_hash"]: e for e in utils.load_references_json()}

        a = by_hash[entry_a["file_hash"]]
        assert a["publisher"] == ""
        assert a["filename"] == "Doe_A_Paper.pdf"  # unchanged: no rename

        b = by_hash[entry_b["file_hash"]]
        assert b["author"] == "Knuth"
        assert b["title"] == "Art of Computer Programming"
        assert b["year"] == "1975"
        assert b["filename"] != "Administrator_draft3.pdf"
        assert (sandbox["reference"] / b["filename"]).exists()
        assert not path_b.exists()

        rename_events = [e for e in utils.load_history() if e["event"] == "rename"]
        assert any(e["filename"] == b["filename"] for e in rename_events)

        md = sandbox["references_md"].read_text()
        assert a["filename"] in md
        assert b["filename"] in md


class TestStatusMetadataMismatches:
    """status.py's count_annotated_entries must recognise a publisher-only
    annotation, not just author/title/year (the bug T13 fixes)."""

    def test_counts_publisher_only_annotation(self, sandbox):
        from src.scripts.utilities import status

        mismatches_file = sandbox["json_output"] / "metadata_mismatches.json"
        mismatches_file.write_text(
            json.dumps(
                [
                    {
                        "filename": "A.pdf",
                        "quarantine": None,
                        "suggested_author": None,
                        "suggested_title": None,
                        "suggested_year": None,
                        "suggested_publisher": "",
                    }
                ]
            )
        )

        assert status.check_metadata_mismatches() == {
            "exists": True,
            "timestamp": "today",
            "total": 1,
            "annotated": 1,
        }

    def test_not_generated_when_missing(self, sandbox):
        from src.scripts.utilities import status

        assert status.check_metadata_mismatches() == {"exists": False}
