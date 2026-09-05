"""
core.services.db_export
==========================

Copies one run's metadata and responses from whichever :class:`~core.domain.interfaces.Repository`
is live (in practice, always :class:`~core.adapters.jsonl_store.JSONLStore` today -- no router
constructs :class:`~core.adapters.sqlite_repo.SQLiteRepo` for write traffic) into a real
:class:`~core.adapters.sqlite_repo.SQLiteRepo` database file, so the SQL examples in
:doc:`/operations` are reachable via a button/API call instead of only a hand-typed Python
snippet.

Deliberately its own small service, not folded into :class:`~core.services.metrics_engine
.MetricsEngine` -- this reads from one repository and writes to a second, concrete one
(``SQLiteRepo`` specifically, not "whatever ``Repository`` is configured"), which is a different
shape of operation from ``MetricsEngine``'s pure read-side aggregation over a single repository.
"""

from typing import Optional

from core.adapters.sqlite_repo import SQLiteRepo
from core.domain.entities import RunRecord
from core.domain.interfaces import Repository


class DBExportError(Exception):
    """Raised by :func:`export_run_to_db` when the export can't proceed as requested."""


def export_run_to_db(
    source_repo: Repository,
    run_id: str,
    db_path: "str" = "results/nn_lab.db",
    overwrite: bool = False,
) -> dict:
    """
    Copy one run's metadata and every response from ``source_repo`` into a
    :class:`~core.adapters.sqlite_repo.SQLiteRepo` at ``db_path``.

    Parameters
    ----------
    source_repo : Repository
        Where the run currently lives (the live ``JSONLStore`` in practice).
    run_id : str
        The run to export.
    db_path : str
        Target SQLite file, created if missing (default matches the path already documented in
        :doc:`/operations`'s manual-import example, so both paths land in the same database).
    overwrite : bool
        If the run's responses already exist in the target database: ``False`` (default) raises
        :class:`DBExportError` rather than silently duplicating rows (``SQLiteRepo.save_response``
        has no natural dedup key -- see its own docstring); ``True`` deletes the existing rows for
        this run first, then re-inserts the current source data.

    Returns
    -------
    dict
        ``{"run_id", "db_path", "response_count", "overwritten"}``.

    Raises
    ------
    DBExportError
        If ``run_id`` has no responses (or no run metadata) in ``source_repo``, or if it already
        exists in the target database and ``overwrite`` is ``False``.
    """
    responses = source_repo.load_responses(run_id)
    if not responses:
        raise DBExportError(f"No responses found for run '{run_id}' in the source repository.")

    run_record = _find_run(source_repo, run_id)
    if run_record is None:
        raise DBExportError(f"No run metadata found for run '{run_id}'.")

    target = SQLiteRepo(db_path=db_path)
    existing = target.load_responses(run_id)
    if existing:
        if not overwrite:
            raise DBExportError(
                f"Run '{run_id}' already has {len(existing)} response(s) in '{db_path}'. "
                "Re-export with overwrite=True to replace them."
            )
        target.delete_responses(run_id)

    target.save_run(run_record)
    for response in responses:
        target.save_response(run_id, response)

    return {
        "run_id": run_id,
        "db_path": db_path,
        "response_count": len(responses),
        "overwritten": bool(existing),
        # Read back rather than reconstructed here, so this is always the exact value save_run
        # actually persisted, not a second, possibly-clock-skewed timestamp computed separately.
        "synced_at": target.get_sync_status().get(run_id),
    }


def _find_run(source_repo: Repository, run_id: str) -> Optional[RunRecord]:
    return next((run for run in source_repo.list_runs() if run.run_id == run_id), None)


def get_sync_status(db_path: "str" = "results/nn_lab.db") -> "dict[str, str]":
    """
    Every run currently exported into ``db_path``, mapped to when it was last written there --
    thin wrapper around :meth:`~core.adapters.sqlite_repo.SQLiteRepo.get_sync_status` for the
    ``/db_export`` page's "Export status" column (a run absent from the returned dict has never
    been exported to this database).

    Parameters
    ----------
    db_path : str
        Same target database :func:`export_run_to_db` writes to.

    Returns
    -------
    dict[str, str]
        ``{run_id: last_synced_at}`` (ISO 8601 UTC timestamp string).
    """
    return SQLiteRepo(db_path=db_path).get_sync_status()


__all__ = ["DBExportError", "export_run_to_db", "get_sync_status"]
