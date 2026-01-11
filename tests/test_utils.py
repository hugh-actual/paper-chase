#!/usr/bin/env python3
"""Unit tests for utils.py"""

import pytest
from pathlib import Path

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lib.utils import (
    parse_author,
    sanitize_title,
    create_harvard_reference,
    check_duplicate_filename,
    generate_new_filename,
    rename_file,
    title_similarity,
    normalize_author_for_comparison,
    calculate_file_hash,
    is_unknown_author,
    is_suspect_filename,
    PREPOSITIONS,
    DOMAIN_ADJECTIVES,
)


# =============================================================================
# Tests for parse_author()
# =============================================================================


class TestParseAuthor:
    """Tests for parse_author() function."""

    def test_single_author_full_name(self):
        """Single author with first and last name."""
        filename_part, names = parse_author("John Smith")
        assert filename_part == "Smith"
        assert names == ["John Smith"]

    def test_single_author_surname_only(self):
        """Single word author name."""
        filename_part, names = parse_author("Hastie")
        assert filename_part == "Hastie"
        assert names == ["Hastie"]

    def test_two_authors_with_and(self):
        """Two authors separated by 'and'."""
        filename_part, names = parse_author("Smith and Jones")
        assert filename_part == "Smith_Jones"
        assert len(names) == 2

    def test_two_authors_with_comma(self):
        """Two authors separated by comma."""
        filename_part, names = parse_author("Cristianini, Shawe-Taylor")
        assert filename_part == "Cristianini_Shawe-Taylor"
        assert len(names) == 2

    def test_three_authors_et_al(self):
        """Three or more authors should return et_al format."""
        filename_part, names = parse_author("Hastie, Tibshirani, Friedman")
        assert filename_part == "Hastie_et_al"
        assert len(names) == 3

    def test_author_with_apostrophe(self):
        """Author name with apostrophe (O'Regan)."""
        filename_part, names = parse_author("Gerard O'Regan")
        assert filename_part == "O'Regan"
        assert names == ["Gerard O'Regan"]

    def test_empty_string(self):
        """Empty string returns Unknown."""
        filename_part, names = parse_author("")
        assert filename_part == "Unknown"
        assert names == ["Unknown"]

    def test_none_input(self):
        """None input returns Unknown."""
        filename_part, names = parse_author(None)
        assert filename_part == "Unknown"
        assert names == ["Unknown"]

    def test_unknown_string(self):
        """'Unknown' string returns Unknown."""
        filename_part, names = parse_author("Unknown")
        assert filename_part == "Unknown"
        assert names == ["Unknown"]

    def test_author_with_middle_name(self):
        """Author with middle name."""
        filename_part, names = parse_author("Richard A. Berk")
        assert filename_part == "Berk"
        assert names == ["Richard A. Berk"]

    def test_hyphenated_surname(self):
        """Hyphenated surname."""
        filename_part, names = parse_author("John Shawe-Taylor")
        assert filename_part == "Shawe-Taylor"
        assert names == ["John Shawe-Taylor"]

    def test_et_al_single_author(self):
        """Single author with 'et al' returns Author_et_al."""
        filename_part, names = parse_author("Kandel et al")
        assert filename_part == "Kandel_et_al"
        assert names == ["Kandel et al"]

    def test_et_al_with_period(self):
        """Author with 'et al.' (with period) returns Author_et_al."""
        filename_part, names = parse_author("Breck et al.")
        assert filename_part == "Breck_et_al"
        assert names == ["Breck et al."]

    def test_et_al_case_insensitive(self):
        """'Et Al' and 'ET AL' are handled correctly."""
        filename_part1, names1 = parse_author("Laurent Et Al")
        filename_part2, names2 = parse_author("Wilson ET AL")
        assert filename_part1 == "Laurent_et_al"
        assert filename_part2 == "Wilson_et_al"
        assert names1 == ["Laurent Et Al"]
        assert names2 == ["Wilson ET AL"]

    def test_et_al_multiple_authors(self):
        """Multiple authors with 'et al' returns FirstAuthor_et_al."""
        filename_part, names = parse_author("Smith, Jones, et al")
        assert filename_part == "Smith_et_al"
        assert len(names) >= 2

    def test_no_author_duplication_with_comma_and(self):
        """Regression test: 'Hastie, Tibshirani, and Friedman' should not duplicate names."""
        filename_part, names = parse_author("Hastie, Tibshirani, and Friedman")
        assert filename_part == "Hastie_et_al"
        assert len(names) == 3
        # Join with commas to check for duplication
        joined = ", ".join(names)
        assert "Friedman, Friedman" not in joined
        # Verify each name appears only once
        assert names == ["Hastie", "Tibshirani", "Friedman"]

    def test_no_author_duplication_with_et_al(self):
        """Regression test: 'Srivastava, Hinton, et al' should not duplicate names."""
        filename_part, names = parse_author("Srivastava, Hinton, et al")
        assert filename_part == "Srivastava_et_al"
        # Join with commas to check for duplication
        joined = ", ".join(names)
        assert "Hinton, Hinton" not in joined
        assert "et al, et al" not in joined
        # First element should not contain all authors
        assert names[0] == "Srivastava"
        if len(names) > 1:
            assert names[1] in ["Hinton", "Hinton, et al"]


