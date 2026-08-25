"""
Unit tests for :mod:`utils.generate_tag_cloud` -- pins the glossary-term/module-name extraction and
real-frequency-counting logic against fixed temp fixtures, not the live repo content (so these don't
silently break just because someone adds a new glossary term or module). CLAUDE.md SS7: a script
with real parsing logic gets a real test, even a one-off "run manually" utility script -- the same
discipline already applied to ``utils/list_tests.py``'s own two real bugs found this session.
"""

from utils.generate_tag_cloud import extract_glossary_terms, extract_module_names, real_frequency


def test_extract_glossary_terms_pulls_only_term_lines_not_definitions(tmp_path):
    glossary = tmp_path / "glossary.rst"
    glossary.write_text(
        "Glossary\n"
        "========\n"
        "\n"
        "Some category\n"
        "-----------------\n"
        "\n"
        ".. glossary::\n"
        "   :sorted:\n"
        "\n"
        "   Large Language Model (LLM)\n"
        "      A neural network trained on text.\n"
        "      Second definition line.\n"
        "\n"
        "   Embedding\n"
        "      A dense numeric vector.\n",
        encoding="utf-8",
    )

    terms = extract_glossary_terms(glossary)

    assert terms == ["Large Language Model (LLM)", "Embedding"]


def test_extract_glossary_terms_handles_multiple_glossary_blocks(tmp_path):
    """A page can have more than one .. glossary:: block (this project's real glossary.rst does, one
    per category) -- all of them must be picked up, not just the first."""
    glossary = tmp_path / "glossary.rst"
    glossary.write_text(
        ".. glossary::\n"
        "\n"
        "   Term One\n"
        "      Definition.\n"
        "\n"
        "Some other section\n"
        "----------------------\n"
        "\n"
        ".. glossary::\n"
        "\n"
        "   Term Two\n"
        "      Definition.\n",
        encoding="utf-8",
    )

    terms = extract_glossary_terms(glossary)

    assert terms == ["Term One", "Term Two"]


def test_extract_glossary_terms_on_empty_file_returns_empty_list(tmp_path):
    glossary = tmp_path / "glossary.rst"
    glossary.write_text("Glossary\n========\n", encoding="utf-8")

    assert extract_glossary_terms(glossary) == []


def test_extract_module_names_excludes_init_and_pycache(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "core" / "structured_judge.py").write_text("", encoding="utf-8")
    pycache = tmp_path / "core" / "__pycache__"
    pycache.mkdir()
    (pycache / "structured_judge.cpython-312.pyc").write_bytes(b"")

    names = extract_module_names(tmp_path, ["core"])

    assert names == ["structured judge"]


def test_extract_module_names_replaces_underscores_with_spaces(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "hallucination_check.py").write_text("", encoding="utf-8")

    names = extract_module_names(tmp_path, ["api"])

    assert names == ["hallucination check"]


def test_real_frequency_counts_whole_word_case_insensitive_occurrences(tmp_path):
    (tmp_path / "a.rst").write_text("The Archetype label. Another archetype mention.\n", encoding="utf-8")
    (tmp_path / "b.rst").write_text("No matches here.\n", encoding="utf-8")

    assert real_frequency("archetype", tmp_path) == 2


def test_real_frequency_never_returns_zero_even_for_an_unmentioned_term(tmp_path):
    (tmp_path / "a.rst").write_text("Nothing relevant here.\n", encoding="utf-8")

    assert real_frequency("nonexistent term xyz", tmp_path) == 1
