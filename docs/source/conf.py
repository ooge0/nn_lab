# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import shutil
import sys

sys.path.insert(0, os.path.abspath("../.."))

project = "LLM data lab"
copyright = "2026, si0n4ra"
author = "si0n4ra"
release = "0.0.1"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",  # Pulls in Python docstrings
    "sphinx.ext.napoleon",  # Google/NumPy style docstrings
    "sphinx.ext.viewcode",  # Adds links to highlighted source code
    "sphinx.ext.intersphinx",  # Cross-link to other projects' docs
    "sphinx.ext.todo",  # Support for TODO entries
    "sphinx.ext.coverage",  # Documentation coverage checks
    "sphinx.ext.graphviz",  # Graphviz diagrams
    "sphinx.ext.inheritance_diagram",  # UML-style class inheritance diagrams
    "sphinx.ext.githubpages",  # Publish docs on GitHub Pages
    "myst_parser",  # Markdown (.md) file support
    "sphinx.ext.doctest",
    "sphinx.ext.todo",
    "sphinx.ext.autosummary",
    "sphinxcontrib.plantuml",
    "sphinx.ext.mathjax",  # Renders math client-side -- see myst_enable_extensions below
]

# "dollarmath" -- without it, MyST treats $...$/$$...$$ as literal text, not math syntax. Found
# 2026-08-25: every existing $$...$$ formula in faq_eng.md/faq_ua.md (present since before this
# rewrite) had silently never rendered as real math -- confirmed directly in the built HTML, which
# showed the literal "$$ Velocity = \frac{...}{...} $$" text in the page, not a MathJax-rendered
# equation. sphinx.ext.mathjax above supplies the client-side renderer; this supplies the syntax
# recognition -- both were missing, not just one.
myst_enable_extensions = ["dollarmath", "amsmath"]

templates_path = ["_templates"]
exclude_patterns = []


todo_include_todos = True

# -- PlantUML (architecture diagrams, sphinxcontrib-plantuml) ----------------
# Resolution order: a system `plantuml` command (e.g. `apt install plantuml`
# on Ubuntu) if present on PATH; otherwise a locally-vendored jar run via
# `java -jar`. The jar is NOT committed to the repo (see docs/.tools/README) --
# each machine fetches its own copy once. Override with the PLANTUML_JAR env
# var if you keep it elsewhere.
#
# The `java` binary is resolved via JAVA_HOME first, not a bare `java` PATH
# lookup: on at least one real dev machine, a leftover Oracle "javapath"
# redirector stub (Common Files\Oracle\Java\javapath\java.exe) sits earlier
# on PATH than the actual working JDK and fails silently (exit 127, no
# stderr) when invoked, since its registered JRE was uninstalled. JAVA_HOME
# is the standard way to point at a specific JDK on both Windows and Ubuntu
# and isn't affected by PATH ordering, so it's preferred when set.
_java_home = os.environ.get("JAVA_HOME")
_java_bin = os.path.join(_java_home, "bin", "java.exe" if os.name == "nt" else "java") if _java_home else "java"

_system_plantuml = shutil.which("plantuml")
if _system_plantuml:
    plantuml = _system_plantuml
else:
    _jar_path = os.environ.get(
        "PLANTUML_JAR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".tools", "plantuml.jar")),
    )
    plantuml = f'"{_java_bin}" -jar "{_jar_path}"'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = 'alabaster'
# html_theme = "furo"
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
# sphinx_rtd_theme hard-caps content at 800px (.wy-nav-content{max-width:800px}) regardless of
# viewport width -- on a wide monitor this leaves most of the page empty. Older theme versions
# fixed this via html_theme_options["body_max_width"], but that option was dropped from this
# theme's recognized options by v2.0.0 (confirmed directly in theme.conf -- setting it silently did
# nothing rather than raising a warning). The current, working fix is a plain CSS override loaded
# after theme.css -- see _static/custom.css.
html_css_files = ["custom.css"]