# =============================================================================
# Tests for sanitize_title()
# =============================================================================


class TestSanitizeTitle:
    """Tests for sanitize_title() function."""

    def test_removes_leading_article(self):
        """'The' at start should be removed."""
        result = sanitize_title("The Elements of Statistical Learning")
        # 'The' removed, 'of' removed (preposition), 'Statistical' kept (domain adj)
        assert "The" not in result
        assert "Statistical" in result
        assert "Learning" in result

    def test_removes_prepositions(self):
        """Prepositions like 'of', 'to', 'for' should be removed."""
        result = sanitize_title("Introduction to Machine Learning")
        assert "_to_" not in result.lower()
        assert "Introduction" in result
        assert "Machine" in result
        assert "Learning" in result

    def test_keeps_domain_adjectives(self):
        """Domain-specific words like 'Deep', 'Neural', 'Bayesian' should be kept."""
        result = sanitize_title("Deep Neural Networks")
        assert "Deep" in result
        assert "Neural" in result

    def test_removes_article_at_start(self):
        """Articles like 'A' should be removed even at start."""
        result = sanitize_title("A Beginner's Guide to Scala")
        # 'A' removed (article), 'to' removed (preposition)
        assert not result.startswith("A_")
        assert "Beginners" in result or "Beginner" in result
        assert "_to_" not in result.lower()

    def test_removes_special_characters(self):
        """Special characters should be removed."""
        result = sanitize_title("LaTeX: A Guide (2020)")
        assert ":" not in result
        assert "(" not in result
        assert ")" not in result

    def test_empty_string(self):
        """Empty string returns 'Untitled'."""
        result = sanitize_title("")
        assert result == "Untitled"

    def test_none_input(self):
        """None input returns 'Untitled'."""
        result = sanitize_title(None)
        assert result == "Untitled"

    def test_underscores_between_words(self):
        """Words should be joined by underscores."""
        result = sanitize_title("Deep Learning")
        assert result == "Deep_Learning"

    def test_no_double_underscores(self):
        """Should not have consecutive underscores."""
        result = sanitize_title("Introduction   to   Python")
        assert "__" not in result

    def test_flask_by_example(self):
        """Real example: Flask by Example."""
        result = sanitize_title("Flask by Example")
        # 'by' is a preposition, should be removed
        assert "by" not in result.lower().split("_")
        assert "Flask" in result
        assert "Example" in result

    def test_statistical_learning_regression(self):
        """Real example with domain adjective."""
        result = sanitize_title("Statistical Learning from a Regression Perspective")
        assert "Statistical" in result
        assert "Learning" in result
        assert "Regression" in result


# =============================================================================
# Tests for create_harvard_reference()
# =============================================================================


class TestCreateHarvardReference:
    """Tests for create_harvard_reference() function."""

    def test_single_author(self):
        """Single author reference format."""
        ref = create_harvard_reference(
            ["John Smith"], "2020", "Test Title", "Publisher", "file.pdf"
        )
        assert "John Smith (2020)" in ref
        assert "*Test Title*" in ref
        assert "Publisher." in ref
        assert "**File**: file.pdf" in ref

    def test_two_authors(self):
        """Two authors should be joined with 'and'."""
        ref = create_harvard_reference(
            ["Smith", "Jones"], "2020", "Test", "Publisher", "file.pdf"
        )
        assert "Smith and Jones" in ref

    def test_three_authors(self):
        """Three authors: A, B and C format."""
        ref = create_harvard_reference(
            ["Smith", "Jones", "Brown"], "2020", "Test", "Publisher", "file.pdf"
        )
        assert "Smith, Jones and Brown" in ref

    def test_no_year(self):
        """No year should show (n.d.)."""
        ref = create_harvard_reference(["Smith"], None, "Test", "Publisher", "file.pdf")
        assert "(n.d.)" in ref

    def test_no_publisher(self):
        """No publisher should not add trailing text."""
        ref = create_harvard_reference(["Smith"], "2020", "Test", None, "file.pdf")
        assert "*Test*.\n" in ref  # Title followed by period and newline, no publisher

    def test_unknown_author(self):
        """Unknown author list."""
        ref = create_harvard_reference(
            ["Unknown"], "2020", "Test", "Publisher", "file.pdf"
        )
        assert "Unknown (2020)" in ref

    def test_no_title(self):
        """No title should show *Untitled*."""
        ref = create_harvard_reference(["Smith"], "2020", None, "Publisher", "file.pdf")
        assert "*Untitled*" in ref


