"""
core.adapters.jsonl_store
===========================

``Repository`` implementation writing one JSONL file per run under
``results/lab_experiment_results/`` -- the same directory and filename
convention the legacy "Save JSONL" button uses.

Notes
-----
One deliberate behavioural difference from the legacy pattern: the legacy
app accumulates every response in ``st.session_state.history`` (in memory)
and only writes to disk when the user clicks "Save JSONL" -- a run that
crashes or is closed before that click loses everything. This adapter
appends each response to disk as :meth:`JSONLStore.save_response` is
called, so a long-running background-thread run (Stage 5 onward) survives
a crash with whatever was generated up to that point. There is no "click
save" step in the new architecture for this to preserve fidelity to in the
first place -- a headless service layer has no button.
"""

import json
from pathlib import Path
from typing import Optional

from core.domain.entities import RunRecord
from utils import config_loader_short


class JSONLStore:
    """
    ``Repository`` backed by one JSONL file per run.

    Parameters
    ----------
    results_dir : pathlib.Path, optional
        Directory to write run files into (default: ``config.ini``'s
        ``[DIRECTORIES] results_dir``, via ``utils.config_loader_short``).
    """

    def __init__(self, results_dir: Optional[Path] = None) -> None:
        self._results_dir = Path(results_dir) if results_dir is not None else config_loader_short.RESULTS_DIR
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._run_files: "dict[str, Path]" = {}

    def _file_for(self, run_id: str) -> Path:
        if run_id not in self._run_files:
            self._run_files[run_id] = self._results_dir / f"lab_export_{run_id}.jsonl"
        return self._run_files[run_id]

    def _meta_file_for(self, run_id: str) -> Path:
        return self._results_dir / f"lab_export_{run_id}.meta.json"

    def save_run(self, run: RunRecord) -> str:
        """
        See :meth:`core.domain.interfaces.Repository.save_run`.

        Establishes the run's response file path (writes nothing to it yet
        -- unchanged from before) and writes the run's metadata to a
        sidecar ``<run>.meta.json`` file immediately, so :meth:`list_runs`
        can discover the run even if it crashes before its first response.
        Kept in a separate file rather than a header line inside the
        ``.jsonl`` itself so that file's rows stay exactly the legacy
        per-response shape, with nothing for existing consumers to skip.
        """
        self._file_for(run.run_id)
        with open(self._meta_file_for(run.run_id), "w", encoding="utf-8") as f:
            f.write(run.model_dump_json())
        return run.run_id

    def save_response(self, run_id: str, response: dict) -> None:
        """See :meth:`core.domain.interfaces.Repository.save_response`. Appends one JSON line."""
        with open(self._file_for(run_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(response, ensure_ascii=False) + "\n")

    def load_responses(self, run_id: Optional[str] = None) -> "list[dict]":
        """See :meth:`core.domain.interfaces.Repository.load_responses`."""
        if run_id is not None:
            files = [self._file_for(run_id)] if self._file_for(run_id).exists() else []
        else:
            files = sorted(self._results_dir.glob("lab_export_*.jsonl"))

        responses: "list[dict]" = []
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        responses.append(json.loads(line))
        return responses

    def list_runs(self) -> "list[RunRecord]":
        """See :meth:`core.domain.interfaces.Repository.list_runs`. Reads every ``*.meta.json`` sidecar file."""
        runs = []
        for path in self._results_dir.glob("lab_export_*.meta.json"):
            with open(path, "r", encoding="utf-8") as f:
                runs.append(RunRecord.model_validate_json(f.read()))
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs
