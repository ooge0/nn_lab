Operations -- running, seeing, and inspecting results
==========================================================

A concrete, verified walkthrough: set up, run an experiment, see the result -- once through the
UI, once through the raw API -- and how to inspect what actually landed on disk once you're past
the pages this app renders for you. Every command on this page was run for real against a live
local Ollama server while writing it, not assumed.

Scenario 1 -- via the UI
----------------------------

1. Start Ollama and make sure at least one model is pulled::

       ollama serve
       ollama pull tinyllama:latest

2. Start the app::

       uvicorn api.app:app --reload

3. Open http://127.0.0.1:8000/ -- the landing page links to every page below.
4. Click **Run an experiment** (or go straight to http://127.0.0.1:8000/experiments).
5. Fill in the form:

   - **Students** and **Archetypes** are both required (Ctrl/Cmd-click to select more than one) --
     the form won't submit with either left empty.
   - Everything else has a working default; you can just click **Run experiment**.

6. A progress bar appears immediately and updates live via Server-Sent Events -- no page refresh.
7. Once the run finishes, the same panel shows direct links: **Run summary**, **Analytics**,
   **Deep NLP**, **Clusters** -- click any of them to see the result. Each of those pages' own run
   picker defaults to the run you just finished, so you land on it without hunting for it.

Scenario 2 -- via the raw API
----------------------------------

The exact same ``ExperimentRunner`` handles both -- there's no separate "API mode." This is the
same form POST a browser would send, just typed out with ``curl``. Every response below is real
output from a real run against ``tinyllama:latest``, not illustrative.

**1. Start a run** (``POST /experiments/start``, form-encoded -- note this is *not* a JSON body;
FastAPI's ``request.form()`` expects the same ``application/x-www-form-urlencoded`` shape an HTML
form submits)::

    curl -X POST http://127.0.0.1:8000/experiments/start \
      --data-urlencode "student_models=tinyllama:latest" \
      --data-urlencode "archetypes=Neutral" \
      --data-urlencode "teacher_model=tinyllama:latest" \
      --data-urlencode "prompt_mode=Behavioral conditioning (Tuned)" \
      --data-urlencode "biases_raw=formal" \
      --data-urlencode "base_temperature=0.7" \
      --data-urlencode "base_top_p=0.9" \
      --data-urlencode "max_tokens=40"

Response (``202``)::

    <div hx-ext="sse" sse-connect="/experiments/stream" sse-close="progress-done">
      <div id="experiment-progress" sse-swap="progress">Starting&hellip;</div>
    </div>

That's an HTML fragment, not JSON -- this route exists to be swapped into a page by htmx, and
returns the same thing regardless of caller. See :doc:`features` for the full set of
``InvalidExperimentConfigError``/``TooManyTasksError``/"already running" status codes this can
also return.

**2. Watch progress** (``GET /experiments/stream``, Server-Sent Events)::

    curl -N http://127.0.0.1:8000/experiments/stream

Streams one ``event: progress`` per response generated, then closes after ``event:
progress-done``. ``-N`` disables curl's output buffering so you see each event as it arrives,
not all at once at the end.

**3. Find the run id and read its summary** -- runs are named ``run-<millis-since-epoch>``; the
JSONL/meta files under ``results/lab_experiment_results/`` are the source of truth for "what's the
latest run" (see *Inspecting results directly* below for a one-liner), or read it off the
``event: progress`` payload from step 2, which includes ``run <run_id>`` in the terminal event::

    curl "http://127.0.0.1:8000/runs/summary?run_id=run-1787431575576"

Response (``200``, real output)::

    <div id="perf-summary">
      <table>
        <tbody>
          <tr><th>Total records</th><td>1</td></tr>
          <tr><th>Steps</th><td>1/1</td></tr>
          <tr><th>Sweep parameter</th><td>Baseline</td></tr>
          <tr><th>Value range</th><td>0.7 - 0.7</td></tr>
          <tr><th>Total processing time</th><td>4.24 sec</td></tr>
          <tr><th>Avg. ms per word</th><td>2119.34</td></tr>
          ...

Can you get a chart via the API?
--------------------------------------

Yes -- tried directly, not assumed. ``GET /analytics/charts?run_id=...`` (and the equivalent
``/nlp/charts``, ``/clusters/charts``, ``/benchmark/report``, ``/model_evo/evaluate``,
``/monitor/schema`` routes) return the **exact same server-rendered HTML** a browser would swap
into the page -- including fully-formed ``<script>Plotly.newPlot(...)</script>`` calls with the
real data baked in, not a placeholder::

    curl "http://127.0.0.1:8000/analytics/charts?run_id=run-1787407887228" -o charts.html

The nuance: this is **not** a clean JSON visualization API you'd point a different frontend at --
it's a pre-rendered HTML fragment meant for htmx to swap into a live DOM. Swagger's "Try it out"
will show you the raw HTML text, not a rendered chart (Swagger doesn't execute the embedded
``<script>`` tags). If you want to actually *see* the chart from a plain ``curl`` call, save the
response and open it in a browser -- ``charts.html`` above, opened directly, renders the real
Plotly charts (it references ``/static/vendor/plotly/plotly.min.js`` by a relative path, so open
it while the app is still running at ``127.0.0.1:8000``, or copy that vendored file alongside it).
There's no route that returns the underlying chart *data* as plain JSON today -- if you want that,
the closest existing building block is ``core.services.metrics_engine`` /
``core.analysis.data_contract.LabDataBridge`` (build the same DataFrame these routes build, then
serialize it yourself) rather than screen-scraping the embedded Plotly JSON out of the HTML.

Inspecting results directly
--------------------------------

The live storage backend is :class:`~core.adapters.jsonl_store.JSONLStore` -- plain files, not a
database. Two files per run, under ``results/lab_experiment_results/``:

- ``<run_id>.meta.json`` -- one JSON object: ``run_id``, ``started_at``, ``total_tasks``, and the
  full ``config`` that was submitted.
- ``lab_export_<run_id>.jsonl`` -- one JSON object *per line*, one line per generated response.
  Every key is documented in :doc:`features`' "Response record fields" table (66 fields as of
  Stage 6).

