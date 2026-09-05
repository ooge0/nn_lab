"""
api._paths
============

Absolute paths for ``web/templates`` and ``web/static``, anchored to this
module's own location rather than the process's current working
directory. A bare relative path (``"web/templates"``) only resolves
correctly when the process happens to be running from the repo root --
true for ``uvicorn api.app:app`` invoked from there, but not for e.g.
Sphinx importing router modules from ``docs/source/``, which broke exactly
this way (see Stage 5's "found after the fact" log). Centralized here so
the ``.parent`` chain is computed once, correctly, instead of separately
in every router module.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "web" / "templates"
STATIC_DIR = REPO_ROOT / "web" / "static"