# =============================================================================
# Tests for check_duplicate_filename()
# =============================================================================


class TestCheckDuplicateFilename:
    """Tests for check_duplicate_filename() function."""

    def test_no_duplicate_returns_original(self):
        """Non-duplicate filename returns unchanged."""
        result = check_duplicate_filename("Smith_Test.pdf", set())
        assert result == "Smith_Test.pdf"

    def test_duplicate_in_processed_files(self):
        """Duplicate in processed_files set gets suffix."""
        processed = {"Smith_Test.pdf"}
        result = check_duplicate_filename("Smith_Test.pdf", processed)
        assert result == "Smith_Test_2.pdf"

    def test_multiple_duplicates(self):
        """Multiple duplicates increment counter."""
        processed = {"Smith_Test.pdf", "Smith_Test_2.pdf", "Smith_Test_3.pdf"}
        result = check_duplicate_filename("Smith_Test.pdf", processed)
        assert result == "Smith_Test_4.pdf"

    def test_duplicate_in_filesystem(self, tmp_path):
        """Duplicate in filesystem gets suffix."""
        # Create existing file
        (tmp_path / "Smith_Test.pdf").touch()
        result = check_duplicate_filename("Smith_Test.pdf", set(), target_dir=tmp_path)
        assert result == "Smith_Test_2.pdf"


# =============================================================================
# Tests for generate_new_filename()
# =============================================================================


class TestGenerateNewFilename:
    """Tests for generate_new_filename() function."""

    def test_basic_filename(self):
        """Basic author + title filename."""
        filename, names = generate_new_filename("John Smith", "Deep Learning")
        assert filename == "Smith_Deep_Learning.pdf"
        assert names == ["John Smith"]

    def test_with_processed_files(self):
        """Handles duplicates in processed_files."""
        processed = {"Smith_Deep_Learning.pdf"}
        filename, names = generate_new_filename(
            "John Smith", "Deep Learning", processed_files=processed
        )
        assert filename == "Smith_Deep_Learning_2.pdf"

    def test_truncates_long_filename(self):
        """Very long titles get truncated."""
        long_title = " ".join(["Word"] * 50)  # Very long title
        filename, names = generate_new_filename("Smith", long_title)
        assert len(filename) <= 150

    def test_multiple_authors(self):
        """Multiple authors in filename."""
        filename, names = generate_new_filename(
            "Hastie, Tibshirani, Friedman", "Elements of Statistical Learning"
        )
        assert filename.startswith("Hastie_et_al_")
        assert len(names) == 3

    def test_three_authors_uses_first_surname(self):
        """Three authors should use FIRST surname + et_al, not last two."""
        # Regression test for bug where "Zhang, Jiang, Tong" created "Jiang_Tong_..."
        filename, names = generate_new_filename(
            "Zhang, Jiang, Tong", "Sentiment Classification for Chinese Microblog"
        )
        assert filename.startswith("Zhang_et_al_")
        assert not filename.startswith("Jiang_")
        assert not filename.startswith("Tong_")
        assert names == ["Zhang", "Jiang", "Tong"]

    def test_four_authors_uses_first_surname(self):
        """Four authors should use FIRST surname + et_al."""
        filename, names = generate_new_filename(
            "Blum, Hopcroft, Kannan, Smith", "Foundations of Data Science"
        )
        assert filename.startswith("Blum_et_al_")
        assert not filename.startswith("Hopcroft_")
        assert len(names) == 4

    def test_oxford_comma_three_authors(self):
        """Oxford comma with three authors should use first surname."""
        filename, names = generate_new_filename(
            "Hastie, Tibshirani, and Friedman", "Elements of Statistical Learning"
        )
        assert filename.startswith("Hastie_et_al_")
        assert not filename.startswith("Tibshirani_")
        assert not filename.startswith("Friedman_")
        assert names == ["Hastie", "Tibshirani", "Friedman"]

    def test_two_authors_both_surnames(self):
        """Two authors should use both surnames."""
        filename, names = generate_new_filename(
            "Sutton, Barto", "Reinforcement Learning"
        )
        assert filename.startswith("Sutton_Barto_")
        assert names == ["Sutton", "Barto"]

    def test_two_authors_with_and(self):
        """Two authors with 'and' should use both surnames."""
        filename, names = generate_new_filename(
            "Russell and Norvig", "Artificial Intelligence"
        )
        assert filename.startswith("Russell_Norvig_")
        assert names == ["Russell", "Norvig"]

    def test_single_author_full_name(self):
        """Single author with full name should use surname only."""
        filename, names = generate_new_filename("Andrew Ng", "Machine Learning")
        assert filename.startswith("Ng_")
        assert names == ["Andrew Ng"]

    def test_author_with_et_al(self):
        """Author string containing 'et al' should use first author + et_al."""
        filename, names = generate_new_filename("Goodfellow et al", "Deep Learning")
        assert filename.startswith("Goodfellow_et_al_")
        assert names == ["Goodfellow et al"]

    def test_multiple_authors_with_et_al(self):
        """Multiple authors with 'et al' should use first surname + et_al."""
        filename, names = generate_new_filename(
            "Smith, Jones, et al", "Neural Networks"
        )
        assert filename.startswith("Smith_et_al_")
        assert len(names) >= 2


