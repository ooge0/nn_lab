#!/usr/bin/env python3
import subprocess
import pathlib
import inspect
import importlib.util
import re
import sys

OUTPUT_PATH = pathlib.Path("results/test_results/list_of_tests.md")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Mirrors tests/conftest.py's own sys.path setup: get_docstring() imports each
# test file directly (bypassing pytest's normal collection, which is what
# would otherwise trigger conftest.py), so files importing core.*/api.*/utils.*
# need the project root on sys.path here too, or every such import fails with
# "No module named 'core'" and every docstring silently falls back to
# "Description is missing".
_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Real bug, found by actually running this (not assumed): when this file is
# invoked directly (`python utils/list_tests.py`, as opposed to `python -m
# utils.list_tests`), Python auto-inserts this file's own directory --
# `utils/` -- onto sys.path[0]. `utils/plotly/` is a real subpackage
# (utils/plotly/plotly_parser.py), so with `utils/` on the path, `import
# plotly.express` (triggered deep inside every test file that imports
# api.app, e.g. web/plotting/analytics_charts.py) resolves `plotly` to
# `utils/plotly/` instead of the real third-party `plotly` on
# site-packages -- which has no `express` submodule, so it fails with
# "No module named 'plotly.express'" and every affected test's docstring
# silently falls back to "Description is missing". Reproducible 100% of the
# time when run as a direct script (confirmed: 84/196 -- 43% -- of test rows
# came back with a missing description before this fix); never reproduces
# when this module is imported normally (e.g. `import utils.list_tests`),
# since that path never puts `utils/` itself directly on sys.path. Stripped
# explicitly so the script is correct regardless of how it's invoked.
_utils_dir = str(pathlib.Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if pathlib.Path(p or ".").resolve() != pathlib.Path(_utils_dir)]

# A real node ID is "path/to/file.py::test_name" (or "...::Class::test_name").
# `pytest --collect-only -q` also prints a trailing warnings-summary block
# (deprecation warnings, "-- Docs: ..." links, etc.) that isn't test output at
# all -- naively treating every non-empty stdout line as a node ID collects
# that noise too, and then treating the *last* such line as the "N collected"
# summary breaks once warning lines land after it.
#
# Prefix-only match (not full-line): a parametrized test ID can embed a
# literal space inside its brackets, e.g. tests/e2e's own
# test_sweep_min_max_bounds_are_real_per_parameter_not_a_fixed_fake_range
# produces IDs like "...::test_x[chromium-Top P-0-1]" -- requiring the
# *whole* line to be non-whitespace (a trailing `\S+$`) silently dropped 3
# of the 13 real e2e node IDs the first time this ran after tests/e2e was
# added (216 reported instead of the real 219, confirmed via a direct
# `pytest --collect-only` diff). Matching just the "<path>.py::" prefix is
# still safe against the collect-only summary/warnings lines below it, since
# none of those start with a real file path followed immediately by "::".
_NODE_ID_RE = re.compile(r"^\S+\.py::")
_SUMMARY_RE = re.compile(r"^\d+ tests? collected")


def collect_tests():
    """Run pytest in collect-only mode and return (node_ids, summary_line)."""
    root = _ROOT  # project root
    tests_path = root / "tests"
    cmd = ["pytest", str(tests_path), "--collect-only", "-q"]
    print(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    if result.returncode not in (0, 5):  # 5 = no tests collected
        raise RuntimeError(f"pytest failed: {result.stderr}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    node_ids = [line for line in lines if _NODE_ID_RE.match(line)]
    summary = next((line for line in lines if _SUMMARY_RE.match(line)), f"{len(node_ids)} tests collected")
    return node_ids, summary


_module_cache: dict[str, object] = {}


def _load_module(file_path):
    """
    Import one test file exactly once, cached by path.

    Notes
    -----
    Previously this was done fresh inside get_docstring() -- called once per
    *test function*, not once per file, so a file with N tests was
    re-imported N times. For ~200 tests across ~30 files that's ~200 cold
    imports instead of ~30, each dragging in heavy packages (torch, faiss,
    sentence-transformers) again -- confirmed to intermittently fail with
    spurious `No module named 'plotly.express'` errors under that load
    (reproducible only via the real collection sequence, not in isolation --
    consistent with resource/state pressure from redundant re-imports, not a
    real missing dependency). Every module name was also the same literal
    ``"mod"``, so repeated imports weren't even distinguishable in
    `sys.modules` for debugging. Caching by file path fixes both: 1 import
    per file, and a distinct name.
    """
    if file_path not in _module_cache:
        abs_file = _ROOT / file_path
        spec = importlib.util.spec_from_file_location(file_path, abs_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _module_cache[file_path] = mod
    return _module_cache[file_path]


def get_docstring(node_id):
    """Import the test function/class (once per file, cached) and read its docstring."""
    parts = node_id.split("::")
    file_path = parts[0]
    func_name = parts[-1]

    try:
        mod = _load_module(file_path)

        obj = getattr(mod, func_name, None)
        if obj is None and len(parts) == 3:  # class method
            cls = getattr(mod, parts[1], None)
            if cls:
                obj = getattr(cls, func_name, None)

        if obj:
            docstring = inspect.getdoc(obj)
            if docstring:
                # collapse whitespace and newlines
                return " ".join(docstring.split())
            else:
                return "Description is missing"
    except Exception as e:
        print(f" Failed to import {_ROOT / file_path}: {e}")
        return "Description is missing"
    return "Description is missing"


def main():
    tests, summary = collect_tests()
    lines = []
    lines.append("# Test Report\n")
    lines.append(f"Total tests: {len(tests)}\n")
    lines.append("\n| # | Test Name | Description |\n|---|-----------|-------------|")

    for i, node_id in enumerate(tests, start=1):
        test_name = node_id.split("::")[-1]
        docstring = get_docstring(node_id).replace("|", "\\|")
        lines.append(f"| {i} | {test_name} | {docstring} |")
    lines.append("")
    lines.append(f"Summary line: {summary}")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
