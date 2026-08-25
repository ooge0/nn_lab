"""
cli.run_experiment
=====================

Stage 15 -- config-driven batch runner. Reuses
:class:`~core.services.experiment_runner.ExperimentRunner` and Stage 3's
adapters directly, wired the same way :mod:`api.routers.experiments` wires
them -- the only difference is the front end: no FastAPI/SSE, progress is
printed to stdout as each event is drained from
:class:`~core.services.experiment_runner.ExperimentRunner`'s own
``asyncio.Queue`` (the same queue ``/experiments/stream`` reads from), and
``asyncio.run`` supplies the event loop ``try_start`` needs -- purely
internal plumbing to this module, invisible to the person running it from
a terminal. No orchestration logic is duplicated: this module never
touches ``ExperimentConfig``/``RunRecord`` construction or the
generate-judge-persist loop, only :meth:`~core.services.experiment_runner
.ExperimentRunner.try_start` and its progress queue.

Usage::

    python -m cli.run_experiment --config path/to/experiment.toml

See ``cli/example_config.toml`` for the full field reference (mirrors
:class:`~core.domain.entities.ExperimentConfig` exactly -- ``sweep_min``/
``sweep_max`` are the already-resolved endpoints, not the web form's
Delta/MIN-MAX modes, since the entity itself doesn't distinguish those; see
its own docstring).
"""

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path
from typing import Optional, TextIO

from core.adapters.jsonl_store import JSONLStore
from core.adapters.ollama_client import OllamaClient
from core.adapters.structured_judge import StructuredJudge
from core.adapters.prompt_strategy import NaivePromptStrategy
from core.adapters.rag.knowledge_base import RAGKnowledgeBase
from core.domain.entities import ExperimentConfig
from core.services.experiment_runner import ExperimentRunner, InvalidExperimentConfigError, TooManyTasksError
from utils import config_loader_short
from utils.app_utils import AppUtils


def load_config(path: Path) -> ExperimentConfig:
    """
    Load and validate one TOML config file into an
    :class:`~core.domain.entities.ExperimentConfig`.

    Parameters
    ----------
    path : pathlib.Path
        Path to a TOML file whose top-level keys match
        ``ExperimentConfig``'s own field names exactly.

    Returns
    -------
    ExperimentConfig

    Raises
    ------
    pydantic.ValidationError
        If a required field is missing or a value fails validation --
        surfaces the same errors a malformed web-form submission would hit
        pydantic's own validation with, not a separate CLI-specific schema.
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return ExperimentConfig(**data)


def build_runner(config: ExperimentConfig) -> ExperimentRunner:
    """
    Wire the real adapters into an :class:`~core.services.experiment_runner
    .ExperimentRunner`, exactly matching :mod:`api.routers.experiments`'s
    own module-level construction -- the CLI and the web app hit the same
    local Ollama, the same ``JSONLStore`` directory, the same archetypes
    file.

    Parameters
    ----------
    config : ExperimentConfig
        Only consulted for ``rag_enabled`` -- the knowledge base is built
        eagerly here (unlike the web app's lazy, first-request build) since
        a CLI invocation is a single one-shot run, not a long-lived process
        amortizing that cost across many different requests.

    Returns
    -------
    ExperimentRunner
    """
    archetypes = AppUtils().load_archetypes(str(config_loader_short.SYS_PROMPTS_DEFINED_FILE_PATH))
    ollama = OllamaClient()
    runner = ExperimentRunner(
        llm_client=ollama,
        repository=JSONLStore(),
        prompt_strategy=NaivePromptStrategy(archetypes),
        judge=StructuredJudge(ollama),
        archetypes=archetypes,
        max_total_tasks=config_loader_short.MAX_TOTAL_TASKS,
    )
    if config.rag_enabled:
        knowledge_base = RAGKnowledgeBase()
        knowledge_base.load_knowledge_base(str(config_loader_short.KNOWLEDGE_PATH))
        runner.set_knowledge_base(knowledge_base)
    return runner


def run(runner: ExperimentRunner, config: ExperimentConfig, out: "Optional[TextIO]" = None) -> int:
    """
    Drive one run to completion, printing one progress line per event.

    Parameters
    ----------
    runner : ExperimentRunner
        Already constructed (real adapters via :func:`build_runner` in
        production; fakes in tests -- this function never constructs
        adapters itself, so it's testable against either without change).
    config : ExperimentConfig
    out : TextIO, optional
        Where progress lines are printed. Resolved to ``sys.stdout``
        *inside* the function body, not as a default-argument value --
        a default of ``sys.stdout`` would bind whatever ``sys.stdout``
        happened to be at module-import time, which stops respecting
        redirection (e.g. pytest's ``capsys``) applied later at call time.

    Returns
    -------
    int
        Process exit code: ``0`` on a clean ``"done"`` event, ``1`` if the
        config was rejected before any generation started
        (``InvalidExperimentConfigError``/``TooManyTasksError``), a run was
        already in progress, or the run itself emitted an ``"error"``
        event.
    """
    out = out if out is not None else sys.stdout

    async def _drive() -> int:
        loop = asyncio.get_running_loop()
        try:
            queue = runner.try_start(loop, config)
        except (InvalidExperimentConfigError, TooManyTasksError) as exc:
            print(f"ERROR: {exc}", file=out)
            return 1
        if queue is None:
            print("ERROR: a run is already in progress.", file=out)
            return 1

        while True:
            event = await queue.get()
            if event.stage == "error":
                print(f"ERROR: {event.error}", file=out)
                return 1
            if event.stage == "done":
                print(f"Done -- {event.step}/{event.total_tasks} -- run {event.run_id}", file=out)
                return 0
            if event.step is not None:
                print(f"[{event.step}/{event.total_tasks}] {event.stage}...", file=out)
            else:
                print(f"{event.stage}...", file=out)

    return asyncio.run(_drive())


def main(argv: "list[str] | None" = None) -> int:
    """
    Parse ``--config``, load it, wire real adapters, and run it to
    completion. Entry point for ``python -m cli.run_experiment``.

    Parameters
    ----------
    argv : list[str], optional
        Defaults to ``sys.argv[1:]`` (argparse's own default).

    Returns
    -------
    int
        Process exit code -- see :func:`run`.
    """
    parser = argparse.ArgumentParser(description="Run a config-driven batch experiment against local Ollama.")
    parser.add_argument("--config", required=True, type=Path, help="Path to a TOML experiment config.")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    runner = build_runner(config)
    return run(runner, config)


if __name__ == "__main__":
    sys.exit(main())