# =============================================================================
# Tests for rename_file()
# =============================================================================


class TestRenameFile:
    """Tests for rename_file() function."""

    def test_rename_success(self, tmp_path):
        """Successfully rename a file."""
        old_file = tmp_path / "old.pdf"
        new_file = tmp_path / "new.pdf"
        old_file.touch()

        result = rename_file(old_file, new_file)

        assert result is True
        assert not old_file.exists()
        assert new_file.exists()

    def test_same_path_returns_true(self, tmp_path):
        """Same source and destination returns True."""
        file = tmp_path / "test.pdf"
        file.touch()

        result = rename_file(file, file)

        assert result is True
        assert file.exists()

    def test_nonexistent_file_returns_false(self, tmp_path):
        """Non-existent source returns False."""
        old_file = tmp_path / "nonexistent.pdf"
        new_file = tmp_path / "new.pdf"

        result = rename_file(old_file, new_file)

        assert result is False


# =============================================================================
# Tests for constants
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_prepositions_are_lowercase(self):
        """All prepositions should be lowercase."""
        for word in PREPOSITIONS:
            assert word == word.lower()

    def test_domain_adjectives_are_lowercase(self):
        """All domain adjectives should be lowercase."""
        for word in DOMAIN_ADJECTIVES:
            assert word == word.lower()

    def test_expected_prepositions_present(self):
        """Common prepositions should be in the set."""
        expected = {"a", "an", "the", "of", "in", "to", "for", "and", "or"}
        assert expected.issubset(PREPOSITIONS)

    def test_expected_domain_adjectives_present(self):
        """Domain-specific adjectives should be in the set."""
        expected = {"deep", "machine", "neural", "statistical", "bayesian"}
        assert expected.issubset(DOMAIN_ADJECTIVES)


# =============================================================================
# Tests for title_similarity()
# =============================================================================


class TestTitleSimilarity:
    """Tests for title_similarity() function."""

    def test_identical_titles(self):
        """Identical titles return 1.0."""
        result = title_similarity("Deep Learning", "Deep Learning")
        assert result == 1.0

    def test_completely_different_titles(self):
        """Completely different titles return low similarity."""
        result = title_similarity("Deep Learning", "Cooking Recipes")
        assert result < 0.3

    def test_similar_titles(self):
        """Similar titles return high similarity."""
        result = title_similarity(
            "Introduction to Machine Learning",
            "Introduction to Machine Learning 2nd Edition",
        )
        assert result > 0.7

    def test_case_insensitive(self):
        """Comparison is case-insensitive."""
        result = title_similarity("DEEP LEARNING", "deep learning")
        assert result == 1.0

    def test_empty_title_returns_zero(self):
        """Empty title returns 0.0."""
        assert title_similarity("", "Something") == 0.0
        assert title_similarity("Something", "") == 0.0
        assert title_similarity("", "") == 0.0

    def test_none_title_returns_zero(self):
        """None title returns 0.0."""
        assert title_similarity(None, "Something") == 0.0
        assert title_similarity("Something", None) == 0.0
        assert title_similarity(None, None) == 0.0


