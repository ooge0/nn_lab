"""
cli.manage
=============

The one operational console entrypoint -- start the app, check service reachability, list runs,
copy a run into SQLite -- without needing the web UI up. Replaces an earlier scratch note the
author left at ``core/services/app_rynner.py`` (not valid Python, and the wrong architectural
layer regardless -- ``core/services`` must stay free of CLI/framework concerns per this project's
own layering rule) with a real, tested script in ``cli/``, alongside :mod:`cli.run_experiment`.

Usage::

    python -m cli.manage serve                          # start the FastAPI app
    python -m cli.manage serve --port 8010 --no-reload
    python -m cli.manage status                          # Ollama/NLTK/spaCy reachability
    python -m cli.manage list-runs                       # every run JSONLStore knows about
    python -m cli.manage export-db run-1787407887228      # copy one run's JSONL data into SQLite
    python -m cli.manage export-db run-1787407887228 --overwrite

Note on Windows PowerShell's script execution policy: that policy only gates ``.ps1`` files (e.g.
``.venv\\Scripts\\Activate.ps1``), never a plain ``python ...`` invocation -- ``python -m
cli.manage ...`` never touches it, on any OS, regardless of the current policy setting. There is
nothing for this script itself to work around.
"""

import argparse
import sys

from core.adapters.jsonl_store import JSONLStore
from core.services.db_export import DBExportError, export_run_to_db
from core.services.status_checks import check_nltk, check_ollama, check_spacy


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI app in-process -- equivalent to ``uvicorn api.app:app --reload``."""
    import uvicorn

    uvicorn.run("api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """
    Print Ollama/NLTK/spaCy reachability -- the CLI equivalent of the ``/status`` widget in the
    nav, useful before starting a run when the app itself isn't up yet.

    Returns
    -------
    int
        ``0`` if every check passed, ``1`` if any failed -- script/CI-friendly.
    """
    checks = [check_ollama(), check_nltk(), check_spacy()]
    for check in checks:
        symbol = "OK  " if check["ok"] else "FAIL"
        print(f"[{symbol}] {check['name']}: {check['detail']}")
    return 0 if all(c["ok"] for c in checks) else 1


def cmd_list_runs(args: argparse.Namespace) -> int:
    """List every run :class:`~core.adapters.jsonl_store.JSONLStore` knows about, most recent first."""
    runs = JSONLStore().list_runs()
    if not runs:
        print("No runs found.")
        return 0
    for run in runs:
        print(f"{run.run_id}  started={run.started_at}  tasks={run.total_tasks}")
    return 0


def cmd_export_db(args: argparse.Namespace) -> int:
    """Copy one run's JSONL data into SQLite -- the CLI equivalent of the ``/db_export`` page."""
    try:
        result = export_run_to_db(JSONLStore(), args.run_id, db_path=args.db_path, overwrite=args.overwrite)
    except DBExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Exported {result['response_count']} response(s) to {result['db_path']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser with one subcommand per operation."""
    parser = argparse.ArgumentParser(
        prog="python -m cli.manage",
        description="nn_lab operational console -- serve, status, list-runs, export-db.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI app.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--no-reload", dest="reload", action="store_false")
    serve_parser.set_defaults(func=cmd_serve)

    status_parser = subparsers.add_parser("status", help="Check Ollama/NLTK/spaCy reachability.")
    status_parser.set_defaults(func=cmd_status)

    list_runs_parser = subparsers.add_parser("list-runs", help="List every known experiment run.")
    list_runs_parser.set_defaults(func=cmd_list_runs)

    export_db_parser = subparsers.add_parser("export-db", help="Copy one run's JSONL data into SQLite.")
    export_db_parser.add_argument("run_id")
    export_db_parser.add_argument("--db-path", default="results/nn_lab.db")
    export_db_parser.add_argument("--overwrite", action="store_true")
    export_db_parser.set_defaults(func=cmd_export_db)

    return parser


def main(argv: "list[str] | None" = None) -> int:
    """Parse a subcommand and dispatch to it. Entry point for ``python -m cli.manage``."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
