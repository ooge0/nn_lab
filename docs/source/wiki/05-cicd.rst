05 — CI/CD: Current State and a Concrete Target Pipeline
============================================================

Current state: no CI/CD exists
------------------------------------

Confirmed directly, not assumed: there is no ``.github/`` directory anywhere in the repository (no
workflows, no issue templates, nothing), no ``.gitlab-ci.yml``, no ``Jenkinsfile``, and no
``.pre-commit-config.yaml``. Every quality gate documented in :doc:`02-tools-and-stack` --
``pytest``, ``tox -e py312``, ``tox -e e2e``, ``tox -e lint`` (ruff + mypy), ``black`` -- is invoked
by hand, by whoever
is working on the repository at that moment, on their own machine. Nothing enforces that any of them
actually ran before a commit lands.

This matters specifically for this project's stated purpose: CLAUDE.md frames the test suite itself
as the portfolio artifact (SS7, "the testing approach IS the portfolio signal"). A test suite nobody
is forced to run is a weaker version of that claim than one a machine enforces on every push.

Why this gap is real and not just an oversight to gloss over: the project's own deployment target is
explicitly bare-metal Windows and Ubuntu with **no Docker, no cloud** (CLAUDE.md SS2) -- a
single-user local tool has genuinely less pressure toward CI/CD than a deployed multi-user service
does. That context changes what "add CI" should mean here: not a deploy pipeline (there is nowhere
automated to deploy *to*), but a **correctness gate on every push** -- lint, type-check, and test,
nothing more.

What a GitHub Actions pipeline would need to account for, specifically for this repository
------------------------------------------------------------------------------------------------

Three real constraints, each already documented elsewhere in this wiki, shape what a naive
"lint, then test, then build" pipeline would get wrong if copied from a generic template:

1. **``tests/e2e`` cannot share a process, or a CI job, with the rest of the suite.**
   :doc:`02-tools-and-stack` explains the underlying ``asyncio``/Playwright interaction bug this
   project hit directly. A CI pipeline that runs ``pytest tests`` in one step would reproduce that
   exact failure -- the job split below keeps them as two separate GitHub Actions jobs, matching
   ``tox.ini``'s own ``py312``/``e2e`` environment split.

2. **GitHub-hosted runners have no GPU.** ``requirements.in``'s ``torch==2.5.1``/``torchvision==0.20.1``
   pin (see :doc:`02-tools-and-stack`) targets the ``cu121`` CUDA wheel index for local development;
   a hosted CI runner has no CUDA driver to use one. CI must install the CPU-only wheel instead, which
   means CI validates **logical correctness**, not GPU-accelerated performance -- an honest scope
   limit to state, not a bug to fix, since paying for GPU-backed CI runners would work against this
   project's explicit "not a product, no infrastructure spend" framing (CLAUDE.md SS0).

3. **There is no packaged artifact to "build."** This project has no ``setup.py``/``pyproject.toml``
   package definition -- it is not published or installed as a library, it is run in place
   (``uvicorn api.app:app``). A CI "build" stage here means something narrower and more honest than a
   wheel/sdist: confirming the app **imports cleanly** and the **Sphinx docs build without new
   warnings** (the current baseline is a stable, tracked 7 warnings -- see this wiki's own build
   process for how that number is checked). That is the real thing worth automating under the name
   "build" for a project shaped like this one, not a fabricated packaging step.

Proposed pipeline (GitHub Actions, not yet implemented)
--------------------------------------------------------------

The shape below is deliberately close to what already exists in ``tox.ini`` -- CI should run the
*same* commands a developer already runs locally, not a parallel set of CI-only commands that could
drift out of sync with them.

.. code-block:: yaml

   # .github/workflows/ci.yml (proposed -- not yet created)
   name: CI

   on:
     push:
       branches: [master, develop]
     pull_request:

   jobs:
     lint:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.12"
         - run: pip install tox
         # pyproject.toml + tox -e lint landed 2026-08-24 (see 02-tools-and-stack.rst) -- ruff and
         # mypy both pass locally today. black is deliberately not part of this job: it was run
         # once to reformat the existing codebase, but gating on it in CI is a separate decision
         # not yet made.
         - run: tox -e lint

     unit-and-integration:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.12"
         # CPU-only torch -- see the GPU-runner constraint above. requirements-base.txt's own
         # torch==2.5.1 pin still resolves (it's a real PyPI version), just without the cu121
         # CUDA build a local dev machine installs separately.
         - run: pip install -r requirements-base.txt
         - run: pip install pytest-cov allure-pytest
         - run: python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('brown'); nltk.download('averaged_perceptron_tagger_eng')"
         - run: pytest tests --ignore=tests/e2e --cov=core --cov=api --cov=cli --cov=web --cov=utils --cov-report=term-missing

     e2e:
       runs-on: ubuntu-latest
       needs: unit-and-integration
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.12"
         - run: pip install -r requirements-base.txt pytest-playwright
         - run: playwright install --with-deps chromium
         - run: pytest tests/e2e -v

     docs:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.12"
         - run: pip install -r requirements-base.txt
         - run: sphinx-build -b html -W --keep-going docs/source docs/source/_build/html
         # Fails the build on any *new* warning above the tracked baseline, rather than on any
         # warning at all -- the current baseline is a known, stable 7 (see this wiki's own
         # verification notes); a hard -W with zero tolerance would need those 7 fixed first.

     deploy:
       runs-on: ubuntu-latest
       needs: [unit-and-integration, e2e, docs]
       if: github.ref == 'refs/heads/master'
       steps:
         - run: echo "No automated deploy target exists -- CLAUDE.md SS2 states bare-metal
             Windows/Ubuntu, no Docker, no cloud. Deployment today is manual: pull this commit
             on the target machine and restart uvicorn. This job is a placeholder marking where
             a real deploy step would go if a target ever exists, not a working deploy step."

What to add for free, right now, with zero infrastructure
------------------------------------------------------------------

Everything in the ``lint``/``unit-and-integration``/``e2e``/``docs`` jobs above runs entirely on
GitHub's free hosted runners, using commands that already exist and already work locally via
``tox``. Adding this workflow file costs nothing but the runner-minutes GitHub already grants free
public repositories. The ``lint`` job no longer needs special sequencing -- ``pyproject.toml`` and
``tox -e lint`` landed 2026-08-24 (see :doc:`02-tools-and-stack`) and pass cleanly today, so this job
would go green from the day it's added rather than needing to wait for config that doesn't exist yet.

What requires infrastructure later (out of scope for a free GitHub Actions setup)
----------------------------------------------------------------------------------------

- **GPU-validated test runs.** Confirming the ``cu121`` torch build actually behaves as expected
  under load would need either a self-hosted GitHub Actions runner with a real GPU, or a paid
  GPU-backed CI provider -- not something to add speculatively before there's a concrete reason
  (e.g. a GPU-specific regression that CPU-only CI already missed).
- **Any real deploy target.** The ``deploy`` job above is intentionally inert. Automating it for
  real would require deciding on a target machine and access method first (SSH to a bare-metal box,
  a scheduled task, etc.) -- a decision CLAUDE.md explicitly defers, not one this pipeline should
  make unilaterally.