**Quickest look, no SQL, no code** -- find the most recent run and pretty-print its first response::

    ls -t results/lab_experiment_results/lab_export_run-*.jsonl | head -1
    python -c "import json; print(json.dumps(json.loads(open('results/lab_experiment_results/lab_export_run-<id>.jsonl').readline()), indent=2))"

**Real SQL, verified against real data** -- :class:`~core.adapters.sqlite_repo.SQLiteRepo` is a
second, fully-tested :class:`~core.domain.interfaces.Repository` implementation (see
:doc:`features`) that stores the same data as two real tables (``runs``, ``responses``) instead of
files. Two ways to get a run into it:

**Via the UI/API (preferred with the app already running)** -- http://127.0.0.1:8000/db_export
lists every run with a **Send to DB** button (plus checkboxes and a **Send selected to DB** button
for exporting several at once -- bulk export just triggers each checked row's own button, so a run
already in the database still resolves individually, exactly like a single click); clicking it
calls :func:`core.services.db_export.export_run_to_db` behind the scenes, which copies that run's
metadata and every response into ``results/nn_lab.db``. Re-clicking the same run reports "already
has N response(s)" rather than silently duplicating rows (``SQLiteRepo.save_response`` has no
natural dedup key on its own -- confirmed by reading it directly, not assumed); a **Re-export
(overwrite)** action replaces the existing rows if you actually want to refresh a stale copy.
Scriptable the same way with a plain POST::

    curl -X POST "http://127.0.0.1:8000/db_export/export?run_id=run-1787407887228"
    curl -X POST "http://127.0.0.1:8000/db_export/export?run_id=run-1787407887228&overwrite=true"

**Via the console, with no server running at all** -- :mod:`cli.manage` wraps the same function for
a terminal-only workflow::

    python -m cli.manage export-db run-1787407887228
    python -m cli.manage export-db run-1787407887228 --overwrite

**Standalone, without the app running** -- the same underlying function works directly from a
Python one-liner, e.g. for a scripted/batch import outside the running app::

    python -c "
    from core.adapters.jsonl_store import JSONLStore
    from core.services.db_export import export_run_to_db

    result = export_run_to_db(JSONLStore(), 'run-1787407887228')  # substitute your own
    print(result)
    "

Verified live against a real 500-response run while writing this page (not assumed): the UI path
reported ``500 response(s) exported to results/nn_lab.db``, a second click correctly refused with
``already has 500 response(s)``, and ``overwrite=true`` replaced them cleanly rather than doubling
the row count.

Then query it with any SQLite client (``sqlite3 results/nn_lab.db``, DB Browser for SQLite,
``sqlite3`` Python module, etc.). ``responses.data_json`` holds the full 66-field response as one
JSON column -- use SQLite's built-in JSON1 functions (bundled since SQLite 3.38 / Python 3.9's
``sqlite3`` module, no extra install) to query into it:

.. code-block:: sql

   -- Pass rate and sample count per student model
   SELECT
       json_extract(data_json, '$.student')       AS student,
       AVG(json_extract(data_json, '$.v_ok_numeric')) AS pass_rate,
       COUNT(*)                                    AS n
   FROM responses
   GROUP BY student
   ORDER BY pass_rate DESC;

   -- Every response for one archetype, newest first
   SELECT
       json_extract(data_json, '$.batch')     AS generated_at,
       json_extract(data_json, '$.student')   AS student,
       json_extract(data_json, '$.output')    AS output
   FROM responses
   WHERE json_extract(data_json, '$.archetype') = 'Detached'
   ORDER BY generated_at DESC;

   -- Join back to run-level metadata (config, started_at)
   SELECT r.run_id, r.started_at, r.total_tasks,
          json_extract(resp.data_json, '$.v_ok_numeric') AS passed
   FROM runs r
   JOIN responses resp ON resp.run_id = r.run_id;

Real output from the first query above, against the 40-response ``mistral:7b-instruct-q4_K_M`` run
used throughout this session's Stage 10 verification::

    student                     pass_rate  n
    mistral:7b-instruct-q4_K_M  0.9        40

(36 of 40 responses had ``v_ok_numeric = 1`` -- a real number, not a placeholder.)
