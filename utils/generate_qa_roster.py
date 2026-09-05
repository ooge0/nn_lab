#!/usr/bin/env python3
"""
generate_qa_roster.py
=========================

Regenerates ``docs/source/_qa_test_roster.rst`` (included by ``docs/source/qa.rst``'s "Full test
roster" section) directly from the real, currently-collectible test suite -- one subsection per
real ``test_*.py`` file (module docstring + a Test/Description table, one row per real pytest node
ID including parametrize suffixes), in pytest's own natural collection order (``e2e`` ->
``integration`` -> ``legacy_rag`` -> ``unit``, alphabetical by directory).

Written 2026-09-05 after a doc-review found this file had drifted badly out of sync with the real
suite -- six real test files (``test_api_status_api.py``, ``test_cli_manage.py``,
``test_db_export.py``, ``test_db_export_api.py``, ``test_generate_tag_cloud.py``,
``test_knowledge_graph.py``, ``test_serve_docs.py``, ``test_tabs_chart_resize_e2e.py``) had never
been included at all, because the script that had originally produced this file was never
committed to the repo (a scratchpad tool from an earlier session, per this project's own plan-file
log). This script closes that gap for good: it *is* committed, so "regenerate the roster" is now a
real, repeatable command (``python -m utils.generate_qa_roster``), not a one-off manual patch.

Deliberately reuses :func:`utils.list_tests.collect_tests` and its module-import-caching machinery
rather than re-deriving pytest-collection/AST-docstring logic from scratch -- that logic already
had two real bugs found and fixed (a ``sys.path`` shadowing bug, a parametrize-ID-with-spaces
regex bug); duplicating it here would risk reintroducing either.
"""

import inspect
import pathlib
import sys
import textwrap

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
_utils_dir = str(pathlib.Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if pathlib.Path(p or ".").resolve() != pathlib.Path(_utils_dir)]

from utils.list_tests import _load_module, collect_tests  # noqa: E402  (see sys.path fix above)

OUTPUT_PATH = _ROOT / "docs" / "source" / "_qa_test_roster.rst"


def _module_docstring(file_path: str) -> str:
    mod = _load_module(file_path)
    doc = inspect.getdoc(mod)
    if not doc:
        return ""
    # Collapse each paragraph's internal wrapping, then rewrap at a consistent width -- matches
    # the reflowed-prose style already established in this file, not a raw docstring dump.
    paragraphs = doc.split("\n\n")
    return "\n\n".join(textwrap.fill(" ".join(p.split()), width=78) for p in paragraphs if p.strip())


def _test_description(file_path: str, func_name: str) -> str:
    mod = _load_module(file_path)
    obj = getattr(mod, func_name, None)
    if obj is None:
        return "Description is missing"
    doc = inspect.getdoc(obj)
    return " ".join(doc.split()) if doc else "Description is missing"


def main() -> None:
    node_ids, summary = collect_tests()

    # Group by file, preserving pytest's own first-seen order (its natural collection order --
    # alphabetical by directory, then by file within it -- not re-sorted here).
    files: dict[str, list[str]] = {}
    for node_id in node_ids:
        file_path = node_id.split("::")[0]
        files.setdefault(file_path, []).append(node_id)

    sections = []
    for file_path, ids in files.items():
        rel = file_path.replace("\\", "/")
        header = f"``{rel}`` ({len(ids)} test{'' if len(ids) == 1 else 's'})"
        underline = "~" * (len(header) + 2)  # +2: RST underline must be >= the title's display width
        doc = _module_docstring(file_path)

        rows = []
        for node_id in ids:
            test_name = node_id.split("::")[-1]
            base_func = test_name.split("[")[0]
            desc = _test_description(file_path, base_func).replace("|", "\\|")
            rows.append(f"   * - ``{test_name}``\n     - {desc}")

        table = (
            ".. list-table::\n"
            "   :widths: 45 55\n"
            "   :header-rows: 1\n\n"
            "   * - Test\n     - Description\n" + "\n".join(rows)
        )
        section = f"{header}\n{underline}\n\n{doc}\n\n{table}" if doc else f"{header}\n{underline}\n\n{table}"
        sections.append(section)

    OUTPUT_PATH.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"{summary} -- wrote {len(files)} file sections to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
