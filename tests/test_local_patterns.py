"""Tests for the optional local title-pattern loader in find_broken_titles."""

import json

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
