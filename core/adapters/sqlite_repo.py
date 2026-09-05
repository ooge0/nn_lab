"""
core.adapters.sqlite_repo
============================

``Repository`` implementation over SQLite (SQLAlchemy 2.x, sync -- no async
driver needed for a strictly single-user, single-session app). Normalizes
run metadata into its own table rather than repeating it on every response
row, directly motivated by Stage 0's finding against real exported data:
21.3% of every row's bytes in a sampled export were exactly-repeated
run-level fields.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import ForeignKey, JSON, create_engine, delete
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from core.domain.entities import ExperimentConfig, RunRecord


class _Base(DeclarativeBase):
    """SQLAlchemy 2.0 typed declarative base -- gives mypy a real class to check against (the classic
    ``declarative_base()`` factory function does not, without an extra mypy plugin)."""


class RunORM(_Base):
    """SQLAlchemy model for the ``runs`` table -- one row per run."""

    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(primary_key=True)
    started_at: Mapped[str]
    total_tasks: Mapped[int]
    config_json: Mapped[dict] = mapped_column(JSON)
    # When this row was last written by save_run() -- distinct from started_at (the run's own
    # origin time, copied from the source RunRecord). Added 2026-08-25 for /db_export's "last
    # synced" column; see _ensure_last_synced_at_column for why a database created before this
    # column existed doesn't just break.
    last_synced_at: Mapped[str]


class ResponseORM(_Base):
    """SQLAlchemy model for the ``responses`` table -- one row per response, foreign-keyed to its run."""

    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    data_json: Mapped[dict] = mapped_column(JSON)


class SQLiteRepo:
    """
    ``Repository`` backed by SQLite.

    Parameters
    ----------
    db_path : str, optional
        SQLite database file path, or ``":memory:"`` for an ephemeral
        in-process database (default: ``results/nn_lab.db``, created if
        missing).
    """

    def __init__(self, db_path: "str | Path" = "results/nn_lab.db") -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}")
        _Base.metadata.create_all(self._engine)
        self._ensure_last_synced_at_column()
        self._session_factory = sessionmaker(bind=self._engine)

    def _ensure_last_synced_at_column(self) -> None:
        """
        Self-healing migration for a ``runs`` table created before ``last_synced_at`` existed --
        ``create_all`` above only creates *missing tables*, it never adds a missing *column* to an
        already-existing one, so a database file exported before 2026-08-25 would otherwise raise
        ``OperationalError: no such column`` the moment :meth:`save_run` or :meth:`get_sync_status`
        touched it. No formal migration tool (Alembic etc.) exists in this project -- disproportionate
        for a single-user local SQLite file with one such change so far -- so a plain, idempotent
        ``ALTER TABLE`` is the minimal correct fix, guarded so it only ever runs once per database.
        """
        with self._engine.connect() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(runs)")}
            if columns and "last_synced_at" not in columns:
                conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN last_synced_at TEXT DEFAULT ''")
                conn.commit()

    def save_run(self, run: RunRecord) -> str:
        """See :meth:`core.domain.interfaces.Repository.save_run`."""
        with self._session_factory() as session:
            session.merge(
                RunORM(
                    run_id=run.run_id,
                    started_at=run.started_at,
                    total_tasks=run.total_tasks,
                    config_json=run.config.model_dump(mode="json"),
                    last_synced_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            session.commit()
        return run.run_id

    def delete_run(self, run_id: str) -> None:
        """
        Delete one run's row from the ``runs`` table -- not part of the ``Repository`` interface
        (SQLite-specific maintenance, same category as :meth:`delete_responses`). Does **not**
        cascade to that run's ``responses`` rows; call :meth:`delete_responses` first if a full
        removal is wanted. Used by E2E test fixtures to reset a fixture run's sync status between
        runs (``get_sync_status`` only reports rows still present in ``runs``); no production code
        path calls this today.

        Parameters
        ----------
        run_id : str
            The run to remove.
        """
        with self._session_factory() as session:
            session.query(RunORM).filter(RunORM.run_id == run_id).delete()
            session.commit()

    def get_sync_status(self) -> "dict[str, str]":
        """
        Every run currently in this database, mapped to when its metadata was last written here by
        :meth:`save_run` -- not part of the ``Repository`` interface (SQLite-specific, built for
        the ``/db_export`` page's "last synced" column, not a generic read operation every adapter
        needs).

        Returns
        -------
        dict[str, str]
            ``{run_id: last_synced_at}`` (ISO 8601 UTC timestamp string) for every run this
            database holds. A ``run_id`` absent from this dict has never been exported here.
        """
        with self._session_factory() as session:
            rows = session.query(RunORM.run_id, RunORM.last_synced_at).all()
            return {run_id: last_synced_at for run_id, last_synced_at in rows}

    def save_response(self, run_id: str, response: dict) -> None:
        """See :meth:`core.domain.interfaces.Repository.save_response`."""
        with self._session_factory() as session:
            session.add(ResponseORM(run_id=run_id, data_json=response))
            session.commit()

    def delete_responses(self, run_id: str) -> int:
        """
        Delete every ``responses`` row for ``run_id`` -- not part of the ``Repository`` interface
        (SQLite-specific maintenance, not a generic read/write operation every adapter needs).

        Notes
        -----
        ``save_response`` has no natural primary key beyond an autoincrementing ``id`` -- calling it
        twice for the same response duplicates the row rather than upserting. This exists so a
        caller re-exporting a run (:func:`core.services.db_export.export_run_to_db`) can clear the
        old rows first instead of silently accumulating duplicates on a second export.

        Parameters
        ----------
        run_id : str
            The run whose responses should be removed.

        Returns
        -------
        int
            Number of rows deleted.
        """
        with self._session_factory() as session:
            result = session.execute(delete(ResponseORM).where(ResponseORM.run_id == run_id))
            session.commit()
            # Session.execute()'s static return type (Result[Any]) doesn't declare .rowcount, but a
            # DELETE statement always returns a CursorResult at runtime, which does -- a real
            # SQLAlchemy stub gap, not a bug (same class of gap as sqlite_repo's DeclarativeBase note).
            return result.rowcount  # type: ignore[attr-defined]

    def load_responses(self, run_id: Optional[str] = None) -> "list[dict]":
        """See :meth:`core.domain.interfaces.Repository.load_responses`."""
        with self._session_factory() as session:
            query = session.query(ResponseORM)
            if run_id is not None:
                query = query.filter(ResponseORM.run_id == run_id)
            return [row.data_json for row in query.order_by(ResponseORM.id).all()]

    def list_runs(self) -> "list[RunRecord]":
        """See :meth:`core.domain.interfaces.Repository.list_runs`."""
        with self._session_factory() as session:
            rows = session.query(RunORM).order_by(RunORM.started_at.desc()).all()
            return [
                RunRecord(
                    run_id=row.run_id,
                    started_at=row.started_at,
                    config=ExperimentConfig(**row.config_json),
                    total_tasks=row.total_tasks,
                )
                for row in rows
            ]
