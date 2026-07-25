"""Tests for src/lib/config.py path expansion (B1: literal `~` in .env)."""

import importlib
import os

import src.lib.config as config

_ENV_KEYS = (
    "HOME",
    "DOCS_BASE_DIR",
    "PROCESSOR_DIR",
    "REFERENCE_DIR",
    "QUARANTINE_DIR",
    "TODO_DIR",
    "MARKDOWN_DIR",
    "REFERENCES_FILE",
    "REFERENCES_JSON",
    "JSON_OUTPUT_DIR",
)


class ReloadedConfig:
    """Reloads config.py under a patched HOME/env, then restores the
    original environment and reloads again on exit. `importlib.reload`
    mutates the shared config module in place, so pytest's monkeypatch
    (which only undoes attribute/env changes, not module reloads) can't
    clean this up on its own."""

    def __init__(self, tmp_home, **env_overrides):
        self.tmp_home = tmp_home
        self.env_overrides = env_overrides
        self._saved = {}

    def __enter__(self):
        for key in _ENV_KEYS:
            self._saved[key] = os.environ.get(key)
        os.environ["HOME"] = str(self.tmp_home)
        for key, value in self.env_overrides.items():
            os.environ[key] = value
        return importlib.reload(config)

    def __exit__(self, *exc_info):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(config)


class TestExpandUser:
    def test_base_tilde_paths_are_expanded(self, tmp_path):
        with ReloadedConfig(
            tmp_path, DOCS_BASE_DIR="~/documents", PROCESSOR_DIR="~/paper-chase"
        ) as reloaded:
            assert str(reloaded.DOCS_BASE_DIR) == str(tmp_path / "documents")
            assert str(reloaded.PROCESSOR_DIR) == str(tmp_path / "paper-chase")
            assert not (tmp_path / "~").exists()

    def test_derived_vars_with_literal_tilde_are_expanded(self, tmp_path):
        """Like `.env.example`, a derived var can carry its own literal
        `~/...` value (e.g. `REFERENCE_DIR=${DOCS_BASE_DIR}/reference`
        resolved against a tilde `DOCS_BASE_DIR`) -- dotenv hands config.py
        that literal string before Path() ever sees it, so expanding only
        the base vars (DOCS_BASE_DIR/PROCESSOR_DIR) is not enough; every
        derived var needs its own `.expanduser()`."""
        with ReloadedConfig(
            tmp_path,
            DOCS_BASE_DIR="~/documents",
            REFERENCE_DIR="~/documents/reference",
            JSON_OUTPUT_DIR="~/documents/json-output",
        ) as reloaded:
            assert "~" not in str(reloaded.REFERENCE_DIR)
            assert str(reloaded.REFERENCE_DIR) == str(
                tmp_path / "documents" / "reference"
            )
            assert "~" not in str(reloaded.JSON_OUTPUT_DIR)
            assert str(reloaded.JSON_OUTPUT_DIR) == str(
                tmp_path / "documents" / "json-output"
            )
            assert not (tmp_path / "~").exists()
