"""
Unit tests for :mod:`utils.serve_docs` -- pins the one real piece of logic (refusing to start
against a missing/unbuilt docs directory, with a helpful message) rather than the thin
``http.server``/``argparse`` wrapping around it, which is already exercised live (manual smoke
test against a real local port, confirmed 200 + real page bytes served).
"""

import sys

import pytest

from utils import serve_docs


def test_main_raises_system_exit_with_a_helpful_message_when_build_dir_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_docs, "_DOCS_HTML_DIR", tmp_path / "not_built_yet")
    monkeypatch.setattr(sys, "argv", ["serve_docs.py", "--no-browser"])

    with pytest.raises(SystemExit) as exc_info:
        serve_docs.main()

    assert "make html" in str(exc_info.value)


def test_default_docs_html_dir_points_at_the_real_sphinx_build_output_location():
    parts = serve_docs._DOCS_HTML_DIR.parts[-4:]
    assert parts == ("docs", "source", "_build", "html")
