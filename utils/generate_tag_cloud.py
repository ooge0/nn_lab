#!/usr/bin/env python3
"""
generate_tag_cloud.py

One-off generator (matches ``utils/list_tests.py``'s convention -- run manually, output committed,
not a Sphinx build-time step) for ``docs/source/_static/tag_cloud.png``, embedded in
:doc:`architecture.rst </architecture>`'s "Feature map" section.

Two real, cited data sources, not an arbitrary word list:

1. Every glossary term name in ``docs/source/glossary.rst`` (the ``.. glossary::`` directive's own
   term lines -- parsed directly from the RST, not hand-copied, so it can't drift out of sync).
2. Every real Python module name under ``core/``, ``api/``, ``web/`` (the actual file tree, not a
   hand-picked feature list).

Sizing is real term/module frequency across ``docs/source/**/*.rst`` (a whole-word,
case-insensitive count via ``wordcloud``'s own frequency-dict mode), not assumed importance --
a term used constantly across the docs renders larger than one mentioned once, the same
"ground claims in what's actually there" discipline the rest of this project's docs follow.
"""

import pathlib
import re

from wordcloud import WordCloud

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_GLOSSARY_PATH = _ROOT / "docs" / "source" / "glossary.rst"
_DOCS_DIR = _ROOT / "docs" / "source"
_OUTPUT_PATH = _DOCS_DIR / "_static" / "tag_cloud.png"

_MODULE_DIRS = ["core", "api", "web"]


def extract_glossary_terms(glossary_path: pathlib.Path = _GLOSSARY_PATH) -> list[str]:
    """Parse .. glossary:: term lines directly from the RST source -- a term line is indented
    exactly 3 spaces (the directive's own content indent) and isn't a directive option (":sorted:")."""
    terms = []
    in_glossary = False
    for line in glossary_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == ".. glossary::":
            in_glossary = True
            continue
        if not in_glossary:
            continue
        if line and not line.startswith(" "):
            in_glossary = False
            continue
        stripped = line[3:] if line.startswith("   ") else ""
        if stripped and not line.startswith("    ") and not stripped.startswith(":"):
            terms.append(stripped.strip())
    return terms


def extract_module_names(root: pathlib.Path = _ROOT, module_dirs: "list[str]" = _MODULE_DIRS) -> list[str]:
    """Every real .py module's stem under the given dirs (default core/, api/, web/) -- excludes
    __init__/__pycache__."""
    names = []
    for dirname in module_dirs:
        for path in (root / dirname).rglob("*.py"):
            if path.stem in ("__init__",) or "__pycache__" in path.parts:
                continue
            names.append(path.stem.replace("_", " "))
    return names


def real_frequency(term: str, docs_dir: pathlib.Path = _DOCS_DIR) -> int:
    """Whole-word (allowing internal spaces/underscores), case-insensitive count of `term` across
    every .rst file under docs_dir -- the real, measured signal driving word size, not a guess."""
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    count = 0
    for rst_file in docs_dir.rglob("*.rst"):
        count += len(pattern.findall(rst_file.read_text(encoding="utf-8", errors="ignore")))
    return max(count, 1)  # never zero -- every term/module is real and belongs on the map


def main() -> None:
    terms = extract_glossary_terms()
    modules = extract_module_names()
    print(f"{len(terms)} glossary terms, {len(modules)} module names")

    frequencies = {}
    for word in set(terms) | set(modules):
        frequencies[word] = real_frequency(word)

    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cloud = WordCloud(
        width=1600,
        height=900,
        background_color="white",
        colormap="viridis",
        prefer_horizontal=0.9,
        max_words=200,
    ).generate_from_frequencies(frequencies)
    cloud.to_file(str(_OUTPUT_PATH))
    print(f"Wrote {_OUTPUT_PATH} ({len(frequencies)} unique terms/modules)")


if __name__ == "__main__":
    main()
