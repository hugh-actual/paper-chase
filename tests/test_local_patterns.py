"""Tests for the optional local title-pattern loader in find_broken_titles."""

import json

import pytest

from src.scripts.detection.find_broken_titles import (
    is_broken_title,
    load_local_patterns,
)


def write_patterns(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestLoadLocalPatterns:
    def test_missing_file_returns_empty_list(self, tmp_path):
        assert load_local_patterns(tmp_path / "nope.json") == []

    def test_loads_valid_patterns(self, tmp_path):
        path = write_patterns(
            tmp_path / "local_title_patterns.json",
            [{"pattern": r"knitting", "reason": "Hobby content - out of place"}],
        )
        patterns = load_local_patterns(path)
        assert len(patterns) == 1
        assert patterns[0]["reason"] == "Hobby content - out of place"
        assert patterns[0]["regex"].search("Advanced Knitting Techniques")

    def test_skips_invalid_entries(self, tmp_path, capsys):
        path = write_patterns(
            tmp_path / "local_title_patterns.json",
            [
                {"pattern": r"good", "reason": "ok"},
                {"pattern": r"[unclosed", "reason": "bad regex"},
                {"reason": "missing pattern"},
                "not a dict",
            ],
        )
        patterns = load_local_patterns(path)
        assert len(patterns) == 1
        out = capsys.readouterr().out
        assert out.count("⚠ Skipping") == 3


class TestLocalPatternsInDetection:
    def test_local_pattern_flags_title(self, tmp_path):
        path = write_patterns(
            tmp_path / "p.json",
            [{"pattern": r"gardening", "reason": "Off-topic subject"}],
        )
        patterns = load_local_patterns(path)
        reasons = is_broken_title("A Gardening Almanac", "Smith", "f.pdf", patterns)
        assert "Off-topic subject" in reasons

    def test_no_local_patterns_is_default(self):
        assert (
            is_broken_title("Elements of Statistical Learning", "Hastie", "f.pdf") == []
        )


class TestBuiltInPatterns:
    """The built-in patterns must stay generic: authoring-tool signatures and
    structural damage, never subject matter from any one collection."""

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Microsoft Word - Document1", "Metadata artifact/placeholder"),
            ("Microsoft PowerPoint - deck", "Metadata artifact/placeholder"),
            ("Combined DVI Document", "Metadata artifact/placeholder"),
            ("untitled", "Generic placeholder title"),
            ("Untitled Document", "Generic placeholder title"),
            ("My title", "Generic placeholder title"),
            ("Slide 12", "Very short/broken title"),
            ("Lecture 3", "Very short/broken title"),
            ("report.docx", "Contains file extension"),
            ("deck.pptx", "Contains file extension"),
            ("9781234567890", "Title is an ISBN code"),
            ("Some_Extracted_Title", "Contains underscores - likely extraction error"),
            ("A COMPLETELY SHOUTED TITLE", "All CAPS - formatting error"),
            ("Broken\nTitle", "Title contains line break"),
        ],
    )
    def test_generic_patterns_are_flagged(self, title, expected):
        assert expected in is_broken_title(title, "Author", "f.pdf")

    @pytest.mark.parametrize(
        "title",
        [
            "Elements of Statistical Learning",
            "Attention Is All You Need",
            "A Gardening Almanac",
        ],
    )
    def test_legitimate_titles_are_clean(self, title):
        assert is_broken_title(title, "Author", "f.pdf") == []

    @pytest.mark.parametrize(
        "title",
        [
            "Kernel Methods",
            "Regularisation",
            "Widget Alignment Document",
            "Numismatics of the Lower Rhine",
            "Sourdough Fermentation",
        ],
    )
    def test_subject_matter_alone_is_never_flagged(self, title):
        """Guard against collection-derived literals creeping back into tracked
        source. A title must only be flagged for *structural* damage or an
        authoring-tool signature -- never for what it is about. Anything
        topic-based belongs in the untracked local patterns file.

        The titles here are invented on purpose: naming the real ones would
        reintroduce into tracked source exactly what this guard exists to keep
        out. Short bare noun phrases and `<Topic> Document` shapes are included
        because those were the shapes previously hardcoded."""
        assert is_broken_title(title, "Author", "f.pdf") == []