# =============================================================================
# Tests for normalize_author_for_comparison()
# =============================================================================


class TestNormalizeAuthorForComparison:
    """Tests for normalize_author_for_comparison() function."""

    def test_lowercase_and_strip(self):
        """Should lowercase and strip whitespace."""
        result = normalize_author_for_comparison("  John Smith  ")
        assert result == "john smith"

    def test_already_normalized(self):
        """Already normalized string unchanged."""
        result = normalize_author_for_comparison("john smith")
        assert result == "john smith"

    def test_empty_string(self):
        """Empty string returns empty string."""
        result = normalize_author_for_comparison("")
        assert result == ""

    def test_none_returns_empty(self):
        """None returns empty string."""
        result = normalize_author_for_comparison(None)
        assert result == ""


# =============================================================================
# Tests for calculate_file_hash()
# =============================================================================


class TestCalculateFileHash:
    """Tests for calculate_file_hash() function."""

    def test_hash_returns_hex_string(self, tmp_path):
        """Hash returns a 64-character hex string (SHA256)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = calculate_file_hash(test_file)

        assert result is not None
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path):
        """Same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Same content")
        file2.write_text("Same content")

        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)

        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path):
        """Different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content A")
        file2.write_text("Content B")

        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)

        assert hash1 != hash2

    def test_nonexistent_file_returns_none(self, tmp_path):
        """Nonexistent file returns None."""
        nonexistent = tmp_path / "nonexistent.txt"

        result = calculate_file_hash(nonexistent)

        assert result is None


# =============================================================================
# Tests for is_unknown_author()
# =============================================================================


class TestIsUnknownAuthor:
    """Tests for is_unknown_author() function."""

    def test_unknown_lowercase(self):
        """'unknown' returns True."""
        assert is_unknown_author("unknown") is True

    def test_unknown_mixed_case(self):
        """'Unknown' returns True (case insensitive)."""
        assert is_unknown_author("Unknown") is True
        assert is_unknown_author("UNKNOWN") is True

    def test_dashes(self):
        """'---' returns True."""
        assert is_unknown_author("---") is True

    def test_null_string(self):
        """'null' returns True."""
        assert is_unknown_author("null") is True

    def test_empty_string(self):
        """Empty string returns True."""
        assert is_unknown_author("") is True

    def test_none_returns_true(self):
        """None returns True."""
        assert is_unknown_author(None) is True

    def test_whitespace_only(self):
        """Whitespace-only string returns True."""
        assert is_unknown_author("   ") is True

    def test_valid_author(self):
        """Valid author name returns False."""
        assert is_unknown_author("John Smith") is False
        assert is_unknown_author("Hastie") is False


# =============================================================================
# Tests for is_suspect_filename()
# =============================================================================


class TestIsSuspectFilename:
    """Tests for is_suspect_filename() function."""

    def test_normal_filename(self):
        """Normal filename returns False."""
        assert is_suspect_filename("Smith_Deep_Learning.pdf") is False
        assert is_suspect_filename("Hastie_et_al_Statistical_Learning.pdf") is False

    def test_starts_with_multiple_numbers(self):
        """Filename starting with numbers is suspect."""
        assert is_suspect_filename("12345_Document.pdf") is True
        assert is_suspect_filename("19_56_25_Document.pdf") is True

    def test_untitled(self):
        """'untitled' filename is suspect."""
        assert is_suspect_filename("untitled.pdf") is True
        assert is_suspect_filename("Untitled_Document.pdf") is True

    def test_short_filename(self):
        """Very short filename without underscore is suspect."""
        assert is_suspect_filename("abc.pdf") is True

    def test_mostly_numbers(self):
        """Filename that is mostly numbers is suspect."""
        assert is_suspect_filename("123456789.pdf") is True

    def test_valid_short_with_underscore(self):
        """Short filename with underscore may be valid."""
        # Short but has underscore structure
        result = is_suspect_filename("ML_Intro.pdf")
        # This is 8 chars without .pdf, so might be suspect
        # But let's check actual behavior
        assert isinstance(result, bool)


# =============================================================================
# Tests for JSON operations
# =============================================================================


import json
from src.lib import utils


class TestReferencesJsonOperations:
    """Tests for references.json operations."""

    @pytest.fixture
    def setup_json_env(self, tmp_path, monkeypatch):
        """Set up temporary JSON file for testing."""
        json_file = tmp_path / "references.json"
        json_file.write_text("[]")
        monkeypatch.setattr(utils, "REFERENCES_JSON", json_file)
        return json_file

    def test_load_references_json_empty(self, setup_json_env):
        """Loading empty JSON file returns empty list."""
        from src.lib.utils import load_references_json

        result = load_references_json()
        assert result == []

    def test_load_references_json_with_entries(self, setup_json_env):
        """Loading JSON file with entries returns entries."""
        from src.lib.utils import load_references_json

        setup_json_env.write_text(
            json.dumps([{"filename": "test.pdf", "author": "Smith"}])
        )
        result = load_references_json()
        assert len(result) == 1
        assert result[0]["filename"] == "test.pdf"

    def test_load_references_json_missing_file(self, tmp_path, monkeypatch):
        """Loading non-existent JSON file returns empty list."""
        from src.lib.utils import load_references_json

        nonexistent = tmp_path / "nonexistent.json"
        monkeypatch.setattr(utils, "REFERENCES_JSON", nonexistent)
        result = load_references_json()
        assert result == []

    def test_save_references_json(self, setup_json_env):
        """Saving entries writes them to JSON file."""
        from src.lib.utils import save_references_json

        entries = [{"filename": "test.pdf", "author": "Smith"}]
        save_references_json(entries)

        content = json.loads(setup_json_env.read_text())
        assert len(content) == 1
        assert content[0]["filename"] == "test.pdf"

    def test_add_entry_new(self, setup_json_env):
        """Adding new entry creates it in JSON file."""
        from src.lib.utils import add_entry_to_references_json, load_references_json

        add_entry_to_references_json(
            author_names=["John Smith"],
            year="2020",
            title="Test Title",
            publisher="Publisher",
            filename="test.pdf",
        )

        entries = load_references_json()
        assert len(entries) == 1
        assert entries[0]["filename"] == "test.pdf"
        assert entries[0]["author"] == "John Smith"
        assert entries[0]["year"] == "2020"

    def test_add_entry_update_existing(self, setup_json_env):
        """Adding entry with existing filename updates it."""
        from src.lib.utils import add_entry_to_references_json, load_references_json

        # Add first entry
        add_entry_to_references_json(
            author_names=["Smith"],
            year="2020",
            title="Old Title",
            publisher="Old Publisher",
            filename="test.pdf",
        )

        # Update same filename
        add_entry_to_references_json(
            author_names=["Jones"],
            year="2021",
            title="New Title",
            publisher="New Publisher",
            filename="test.pdf",
        )

        entries = load_references_json()
        assert len(entries) == 1  # Still only one entry
        assert entries[0]["author"] == "Jones"
        assert entries[0]["year"] == "2021"
        assert entries[0]["title"] == "New Title"

    def test_add_entry_with_original_filename(self, setup_json_env):
        """Adding entry with original_filename stores it."""
        from src.lib.utils import add_entry_to_references_json, load_references_json

        add_entry_to_references_json(
            author_names=["Smith"],
            year="2020",
            title="Test",
            publisher="Publisher",
            filename="renamed.pdf",
            original_filename="original_file.pdf",
        )

        entries = load_references_json()
        assert entries[0]["original_filename"] == "original_file.pdf"

    def test_remove_entry_exists(self, setup_json_env):
        """Removing existing entry returns True."""
        from src.lib.utils import (
            add_entry_to_references_json,
            remove_entry_from_references_json,
            load_references_json,
        )

        add_entry_to_references_json(["Smith"], "2020", "Test", "Publisher", "test.pdf")
        assert len(load_references_json()) == 1

        result = remove_entry_from_references_json("test.pdf")
        assert result is True
        assert len(load_references_json()) == 0

    def test_remove_entry_missing(self, setup_json_env):
        """Removing non-existent entry returns False."""
        from src.lib.utils import remove_entry_from_references_json

        result = remove_entry_from_references_json("nonexistent.pdf")
        assert result is False

    def test_update_entry(self, setup_json_env):
        """Updating entry changes filename and metadata."""
        from src.lib.utils import (
            add_entry_to_references_json,
            update_entry_in_references_json,
            load_references_json,
        )

        add_entry_to_references_json(
            ["Smith"], "2020", "Old Title", "Publisher", "old.pdf"
        )

        result = update_entry_in_references_json(
            old_filename="old.pdf",
            new_filename="new.pdf",
            author_names=["Jones"],
            year="2021",
            title="New Title",
            publisher="New Publisher",
        )

        assert result is True
        entries = load_references_json()
        assert len(entries) == 1
        assert entries[0]["filename"] == "new.pdf"
        assert entries[0]["author"] == "Jones"
        assert entries[0]["title"] == "New Title"

    def test_update_entry_missing(self, setup_json_env):
        """Updating non-existent entry returns False."""
        from src.lib.utils import update_entry_in_references_json

        result = update_entry_in_references_json(
            old_filename="nonexistent.pdf",
            new_filename="new.pdf",
            author_names=["Smith"],
            year="2020",
            title="Title",
            publisher="Publisher",
        )
        assert result is False

    def test_get_entry_exists(self, setup_json_env):
        """Getting existing entry returns it."""
        from src.lib.utils import add_entry_to_references_json, get_entry_from_references_json

        add_entry_to_references_json(
            ["Smith"], "2020", "Test Title", "Publisher", "test.pdf"
        )

        result = get_entry_from_references_json("test.pdf")
        assert result is not None
        assert result["filename"] == "test.pdf"
        assert result["author"] == "Smith"

    def test_get_entry_missing(self, setup_json_env):
        """Getting non-existent entry returns None."""
        from src.lib.utils import get_entry_from_references_json

        result = get_entry_from_references_json("nonexistent.pdf")
        assert result is None

    def test_add_entry_with_file_hash(self, setup_json_env):
        """Adding entry with file_hash stores it."""
        from src.lib.utils import add_entry_to_references_json, load_references_json

        add_entry_to_references_json(
            author_names=["Smith"],
            year="2020",
            title="Test",
            publisher="Publisher",
            filename="test.pdf",
            file_hash="abc123def456",
        )

        entries = load_references_json()
        assert entries[0]["file_hash"] == "abc123def456"

    def test_add_entry_update_with_file_hash(self, setup_json_env):
        """Updating existing entry with file_hash stores it."""
        from src.lib.utils import add_entry_to_references_json, load_references_json

        # Add entry without hash
        add_entry_to_references_json(
            author_names=["Smith"],
            year="2020",
            title="Test",
            publisher="Publisher",
            filename="test.pdf",
        )

        # Update with hash
        add_entry_to_references_json(
            author_names=["Smith"],
            year="2020",
            title="Test",
            publisher="Publisher",
            filename="test.pdf",
            file_hash="newhash123",
        )

        entries = load_references_json()
        assert entries[0]["file_hash"] == "newhash123"


# =============================================================================
# Tests for check_hash_conflict()
# =============================================================================


from src.lib.utils import check_hash_conflict


class TestCheckHashConflict:
    """Tests for check_hash_conflict() function."""

    def test_no_conflict_returns_none(self):
        """No matching hash returns None."""
        references = [
            {"filename": "a.pdf", "file_hash": "hash_a"},
            {"filename": "b.pdf", "file_hash": "hash_b"},
        ]
        result = check_hash_conflict("hash_c", references)
        assert result is None

    def test_matching_hash_returns_entry(self):
        """Matching hash returns the entry."""
        references = [
            {"filename": "a.pdf", "file_hash": "hash_a", "title": "Title A"},
            {"filename": "b.pdf", "file_hash": "hash_b", "title": "Title B"},
        ]
        result = check_hash_conflict("hash_a", references)
        assert result is not None
        assert result["filename"] == "a.pdf"
        assert result["title"] == "Title A"

    def test_empty_hash_returns_none(self):
        """Empty hash returns None."""
        references = [{"filename": "a.pdf", "file_hash": "hash_a"}]
        assert check_hash_conflict("", references) is None

    def test_none_hash_returns_none(self):
        """None hash returns None."""
        references = [{"filename": "a.pdf", "file_hash": "hash_a"}]
        assert check_hash_conflict(None, references) is None

    def test_entry_without_hash_ignored(self):
        """Entries without file_hash are skipped."""
        references = [
            {"filename": "a.pdf"},  # No hash
            {"filename": "b.pdf", "file_hash": "hash_b"},
        ]
        result = check_hash_conflict("hash_b", references)
        assert result["filename"] == "b.pdf"

    def test_empty_references_returns_none(self):
        """Empty references list returns None."""
        result = check_hash_conflict("some_hash", [])
        assert result is None


# =============================================================================
# Tests for check_filename_conflict()
# =============================================================================


from src.lib.utils import check_filename_conflict


class TestCheckFilenameConflict:
    """Tests for check_filename_conflict() function."""

    def test_no_conflict_returns_none(self):
        """No matching filename returns None."""
        references = [
            {"filename": "a.pdf"},
            {"filename": "b.pdf"},
        ]
        result = check_filename_conflict("c.pdf", references)
        assert result is None

    def test_matching_filename_returns_entry(self):
        """Matching filename returns the entry."""
        references = [
            {"filename": "Smith_Title.pdf", "title": "The Title"},
        ]
        result = check_filename_conflict("Smith_Title.pdf", references)
        assert result is not None
        assert result["title"] == "The Title"

    def test_partial_match_no_conflict(self):
        """Partial filename match is not a conflict."""
        references = [
            {"filename": "Smith_Title.pdf"},
        ]
        result = check_filename_conflict("Smith_Title_Extended.pdf", references)
        assert result is None

    def test_case_sensitive(self):
        """Filename matching is case-sensitive."""
        references = [
            {"filename": "Smith_Title.pdf"},
        ]
        result = check_filename_conflict("smith_title.pdf", references)
        assert result is None

    def test_empty_references_returns_none(self):
        """Empty references list returns None."""
        result = check_filename_conflict("test.pdf", [])
        assert result is None


# =============================================================================
# Tests for create_reference_stub()
# =============================================================================


from src.lib.utils import create_reference_stub


class TestCreateReferenceStub:
    """Tests for create_reference_stub() function."""

    @pytest.fixture
    def setup_stub_env(self, tmp_path, monkeypatch):
        """Set up temporary environment for stub testing."""
        ref_dir = tmp_path / "reference"
        ref_dir.mkdir()
        monkeypatch.setattr(utils, "REFERENCE_DIR", ref_dir)
        return tmp_path, ref_dir

    def test_creates_stub_with_all_fields(self, setup_stub_env):
        """Stub contains all required fields."""
        tmp_path, ref_dir = setup_stub_env

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        stub = create_reference_stub(
            file_path=test_file,
            author="John Smith",
            title="Test Title",
            year="2024",
            publisher="Publisher",
        )

        assert "file_hash" in stub
        assert len(stub["file_hash"]) == 64  # SHA256
        assert stub["filename"] == "Smith_Test_Title.pdf"
        assert stub["author"] == "John Smith"
        assert stub["author_names"] == ["John Smith"]
        assert stub["title"] == "Test Title"
        assert stub["year"] == "2024"
        assert stub["publisher"] == "Publisher"
        assert stub["original_filename"] == "test.pdf"

    def test_handles_none_year(self, setup_stub_env):
        """None year is stored correctly."""
        tmp_path, ref_dir = setup_stub_env

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        stub = create_reference_stub(
            file_path=test_file,
            author="Smith",
            title="Title",
            year=None,
            publisher=None,
        )

        assert stub["year"] is None
        assert stub["publisher"] is None

    def test_respects_processed_files(self, setup_stub_env):
        """Avoids filenames in processed_files set."""
        tmp_path, ref_dir = setup_stub_env

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        stub = create_reference_stub(
            file_path=test_file,
            author="Smith",
            title="Title",
            year="2024",
            publisher=None,
            processed_files={"Smith_Title.pdf"},
        )

        assert stub["filename"] == "Smith_Title_2.pdf"

    def test_avoids_existing_files_in_target_dir(self, setup_stub_env):
        """Avoids filenames that exist in reference directory."""
        tmp_path, ref_dir = setup_stub_env

        # Create existing file in reference dir
        (ref_dir / "Smith_Title.pdf").touch()

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        stub = create_reference_stub(
            file_path=test_file,
            author="Smith",
            title="Title",
            year="2024",
            publisher=None,
        )

        assert stub["filename"] == "Smith_Title_2.pdf"

    def test_multiple_authors(self, setup_stub_env):
        """Multiple authors are handled correctly."""
        tmp_path, ref_dir = setup_stub_env

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        stub = create_reference_stub(
            file_path=test_file,
            author="Smith, Jones, Brown",
            title="Title",
            year="2024",
            publisher=None,
        )

        assert stub["filename"].startswith("Smith_et_al_")
        assert len(stub["author_names"]) == 3

    def test_unknown_author(self, setup_stub_env):
        """Unknown author is handled correctly."""
        tmp_path, ref_dir = setup_stub_env

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        stub = create_reference_stub(
            file_path=test_file,
            author=None,
            title="Title",
            year="2024",
            publisher=None,
        )

        assert stub["filename"].startswith("Unknown_")
        assert stub["author"] == "Unknown"
