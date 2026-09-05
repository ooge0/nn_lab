``tests/e2e/test_db_export_e2e.py`` (2 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Playwright E2E test for ``/db_export``'s "Export status" column --
specifically the htmx out-of-band (``hx-swap-oob``) update after a successful
export.

Why this needs a real browser and not ``TestClient``: the original bug (found
by the author from a real screenshot, not hypothetical) was a bare ``<td hx-
swap-oob="true">`` in the AJAX response -- valid as a string of HTML, but a
``<td>`` at the top level of a fragment (outside any ``<table>``/``<tr>``
context) gets mangled by the *browser's own* HTML table-parsing rules, so the
out-of-band swap silently failed to replace the existing cell content -- the
old "Not synced" badge and the new timestamp ended up stacked instead of one
replacing the other, until a full page reload re-parsed everything correctly.
``TestClient``-based integration tests (``test_db_export_api.py``) only ever
assert against the raw HTTP response text and structurally cannot catch this
class of bug -- they were green even with the broken ``<td>`` version, since
the OOB element's id/attributes were present in the string either way. Only a
real browser DOM, inspected after real parsing, proves the swap actually
replaced the cell rather than appending to it.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_export_status_cell_shows_only_the_new_timestamp_not_stacked_with_not_synced[chromium]``
     - Regression test for the exact bug reported: after clicking "Send to DB", the "Export status" cell must show only the fresh timestamp -- not "Not synced" and the timestamp both visible at once, which is what a mis-parsed out-of-band <td> swap produces.
   * - ``test_reexport_updates_the_sync_status_cell_to_the_new_timestamp_not_the_old_one[chromium]``
     - Regression test for the author's follow-up report: re-exporting an already-exported run (the "Re-export (overwrite)" button, a *different* element than the original "Send to DB" button, with its own hx-post/hx-target) must update the "Export status" cell to the new timestamp, not leave the old one in place or stack both.

``tests/e2e/test_experiments_e2e.py`` (13 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Playwright E2E tests for ``/experiments`` -- the first real browser-driven
layer this project has (CLAUDE.md SS7 names Playwright as a target layer;
before this file, zero infra existed anywhere in the repo -- see :doc:`qa`'s
former R37 gap). Scoped deliberately to what a real browser is *required* for:
the client-side JS added alongside this file (conditional field
enabling/disabling, dynamic sweep-parameter bounds, tab switching) is
invisible to ``TestClient``, which never executes JavaScript at all -- every
other test in this suite that touches ``/experiments`` tests the server side,
not this.

No real Ollama call happens anywhere here -- these tests exercise form
*behavior* (what becomes enabled/disabled/validated as fields change), not a
live generation run, so they're fast and don't depend on a local model being
pulled.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_sweep_fields_are_disabled_when_no_sweep_parameter_selected[chromium]``
     - Regression test for the reported bug: 'Steps' (and every other sweep sub-field) must be disabled while Sweep parameter = None, not silently editable with no effect.
   * - ``test_selecting_a_sweep_parameter_enables_mode_and_steps_and_delta_mode_fields[chromium]``
     - Choosing a real sweep parameter enables Mode/Steps, and (since Delta is the default mode) the Delta/Descending fields -- but not the MIN-MAX explicit fields.
   * - ``test_switching_sweep_mode_to_minmax_swaps_which_fields_are_enabled[chromium]``
     - Switching Mode from Delta to MIN-MAX disables Delta/Descending and enables the explicit min/max fields -- mutually exclusive, not all-editable at once.
   * - ``test_choosing_none_again_disables_every_sweep_field_again[chromium]``
     - Selecting a parameter then switching back to None re-disables everything -- the toggle is fully reversible, not one-way.
   * - ``test_sweep_min_max_bounds_are_real_per_parameter_not_a_fixed_fake_range[chromium-Temperature-0-2]``
     - Regression test: the explicit min/max fields' own min/max *attributes* (the browser-enforced bounds) must match the selected parameter's real valid range -- e.g. Top P must be bounded to [0, 1], not left at Temperature's [0, 2] regardless of which parameter is actually being swept, which would let an unskilled user submit a nonsensical value.
   * - ``test_self_critic_checkbox_disables_teacher_model_and_shows_hint[chromium]``
     - Checking self-critic disables the (now-irrelevant) teacher_model select and reveals the 'ignored while self-critic is on' hint.
   * - ``test_rag_enabled_checkbox_enables_rag_mode_and_top_k[chromium]``
     - RAG mode/Top-K start disabled and only become editable once 'Enable RAG' is checked.
   * - ``test_non_tuned_prompt_mode_disables_and_unchecks_exclude_archetype[chromium]``
     - 'Exclude archetype from prompt' only makes sense in Tuned mode -- switching away disables it and clears any existing check, rather than silently submitting a no-op checked value.
   * - ``test_submitting_with_no_archetypes_selected_is_blocked_by_the_browser[chromium]``
     - Regression test: student_models/archetypes are required selects; a browser must refuse to submit the form while archetypes has nothing selected (native HTML5 constraint validation), rather than silently POSTing a config that resolves to a real-but-empty 0-task run.
   * - ``test_preview_panel_updates_live_when_a_field_changes[chromium]``
     - Changing a real form field triggers a real htmx round-trip to /experiments/preview against the live server, and the setup summary panel reflects the new selection -- not just the bare task count.
   * - ``test_sweep_min_max_bounds_are_real_per_parameter_not_a_fixed_fake_range[chromium-Top P-0-1]``
     - Regression test: the explicit min/max fields' own min/max *attributes* (the browser-enforced bounds) must match the selected parameter's real valid range -- e.g. Top P must be bounded to [0, 1], not left at Temperature's [0, 2] regardless of which parameter is actually being swept, which would let an unskilled user submit a nonsensical value.
   * - ``test_sweep_min_max_bounds_are_real_per_parameter_not_a_fixed_fake_range[chromium-Frequency penalty--2-2]``
     - Regression test: the explicit min/max fields' own min/max *attributes* (the browser-enforced bounds) must match the selected parameter's real valid range -- e.g. Top P must be bounded to [0, 1], not left at Temperature's [0, 2] regardless of which parameter is actually being swept, which would let an unskilled user submit a nonsensical value.
   * - ``test_sweep_min_max_bounds_are_real_per_parameter_not_a_fixed_fake_range[chromium-Presence penalty--2-2]``
     - Regression test: the explicit min/max fields' own min/max *attributes* (the browser-enforced bounds) must match the selected parameter's real valid range -- e.g. Top P must be bounded to [0, 1], not left at Temperature's [0, 2] regardless of which parameter is actually being swept, which would let an unskilled user submit a nonsensical value.

``tests/e2e/test_tabs_chart_resize_e2e.py`` (1 test)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Playwright E2E test for the tabbed-page Plotly-width bug: a chart rendered
inside a hidden (``display: none``) ``.tab-panel`` gets measured by Plotly at
zero/collapsed width the moment its ``Plotly.newPlot()`` call runs (before
``tabs.js`` has applied ``.active`` to make the panel visible), and never
recovers until something fires a real browser ``resize`` event -- reported by
the author from a real screenshot: charts rendered narrower than their
container, fixed only by nudging the browser's zoom level. Server-rendered
``TestClient`` assertions cannot see this (the HTML string is identical either
way; only real browser layout geometry shows the collapsed width), so this
needs a real browser, same as the ``/db_export`` OOB-swap bug in
:mod:`tests.e2e.test_db_export_e2e`.

Uses a real run already on disk (created by the author, not this suite) if one
exists with a useful response count; skipped otherwise rather than fabricating
one, since NLP charts need a real multi-response run to render meaningfully.
See ``tests/e2e/conftest.py`` for ``live_server``/``page``.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_charts_in_the_default_and_a_switched_tab_both_render_at_full_container_width[chromium]``
     - Regression test for the reported bug: fixed by tabs.js explicitly calling Plotly.Plots.resize() on a panel's charts the moment that panel becomes .active, both on initial load (the default tab) and on every later click (a previously-hidden tab).

``tests/integration/test_analytics_api.py`` (8 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 8 read-side endpoints
(:mod:`api.routers.analytics`) -- through the real FastAPI app, with
``analytics._repository`` swapped for a fake so no real disk data is required
and no real Plotly-heavy computation is skipped (the charts are built for real
against fixture data, just not against a live-Ollama run).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_analytics_page_with_no_runs_shows_empty_state``
     - GET /analytics with zero persisted runs renders the empty-state message, not an error.
   * - ``test_analytics_page_renders_all_three_subtabs_for_a_populated_run``
     - GET /analytics with a real run renders all three sub-tab headings and at least one chart div per sub-tab.
   * - ``test_analytics_charts_fragment_for_known_run_returns_populated_charts``
     - GET /analytics/charts?run_id=... for a run with responses returns real chart HTML, not the empty state.
   * - ``test_analytics_charts_fragment_for_unknown_run_returns_404_with_message``
     - GET /analytics/charts?run_id=... for a run with no persisted responses returns 404, matching /runs/summary's convention.
   * - ``test_analytics_charts_does_not_500_on_a_sparse_pre_stage6_run``
     - Regression test for a real bug found on real disk data: an early (pre-Stage-6) export with only student/archetype/bias/duration_ms/output -- no teacher, no val, no metrics at all -- crashed the adherence sub-tab with a 500 because several charts assumed columns that simply weren't there. Must degrade gracefully instead (200, whatever charts the available columns support).
   * - ``test_analytics_charts_does_not_500_when_some_but_not_all_responses_lack_word_count``
     - Regression test for a real bug reproduced against a real 500-response live run: a Layer-0- rejected response (e.g. TRUNCATED) never gets word_count computed at all (ExperimentRunner._run_one skips metrics computation for it), so a run with even one such response alongside normal ones has a real, present-but-partially-NaN word_count column once loaded into a DataFrame. _add_if_present's column-existence check doesn't catch this -- most charts tolerate a NaN value, but the "Psycholinguistic signature" scatter uses word_count as Plotly marker `size`, whose validator rejects NaN outright and crashed the whole page with a real 500 (confirmed via a direct reproduction against live disk data, not assumed).
   * - ``test_analytics_charts_skips_high_dim_and_zipf_gracefully_when_columns_missing``
     - A run whose responses lack the high-dim/zipf columns renders the adherence charts but shows the graceful skip message for the others, not a 500.
   * - ``test_analytics_charts_include_prompt_strategy_charts_when_strategy_and_coherence_present``
     - Added 2026-08-24: 'strategy' was persisted on every response but never used as a chart grouping dimension anywhere -- these two charts answer 'does prompt structure affect stability.'

``tests/integration/test_api_status_api.py`` (3 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for :mod:`api.routers.api_status` -- through the real
FastAPI app (no fakes swapped in for the routers it checks, since the whole
point is verifying it exercises the *real* app, the same way a browser would).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_api_status_page_returns_200_and_reports_all_frontend_pages_checked``
     - Description is missing
   * - ``test_api_status_page_never_fires_side_effecting_or_streaming_routes``
     - The 'Not fired' section lists these routes by name -- confirms they're documented as skipped, not silently omitted or (worse) actually called.
   * - ``test_api_status_page_skips_run_id_routes_gracefully_when_no_runs_exist``
     - With zero runs in the live JSONLStore directory, run_id-needing backend routes must report a clear skip, not a 500 or a fabricated run_id.

``tests/integration/test_benchmark_api.py`` (4 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 12 read-side endpoints
(:mod:`api.routers.benchmark`) -- through the real FastAPI app, with
``benchmark._repository`` swapped for a fake so no real disk data is required.
Charts/aggregation are built for real against fixture data, not mocked out.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_benchmark_page_with_no_runs_shows_empty_state``
     - GET /benchmark with zero persisted runs renders the empty-state message, not an error.
   * - ``test_benchmark_report_renders_overview_and_leaderboard_for_a_populated_run``
     - GET /benchmark/report?run_id=... for a fully-populated run renders overview, charts, and a leaderboard with a champion.
   * - ``test_benchmark_report_for_unknown_run_returns_404_with_message``
     - GET /benchmark/report?run_id=... for a run with no persisted responses returns 404, matching the other read-side routers' convention.
   * - ``test_benchmark_report_degrades_gracefully_on_a_sparse_pre_stage5_run``
     - Regression coverage mirroring Stage 8's own real-data finding: a run missing required columns (student/teacher/word_count/v_ok/...) must show a clear message, not 500.

``tests/integration/test_clusters_api.py`` (4 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 10 read-side endpoints
(:mod:`api.routers.clusters`) -- through the real FastAPI app, with
``clusters._repository`` swapped for a fake so no real disk data is required.
Kept to a small number of full-clustering tests deliberately -- UMAP/HDBSCAN
fitting takes real seconds even on synthetic data, and the computation itself
is already thoroughly covered by ``tests/unit/test_cluster_discovery.py``'s
unit tests. These tests confirm routing/wiring, not re-verify the algorithms.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_clusters_page_with_no_runs_shows_empty_state``
     - GET /clusters with zero persisted runs renders the empty-state message, not an error.
   * - ``test_clusters_charts_fragment_for_unknown_run_returns_404_with_message``
     - GET /clusters/charts?run_id=... for a run with no persisted responses returns 404, matching /analytics/charts's convention.
   * - ``test_clusters_charts_degrades_gracefully_with_too_few_responses``
     - A run with only a couple of responses (below every clustering algorithm's minimum) renders the graceful 'not enough data' messages, not a 500.
   * - ``test_clusters_page_renders_all_three_subtabs_for_a_populated_run``
     - GET /clusters with enough real data renders K-Means, HDBSCAN, and Behavioral topology charts -- the one full end-to-end run through the whole pipeline.

``tests/integration/test_db_export_api.py`` (12 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for :mod:`api.routers.db_export` -- through the real
FastAPI app, with ``db_export._repository`` swapped for a fake so no real disk
data is required. The target side is a real temp-file SQLite database (see
:mod:`tests.unit.test_db_export`'s docstring for why ``:memory:`` can't
exercise the overwrite/collision path) -- ``core.services.db_export`` itself
constructs its own ``SQLiteRepo``, so the test points it at a temp path via
monkeypatching the default rather than mocking SQLite out entirely.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_db_export_page_with_no_runs_shows_empty_state``
     - Description is missing
   * - ``test_db_export_page_lists_runs_with_a_send_to_db_button``
     - Description is missing
   * - ``test_db_export_page_has_bulk_select_checkboxes_wired_to_each_rows_own_button``
     - Bulk export deliberately has no separate backend endpoint -- the 'Send selected to DB' button just triggers each checked row's own existing button (htmx.trigger), so per-row conflict resolution stays identical to a manual single click. Confirms the wiring is present: a select-all checkbox, one checkbox per row carrying its row index, and each row's action button having the matching id the bulk-trigger JS looks up.
   * - ``test_export_run_copies_responses_and_reports_success``
     - Description is missing
   * - ``test_export_run_for_unknown_run_shows_a_clear_error_not_a_500``
     - Description is missing
   * - ``test_export_run_twice_without_overwrite_shows_already_exported_with_a_reexport_action``
     - Description is missing
   * - ``test_export_run_with_overwrite_true_replaces_rather_than_erroring``
     - Description is missing
   * - ``test_export_failure_for_one_run_does_not_report_success_for_a_different_run``
     - Two runs visible on the same /db_export page each get their own status fragment (id="db-export-result-{run_id}") so htmx swaps the right row -- confirms a failed export for one run's response fragment never mentions the other run's id or a stray success badge, which would indicate the two rows' results got crossed.
   * - ``test_db_export_page_shows_not_synced_for_a_run_never_exported``
     - Description is missing
   * - ``test_db_export_page_shows_the_real_synced_timestamp_after_an_export``
     - Export a run, then reload the page (a fresh GET, simulating a browser refresh) -- the 'Export status' column must show a real timestamp, not 'Not synced', once the run is actually in the database.
   * - ``test_export_run_response_includes_an_out_of_band_update_for_the_sync_status_cell``
     - A successful export's response fragment carries an hx-swap-oob element updating the 'Export status' cell in place, so the new timestamp appears without a page reload.
   * - ``test_export_run_that_fails_does_not_include_a_sync_status_oob_update``
     - Nothing actually changed in the database on a failed export -- the OOB fragment (and its 'Not synced'-vs-timestamp decision) should not be emitted at all, not emitted with a stale or fabricated value.

``tests/integration/test_demo_api.py`` (4 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 1 SSE + background-thread demo
(:mod:`api.routers.demo`) -- proving the mechanism end-to-end through the real
FastAPI app, not just its isolated helper (see ``test_demo_queue_bridge.py``
for that).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_start_returns_202_with_sse_fragment``
     - POST /demo/start launches a run and returns the htmx SSE-connect fragment.
   * - ``test_second_concurrent_start_is_rejected``
     - A second POST /demo/start while one is in flight is rejected with 409 (the concurrent-run guard).
   * - ``test_stream_yields_all_progress_events_in_order_then_closes``
     - GET /demo/stream, after a start, yields exactly N ordered progress events then progress-done.
   * - ``test_stream_without_a_started_run_sends_error_and_closes``
     - GET /demo/stream with no run ever started sends a single error event, not a hang.

``tests/integration/test_experiments_api.py`` (22 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 6 experiment endpoints
(:mod:`api.routers.experiments`) -- through the real FastAPI app, with
``experiments._runner`` swapped for a fake-backed ``ExperimentRunner`` so no
real Ollama call or disk write happens.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_experiments_page_lists_archetypes_and_prompt_modes``
     - GET /experiments renders the real archetype names and prompt-mode options, not a placeholder form.
   * - ``test_experiments_page_renders_a_real_initial_preview_not_undefined``
     - Regression test: the initial GET must render a real setup-summary preview matching the form's own hardcoded defaults, not crash with a Jinja2 UndefinedError -- the preview fragment is now included directly on first paint (not just after a POST /experiments/preview), so the page-load handler must supply the same context shape.
   * - ``test_preview_renders_the_full_setup_summary_including_sweep_range``
     - POST /experiments/preview shows a full recap (students/archetypes/biases/judge/sweep), including the real computed sweep value list, not just the bare task count.
   * - ``test_preview_shows_no_sweep_when_sweep_param_is_unset``
     - When sweep_param is empty, the preview clearly states no sweep is active, rather than showing a stale or misleading range.
   * - ``test_preview_returns_total_tasks_without_starting_anything``
     - POST /experiments/preview computes and returns the real total_tasks count for the submitted config, without starting a run (runner.running stays False).
   * - ``test_start_returns_202_with_sse_fragment``
     - POST /experiments/start with a valid config returns 202 and the htmx SSE-connecting fragment, not a full page.
   * - ``test_start_over_the_cap_returns_413_and_does_not_start``
     - A config computing to more than the configured max_total_tasks cap is refused with 413 before any generation starts.
   * - ``test_second_concurrent_start_is_rejected``
     - A second POST /experiments/start while one is already running is rejected with 409, at the API layer (the concurrent-run guard's HTTP-facing behavior).
   * - ``test_stop_with_no_run_in_progress_returns_409``
     - POST /experiments/stop with nothing running is refused with 409, at the API layer -- there is nothing to stop.
   * - ``test_stop_mid_run_returns_200_and_the_run_actually_halts_early``
     - POST /experiments/stop while a run is in progress returns 200 and asks the background thread to halt -- restores the legacy sidebar's "Stop generation" button. Confirmed via the runner's own guard clearing (not stuck "running" forever) and fewer than the full 2 responses persisted (the run started with 2 archetypes -> total_tasks=2).
   * - ``test_self_critic_checkbox_is_honored``
     - When the self_critic checkbox is present, the fake judge is called with the student model.
   * - ``test_split_biases_produces_one_entry_per_bias``
     - split_biases=on with a comma-separated biases_raw string generates one response per bias, not one response for the whole raw string.
   * - ``test_rag_enabled_lazily_builds_the_knowledge_base``
     - rag_enabled=on triggers _get_knowledge_base(), which is monkeypatched here to avoid a real model load.
   * - ``test_get_knowledge_base_does_not_cache_a_failed_load``
     - Regression test for the caching bug itself (not just the route's error handling): _get_knowledge_base() must leave the module-level cache at None after a failed load_knowledge_base() call, so a later call can retry -- not permanently reuse a half-built, never-loaded instance.
   * - ``test_rag_enabled_with_unbuildable_knowledge_base_returns_400_not_500``
     - Regression test: if RAGEngine.load_knowledge_base raises (e.g. an empty knowledge/rag/ directory -- ValueError -- or an unreadable one -- RuntimeError), the route must return a clean 400 with the fragment template, not let the exception propagate into a bare 500. Also confirms the module-level knowledge-base cache stays None afterward (not permanently poisoned by a half-built instance), so a later request can retry once the underlying problem is fixed.
   * - ``test_progress_fragment_renders_a_real_progress_element_not_just_text``
     - Regression test: every non-terminal progress fragment must include a real <progress> element (previously this was plain text with no visual indicator at all -- a real UX gap, not a styling nicety).
   * - ``test_progress_fragment_on_done_links_to_every_read_side_page``
     - The terminal 'done' fragment links directly to /runs, /analytics, /nlp, /clusters -- previously there was no way to reach results from the progress view at all.
   * - ``test_progress_fragment_on_stopped_reports_partial_progress_and_links_to_results``
     - The terminal 'stopped' fragment (from a Stop-button click) reports how many responses actually completed and still links to the read-side pages -- partial results are real results, not discarded.
   * - ``test_progress_fragment_while_in_progress_includes_a_stop_button``
     - Every non-terminal fragment (started/generating) includes a real Stop button, restoring the legacy sidebar's 'Stop generation' control.
   * - ``test_progress_fragment_on_terminal_stages_omits_the_stop_button``
     - done/stopped/error fragments do not show a Stop button -- there is nothing left to stop once the run has already ended.
   * - ``test_progress_fragment_on_error_shows_the_message``
     - The terminal 'error' fragment shows the real error text, not a generic message.
   * - ``test_stream_without_a_started_run_sends_error_and_closes``
     - GET /experiments/stream with no active run (queue is None) sends an error event and closes immediately, rather than hanging.

``tests/integration/test_faq_api.py`` (4 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 14 ``/faq`` endpoint
(:mod:`api.routers.faq`) -- through the real FastAPI app, against the real
``faq_eng.md``/``faq_ua.md`` files on disk (no fakes -- there's no persisted-
run data involved in this tab at all).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_faq_defaults_to_english``
     - GET /faq with no lang param renders faq_eng.md's real content as HTML.
   * - ``test_faq_renders_ukrainian_when_selected``
     - GET /faq?lang=Українська renders faq_ua.md, a different file than the English default.
   * - ``test_faq_with_unknown_language_shows_inline_error_not_500``
     - GET /faq?lang=Klingon (not a real option) shows an inline 'not found' message, not a crash.
   * - ``test_faq_page_includes_language_switch_links``
     - The rendered page includes links for both known languages, matching the legacy segmented control's options.

``tests/integration/test_model_evo_api.py`` (7 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 11 read-side endpoints
(:mod:`api.routers.model_evo`) -- through the real FastAPI app, with
``model_evo._repository`` swapped for a fake so no real disk data is required.
:class:`~core.analysis.model_evaluation.ModelEvaluation` runs for real against
synthetic fixture data, not mocked out.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_model_evo_page_with_no_runs_shows_empty_state``
     - GET /model_evo with zero persisted runs renders the empty-state message, not an error.
   * - ``test_model_evo_targets_lists_discrete_columns_for_a_populated_run``
     - GET /model_evo/targets?run_id=... lists archetype/student/bias as candidate targets (2-10 unique values, non-float).
   * - ``test_model_evo_targets_for_unknown_run_returns_404_with_message``
     - GET /model_evo/targets?run_id=... for a run with no persisted responses returns 404, matching /nlp/charts's convention.
   * - ``test_model_evo_evaluate_renders_real_metrics_and_charts``
     - POST /model_evo/evaluate for a real classifiable dataset returns real precision/ROC-AUC numbers and chart HTML, not an error.
   * - ``test_model_evo_evaluate_with_too_few_rows_renders_inline_error_not_500``
     - POST /model_evo/evaluate against a dataset under ModelEvaluation's own 10-row minimum shows an inline error, not a 500.
   * - ``test_model_evo_evaluate_with_missing_target_column_renders_inline_error``
     - POST /model_evo/evaluate with a target_column not present in the data shows an inline error, not a 500.
   * - ``test_model_evo_evaluate_for_unknown_run_returns_404``
     - POST /model_evo/evaluate for a run with no persisted responses returns 404.

``tests/integration/test_monitor_api.py`` (6 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 13 read-side endpoint
(:mod:`api.routers.monitor`) -- through the real FastAPI app, with
``monitor._repository`` swapped for a fake so no real disk data is required.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_monitor_page_with_no_runs_shows_empty_state``
     - GET /monitor with zero persisted runs renders the empty-state message, not an error.
   * - ``test_monitor_schema_reports_correct_dtypes_for_a_populated_run``
     - GET /monitor/schema?run_id=... reports the real row/column counts and dtype names for a fixture run.
   * - ``test_monitor_schema_for_unknown_run_returns_404_with_message``
     - GET /monitor/schema?run_id=... for a run with no persisted responses returns 404, matching the other read-side routers' convention.
   * - ``test_monitor_schema_includes_a_data_preview_table``
     - GET /monitor/schema?run_id=... includes a rendered preview table with real cell values, not just the dtypes.
   * - ``test_monitor_schema_default_view_truncates_to_20_rows_with_a_show_all_link``
     - Regression test for the "view JSONL as a table" gap: by default only the first 20 rows render, but a real "Show all N rows" link to ?full=true is present so every row is genuinely reachable, not just the preview -- the direct replacement for the legacy Streamlit app's full-table view.
   * - ``test_monitor_schema_full_true_returns_every_row``
     - GET /monitor/schema?run_id=...&full=true returns all 25 rows, not just the 20-row preview.

``tests/integration/test_nlp_api.py`` (5 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 9 read-side endpoints
(:mod:`api.routers.nlp`) -- through the real FastAPI app, with
``nlp._repository`` swapped for a fake so no real disk data is required.
Charts are built for real against fixture data (via the real
``LabDataBridge``), not mocked out.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_nlp_page_with_no_runs_shows_empty_state``
     - GET /nlp with zero persisted runs renders the empty-state message, not an error.
   * - ``test_nlp_page_renders_all_three_subtabs_for_a_populated_run``
     - GET /nlp with a real run renders all three sub-tab headings and real chart HTML.
   * - ``test_nlp_charts_fragment_for_known_run_returns_populated_charts``
     - GET /nlp/charts?run_id=... for a run with responses returns real chart HTML, not the empty state.
   * - ``test_nlp_charts_fragment_for_unknown_run_returns_404_with_message``
     - GET /nlp/charts?run_id=... for a run with no persisted responses returns 404, matching /analytics/charts's convention.
   * - ``test_nlp_charts_uses_self_focus_ext_not_self_focus_for_neuro_self_focus``
     - Regression coverage at the API level for the LabDataBridge fix: a run whose responses have deliberately different self_focus (0.9) vs self_focus_ext (0.05) must not crash, and must render successfully using the corrected mapping (verified at the unit level in test_contract.py; this just confirms the whole path from a persisted response through to rendered HTML doesn't error).

``tests/integration/test_runs_api.py`` (7 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the Stage 7 read-side endpoints
(:mod:`api.routers.runs`) -- through the real FastAPI app, with
``runs._repository``/``runs._metrics_engine`` swapped for fakes so no real
disk data is required.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_runs_page_with_no_runs_shows_empty_state``
     - GET /runs with zero persisted runs renders the empty-state message, not an error.
   * - ``test_runs_page_selects_most_recently_started_run_by_default``
     - GET /runs with multiple runs pre-selects the one with the latest started_at and shows its summary.
   * - ``test_run_summary_fragment_for_known_run_returns_populated_table``
     - GET /runs/summary?run_id=... for a run with responses returns the populated summary fragment.
   * - ``test_run_summary_fragment_for_unknown_run_returns_404_with_message``
     - GET /runs/summary?run_id=... for a run with no persisted responses returns 404, not a 500 or an empty table.
   * - ``test_runs_page_renders_the_judging_comparison_picker``
     - GET /runs with runs present shows the self-critic-vs-teacher-judging comparison form.
   * - ``test_judging_comparison_fragment_shows_pass_rates_and_delta``
     - GET /runs/judging_comparison for a self-critic run and a teacher-judged run renders both pass rates, both mode labels, and the delta -- a real end-to-end check of the router wiring, not just the underlying MetricsEngine call (already unit-pinned separately).
   * - ``test_judging_comparison_fragment_for_unknown_run_returns_404_with_message``
     - GET /runs/judging_comparison where one run_id has no persisted responses returns 404, not a 500.

``tests/integration/test_status_api.py`` (4 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functional API tests for the ``/status`` endpoint (:mod:`api.routers.status`)
-- through the real FastAPI app, with the underlying :func:`core.services.stat
us_checks.check_ollama`/``check_nltk``/``check_spacy`` swapped for
deterministic fakes so this suite doesn't depend on a real local Ollama
server, NLTK data directory, or spaCy model being present.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_status_json_reports_all_three_services_and_an_overall_flag``
     - GET /status returns all three checks verbatim plus an all_ok flag that is False when any one service is down.
   * - ``test_status_json_all_ok_true_when_every_service_is_up``
     - all_ok flips to True only when every service reports ok.
   * - ``test_status_json_all_ok_false_when_only_spacy_is_down``
     - A down spaCy alone (Ollama/NLTK both up) is enough to flip all_ok to False -- confirms spaCy is a real part of the aggregate, not just appended to the list without affecting the flag.
   * - ``test_status_widget_renders_a_badge_per_service_with_ok_fail_classes``
     - GET /status/widget renders one badge per service, with the ok/fail CSS class and a human-readable label matching each check's actual state.

``tests/legacy_rag/test_contract.py`` (9 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_full_pipeline_alignment``
     - Ensures raw JSON data correctly flows through the Bridge into the Schema and finally into a DataFrame with the exact keys required by Plotly.
   * - ``test_alias_regression_check``
     - Verify that providing 'neuro_self_focus' directly works and isn't ignored in favor of an old 'self_focus' alias.
   * - ``test_neuro_self_focus_prefers_ext_over_base_on_a_flat_stage6_style_entry``
     - Regression test for a real bug: ExperimentRunner (Stage 6) persists real entries *flat*, not nested under nlp_raw/neuro_raw (confirmed against a live-generated JSONL entry, not assumed) -- with self_focus (PsychScientist, broad pronoun set) and self_focus_ext (NeuroMetrics, narrower set) as two separate top-level keys. transform_raw's neuro_self_focus mapping previously read the bare "self_focus" key unconditionally, silently mislabeling PsychScientist's value as NeuroMetrics' on every real, current entry. Must prefer self_focus_ext.
   * - ``test_neuro_self_focus_falls_back_to_bare_key_for_pre_stage6_entries``
     - A flat entry with only the old-style bare 'self_focus' key (no _ext) still resolves -- historical exports aren't left broken.
   * - ``test_schema_parsing``
     - Description is missing
   * - ``test_dataframe_build``
     - Description is missing
   * - ``test_no_nan_critical``
     - Description is missing
   * - ``test_pos_mapping``
     - Description is missing
   * - ``test_neuro_fields_prefixed``
     - Description is missing

``tests/legacy_rag/test_ingestion_robustness.py`` (5 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_load_knowledge_base_error_handling``
     - Verify engine raises correct errors for missing or empty paths.
   * - ``test_metadata_integrity``
     - Best Practice: Ensure archetype label is correctly mapped from filename.
   * - ``test_retrieval_isolation_negative``
     - Critical Test: Ensure that asking for a archetype that exists returns data, but asking for one that doesn't returns an empty list (Isolation check).
   * - ``test_chunk_granularity``
     - Verify that every line in a file is treated as a unique chunk.
   * - ``test_query_before_load_safety``
     - Ensure the app doesn't crash if a user triggers a query before RAG is loaded.

``tests/legacy_rag/test_rag.py`` (12 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_chunks_loaded``
     - Ensure the knowledge base is not empty after ingestion.
   * - ``test_all_archetypes_present``
     - Ensure all expected archetype categories exist in the loaded dataset.
   * - ``test_valid_domains``
     - Ensure all ingested chunks adhere to the allowed domain labels (schema validation). Fixed 2026-08-24: the allowed set was a stale, lowercase 5-item list (behavior/speech/cognition/trigger/emotion) that no longer matched the real ``knowledge/rag/*.txt`` taxonomy at all -- confirmed directly by loading the real knowledge base and listing every domain actually present, not guessed. The real taxonomy is Capitalized and has grown to 8 categories; "emotion" doesn't appear in the real data at all. This was a stale test fixture, not an ingestion bug -- nothing about RAGEngine/FAISSVectorStore changed.
   * - ``test_no_empty_chunks``
     - Safety check: Ensure no empty or broken content chunks were ingested.
   * - ``test_chunk_length_quality``
     - Quality Gate: Ensure chunks are not degenerate (too short to provide context). Allow max 10% of short chunks if they are specific triggers.
   * - ``test_retrieval_returns_results``
     - Verify that the vector store (e.g., FAISS) returns valid results for a basic query.
   * - ``test_paranoid_signal_retrieval``
     - Semantic test: Ensure a query with strong paranoid keywords returns paranoid-tagged content.
   * - ``test_retrieval_boundary_isolation``
     - Isolation test: Ensure a query for 'Structured' traits does not leak 'Expressive' content. Prevents cross-contamination in the vector space.
   * - ``test_cosine_alignment_integrity``
     - Validate that the embedding model correctly ranks semantic similarity. Reference RAG chunk should have higher similarity to a relevant query than to noise. Fixed 2026-08-24: the embedding model lives on the vector store (FAISSVectorStore.model, core/adapters/rag/vector_store.py), not directly on RAGEngine -- ``rag.model`` never existed; ``test_valid_domains`` right above this test already correctly uses the ``rag.store.*`` path. A one-attribute-path typo, not an API/architecture change.
   * - ``test_weighted_drift_calculation``
     - Validate the Drift Index formula. Checks if the system correctly identifies 'Out of Character' responses based on weighted attributes.
   * - ``test_retrieval_sanity_loop``
     - Comprehensive smoke test for a variety of archetype queries. Prints retrieval details for manual inspection during debugging.
   * - ``test_feature_correlation_consistency``
     - Structural Integrity Check: Ensures that the correlation between traits in the model output matches the correlation structure of the 'Ground Truth' dataset. This detects 'Psychological Chimera'—responses where individual scores might seem okay, but the combination of traits is logically impossible for the given archetype.

``tests/legacy_rag/test_rag_logic.py`` (3 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_filtered_semantic_retrieval``
     - Archetype-filtered retrieval isolates the target archetype and returns semantically relevant content, checked against a broader keyword set. Superseded 2026-08-24's own stale twin, ``test_filtered_semantic_retrieval_old`` (deleted): that version checked only for the literal words "conceptual"/"abstract" in the top hit, which broke once ``knowledge/rag/schizoid.txt``'s content was reworded -- the real top hit ("Limited social signaling, low need for reciprocal engagement.") is a genuinely correct, on-topic match, it just doesn't happen to contain those two specific words. This version already used a broader keyword set and was already passing before the old twin was removed, matching the ``data_contract.py``/``data_contract_old.py`` precedent -- keep the real one, drop the stale duplicate rather than patching a test that was already superseded.
   * - ``test_unfiltered_retrieval_ranking``
     - Debug test: See what is actually coming back first when unfiltered.
   * - ``test_empty_query_handling``
     - Ensure the system doesn't crash on empty or nonsensical input.

``tests/unit/test_benchmark_charts.py`` (3 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :func:`web.plotting.benchmark_charts.build_benchmark_view` --
specifically the ``/benchmark`` leaderboard's ``final_score`` formula, pinned
directly against a small synthetic DataFrame rather than only observed
indirectly through rendered HTML (the existing
``tests/integration/test_benchmark_api.py`` coverage). Written alongside two
real bugs found and fixed 2026-08-24 in the same block of code -- see
``web/plotting/benchmark_charts.py``'s own inline comments and
``docs/source/wiki/04-llm-analytics.rst``'s "A metric that contradicted
itself" section for the full story:

1. The leaderboard used to weight a ``mimicry_score`` derived from
``semantic_overlap`` -- a field that measures similarity to the bias/archetype
*label*, not to any teacher response, and which the Layer 1 echo-detection
cascade (``core/analysis/response_classification.py``) rejects responses for
when it is *high*. The leaderboard was rewarding the same behavior the cascade
flags as a failure. Removed, not replaced with a different unvalidated proxy.
2. The pass-rate component aggregated ``v_ok_numeric`` from ``df_valid``
(already filtered to ``v_ok == 1``), whose mean is trivially always 1.0 for
any student with at least one passing response -- a real 50% pass rate and a
real 100% pass rate scored identically. Fixed to use the real, un-filtered
per-student mean.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_leaderboard_final_score_matches_the_documented_formula_exactly``
     - final_score = 0.4*pass_rate + 0.3*coherence + 0.3*speed_score, hand-computed on a fixed input.
   * - ``test_leaderboard_pass_rate_is_not_trivially_always_one``
     - Regression test for the df_valid-mean bug: a 50% and a 100% pass rate must differ in the table.
   * - ``test_leaderboard_no_longer_contains_mimicry_score_or_semantic_overlap``
     - Regression test for the removed field: neither name should appear in the rendered table at all.

``tests/unit/test_calculate_advanced_linguistic_metrics.py`` (9 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.analysis.calculate_advanced_linguistic_metrics` --
pinning ``semantic_overlap`` (real sentence-embedding cosine similarity) on
known-similar/known-dissimilar text pairs, per CLAUDE.md SS7's "pin expected
outputs on known inputs" requirement for borrowed math. Previously untested:
this module had no dedicated test file before this one, despite computing
several metrics persisted on every response.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_semantic_similarity_of_identical_text_is_exactly_one``
     - The same string compared to itself has cosine similarity 1.0 (up to floating-point rounding).
   * - ``test_semantic_similarity_of_near_paraphrases_is_high``
     - Two sentences expressing the same idea in different words score a high similarity -- this is the whole point of using embeddings instead of token overlap.
   * - ``test_semantic_similarity_of_unrelated_text_is_low``
     - Two sentences about genuinely unrelated topics score a low similarity, not a coincidentally-inflated one from shared common words alone.
   * - ``test_semantic_similarity_is_symmetric``
     - Order of the two texts must not change the result -- cosine similarity is inherently symmetric, and the wiring around it shouldn't break that.
   * - ``test_semantic_similarity_returns_zero_for_an_empty_text_not_a_model_call``
     - An empty string on either side returns 0.0 directly -- embedding an empty string isn't a meaningful comparison, and this guard avoids sending one to the model at all.
   * - ``test_semantic_similarity_is_clamped_to_zero_one_range``
     - The returned value never falls outside [0.0, 1.0], even though raw cosine similarity is mathematically defined on [-1.0, 1.0] -- a negative value would break is_echo_response's threshold comparison downstream.
   * - ``test_semantic_overlap_field_uses_real_similarity_not_token_overlap``
     - Regression test for a real bug: this field used to be a plain Jaccard token-set overlap despite being named "semantic_overlap" -- found during a wiki audit of what the project's metrics actually measure. These two sentences share zero literal words but mean nearly the same thing; a token-overlap score would be ~0.0, a real semantic-similarity score should be high.
   * - ``test_semantic_overlap_field_is_low_for_dissimilar_output``
     - A response that's entirely off-topic from the prompt scores a low semantic_overlap, not an artificially inflated one.
   * - ``test_other_fields_unaffected_by_the_semantic_overlap_fix``
     - levenshtein_dist/expansion_ratio/word_count/unique_ratio are untouched by this fix -- pinned on a fixed input to confirm the surrounding metrics didn't shift.

``tests/unit/test_cli_manage.py`` (11 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for :mod:`cli.manage` -- the operational console
(``serve``/``status``/``list-runs``/ ``export-db``). Each subcommand's real
dependency (``uvicorn.run``, the status checks, ``JSONLStore``,
``export_run_to_db``) is monkeypatched at the point ``cli.manage`` imports it,
not mocked out at a lower level -- so these tests exercise the real argument
parsing and dispatch, only faking the side-effecting call each command
ultimately makes.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_serve_calls_uvicorn_run_with_the_parsed_host_and_port``
     - Description is missing
   * - ``test_serve_no_reload_flag_disables_reload``
     - Description is missing
   * - ``test_status_prints_every_check_and_returns_0_when_all_ok``
     - Description is missing
   * - ``test_status_returns_1_when_any_check_fails``
     - Description is missing
   * - ``test_list_runs_prints_every_run_most_recent_first``
     - Description is missing
   * - ``test_list_runs_with_no_runs_prints_a_clear_message_not_a_blank_screen``
     - Description is missing
   * - ``test_export_db_prints_a_success_message_and_returns_0``
     - Description is missing
   * - ``test_export_db_passes_through_custom_db_path_and_overwrite_flag``
     - Description is missing
   * - ``test_export_db_on_error_prints_to_stderr_and_returns_1``
     - Description is missing
   * - ``test_build_parser_requires_a_subcommand``
     - Description is missing
   * - ``test_build_parser_export_db_requires_a_run_id``
     - Description is missing

``tests/unit/test_cli_run_experiment.py`` (6 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for :mod:`cli.run_experiment` -- Stage 15's config-driven batch runner.
``run()`` is exercised against a real ``ExperimentRunner`` wired with the same
fake adapters (:class:`~tests.unit.test_experiment_runner
.FakeLLMClient`/``FakeRepository``/``FakePromptStrategy``/``FakeJudge``) Stage
6's own tests use -- no orchestration logic is duplicated or mocked out, only
the adapters are fake. ``main()`` is exercised end to end against a real temp
TOML file, with :func:`cli.run_experiment.build_runner` monkeypatched to
return the same fake-wired runner (avoiding a real Ollama call for a test).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_load_config_parses_a_valid_toml_file_into_experiment_config``
     - A well-formed TOML file loads into an ExperimentConfig with the exact declared values.
   * - ``test_load_config_raises_on_a_config_missing_a_required_field``
     - A TOML file missing a required field (student_models) raises pydantic's own validation error, not a CLI-specific one.
   * - ``test_run_prints_progress_and_done_lines_and_persists_every_response``
     - run() prints one progress line per response plus a final Done line, and the fake repository receives every generated response.
   * - ``test_run_rejects_an_invalid_config_before_starting_and_returns_1``
     - A config with a sweep_param but no resolved sweep_min/sweep_max is rejected by try_start's own validation, printed as an ERROR line, exit code 1.
   * - ``test_run_reports_an_already_running_guard_as_exit_1``
     - If try_start returns None (a run already in progress), run() reports it clearly rather than hanging or crashing.
   * - ``test_main_end_to_end_with_a_real_config_file_and_a_monkeypatched_runner``
     - main() parses --config, loads the real file, and drives a (monkeypatched, fake-adapter) runner to completion.

``tests/unit/test_cluster_discovery.py`` (17 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.services.cluster_discovery` -- Stage 10.

``compute_fit_indices`` is pure, deterministic math (scikit-learn metric
functions over already-fixed embeddings/labels, no randomness) and is pinned
exactly on a fixed synthetic dataset, per CLAUDE.md SS7. The UMAP/HDBSCAN-
driven functions (``run_plain_hdbscan``, ``run_behavioral_topology``) are
*not* pinned to exact cluster-ID assignments -- cluster label numbering is
algorithm-internal and not guaranteed stable across scikit-learn/hdbscan/umap-
learn versions or platforms even with a fixed ``random_state``, so pinning
exact IDs would make the suite fragile for the wrong reason. Instead they're
tested structurally: correct columns, correct shapes, correct filtering
behavior, outlier-subset correctness.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_compute_fit_indices_pinned_on_two_perfectly_separated_clusters``
     - Two tight, far-apart 2-point clusters -> silhouette should be very close to 1 (perfect separation), Davies-Bouldin very close to 0 (tight, well-separated clusters), computed by scikit-learn directly so this pins *our wiring* of those functions, not their internal math.
   * - ``test_compute_fit_indices_single_cluster_uses_legacy_sentinels``
     - A single cluster (nothing to separate) can't compute silhouette/DBI -- matches the legacy app's own 0.0/99.0 sentinels, not a crash.
   * - ``test_compute_fit_indices_ari_with_perfect_archetype_alignment``
     - ARI == 1.0 when cluster labels perfectly match the ground-truth archetype grouping.
   * - ``test_compute_fit_indices_noise_ratio``
     - noise_ratio is the fraction of rows labeled -1 (HDBSCAN's noise sentinel).
   * - ``test_run_plain_hdbscan_adds_cluster_columns``
     - cluster_id and cluster_name columns get added, cluster_name derived correctly from cluster_id.
   * - ``test_run_plain_hdbscan_is_a_no_op_when_too_few_rows``
     - A dataset smaller than min_cluster_size is returned unchanged, not crashed on.
   * - ``test_run_behavioral_topology_adds_expected_columns``
     - x_vis/y_vis/cluster_id/cluster_name all get added, one row per (filtered) input row.
   * - ``test_run_behavioral_topology_filters_invalid_responses_when_requested``
     - filter_v_ok=True drops rows where v_ok_numeric == 0.
   * - ``test_run_behavioral_topology_filters_short_outputs``
     - min_words drops rows whose output has fewer words than the threshold.
   * - ``test_run_behavioral_topology_outliers_are_the_noise_labeled_subset``
     - outliers is exactly the cluster_id == -1 subset of df, nothing more or less.
   * - ``test_run_behavioral_topology_does_not_crash_when_filtering_removes_every_row``
     - Regression test for a real bug: filtering can legitimately leave zero rows (e.g. every response shorter than min_words), which crashed StandardScaler/UMAP with a 0-sample ValueError before this was guarded. Must return a usable (empty) result instead.
   * - ``test_run_behavioral_topology_fit_indices_has_all_expected_keys``
     - fit_indices always has the four expected keys, values are floats.
   * - ``test_cluster_discovery_process_data_adds_expected_columns``
     - process_data adds cluster_id (str), x, y (PCA coords) -- no unit test existed for this pre-existing module before Stage 10.
   * - ``test_cluster_discovery_is_a_no_op_when_fewer_rows_than_n_clusters``
     - Regression test for a real bug: KMeans(n_clusters=3) raised ValueError('n_samples=2 should be >= n_clusters=3') instead of degrading gracefully like the empty-columns case -- caught by Stage 10's own functional API test against a small synthetic run, not hypothetical. Must return df unmodified, matching the existing empty-columns contract.
   * - ``test_cluster_discovery_is_a_no_op_on_empty_numeric_data``
     - A DataFrame with no numeric columns at all is returned unchanged, not crashed on.
   * - ``test_cluster_discovery_component_dependencies_available_after_process_data``
     - get_component_dependencies returns PC1/PC2 loadings after process_data has fit the PCA, keyed by feature name.
   * - ``test_cluster_discovery_component_dependencies_none_before_fit``
     - Before process_data ever runs, get_component_dependencies returns (None, None) rather than raising.

``tests/unit/test_config_loader_short.py`` (4 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`utils.config_loader_short`'s dynamic ``__getattr__``
resolver -- specifically the ``[EXPERIMENT]`` section added for the Stage 6
total_tasks sanity cap, plus a regression check that the pre-existing sections
it resolves (used by the live legacy app and by
:mod:`core.adapters.ollama_client`/:mod:`core.adapters.jsonl_store`) are still
untouched.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_max_total_tasks_resolves_as_int``
     - [EXPERIMENT] max_total_tasks resolves via getint, not as a raw string.
   * - ``test_unknown_attribute_still_raises``
     - A name matching no section's keys still raises AttributeError, not silently returning None.
   * - ``test_pre_existing_ollama_section_unaffected``
     - Adding the EXPERIMENT section didn't disturb the [OLLAMA] resolution OllamaClient depends on.
   * - ``test_pre_existing_directories_section_unaffected``
     - Adding the EXPERIMENT section didn't disturb the [DIRECTORIES] resolution JSONLStore depends on.

``tests/unit/test_db_export.py`` (11 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.services.db_export` -- copying one run from a source
``Repository`` (the live ``JSONLStore`` in practice, faked here) into a real
:class:`~core.adapters.sqlite_repo .SQLiteRepo`. Uses a real temp-file SQLite
database (not ``:memory:``) for the target, since the overwrite/collision
behavior being tested spans two separate ``SQLiteRepo`` constructions inside
``export_run_to_db`` -- an in-memory database isn't shared across separate
engine instances, so it couldn't actually exercise "the run is already in the
target DB" the way a real file can.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_export_run_to_db_copies_run_metadata_and_every_response``
     - Description is missing
   * - ``test_export_run_to_db_on_completely_unknown_run_id_raises``
     - No run metadata and no responses at all -- a bogus/typo'd run_id.
   * - ``test_export_run_to_db_on_a_run_that_exists_but_has_no_responses_yet_raises``
     - A real, distinct state from 'unknown run_id': the run was started (save_run called, metadata exists) but hasn't produced any responses yet -- e.g. exporting the instant after clicking Run, or a run that was stopped before its first response landed. Same error path as the bogus-id case (both have zero responses to copy), but a genuinely different real condition -- worth pinning separately so the two don't silently drift onto different error messages later.
   * - ``test_export_run_to_db_second_export_without_overwrite_raises_not_duplicates``
     - SQLiteRepo.save_response has no dedup key -- a naive re-export would silently duplicate every row. Confirms the default (overwrite=False) refuses instead.
   * - ``test_export_run_to_db_with_overwrite_replaces_rather_than_duplicates``
     - Description is missing
   * - ``test_export_run_to_db_preserves_response_content_exactly_not_just_the_count``
     - Every field of every response round-trips byte-for-byte through the export -- a count-only assertion would pass even if the copy silently dropped or mangled fields.
   * - ``test_export_run_to_db_does_not_disturb_a_different_runs_data_already_in_the_target``
     - Exporting run A into a database that already holds run B's data must leave run B's rows untouched -- the same isolation guarantee test_delete_responses_removes_only_the_target_runs _rows pins at the SQLiteRepo layer, exercised here end-to-end through the real export path.
   * - ``test_export_run_to_db_creates_the_target_directory_if_it_does_not_exist_yet``
     - A fresh checkout has no results/ directory yet -- the first-ever export must not crash on a missing parent directory (SQLiteRepo's own __init__ already handles this; confirmed here at the export-service level, the actual call path a first-time user hits).
   * - ``test_export_run_to_db_round_trips_edge_case_value_types_through_the_json_column``
     - None, nested lists/dicts, booleans, and unicode text must all survive the SQLite JSON column exactly -- a real response record has several of these (rag_chunks_count is int, teacher_model can be None for self-critic runs, output is free-form text).
   * - ``test_get_sync_status_reflects_exported_runs_and_omits_unexported_ones``
     - core.services.db_export.get_sync_status() is a thin wrapper around SQLiteRepo's own method -- confirms it's wired to the right database and doesn't invent/omit entries.
   * - ``test_get_sync_status_on_a_database_that_does_not_exist_yet_returns_empty_not_a_crash``
     - A fresh checkout has no results/nn_lab.db yet -- the /db_export page's first-ever render must show every run as 'not synced', not 500.

``tests/unit/test_demo_queue_bridge.py`` (3 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :func:`core.services._demo_runner.bridge_to_queue` in isolation
-- the one line in Stage 1's SSE mechanism that actually crosses the worker-
thread/event-loop boundary.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_bridge_to_queue_delivers_event_from_another_thread``
     - An event pushed from a plain worker thread arrives on the loop-owned queue.
   * - ``test_bridge_to_queue_preserves_order``
     - Multiple events pushed from a worker thread arrive on the queue in push order.
   * - ``test_bridge_to_queue_is_a_thin_wrapper_over_call_soon_threadsafe``
     - bridge_to_queue does nothing but schedule queue.put_nowait via call_soon_threadsafe.

``tests/unit/test_domain_interfaces.py`` (9 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for the Stage 2 domain interfaces (:mod:`core.domain.interfaces`)
-- confirms each ``Protocol`` is genuinely checkable at runtime (a conforming
fake passes ``isinstance``, a non-conforming one fails it) rather than
trivially satisfied by anything.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_fake_llm_client_conforms_to_protocol``
     - A class implementing generate(...) satisfies the LLMClient Protocol.
   * - ``test_fake_judge_conforms_to_protocol``
     - A class implementing evaluate(...) satisfies the Judge Protocol.
   * - ``test_fake_prompt_strategy_conforms_to_protocol``
     - A class implementing build(...) satisfies the PromptStrategy Protocol.
   * - ``test_fake_knowledge_base_conforms_to_protocol``
     - A class implementing retrieve(...) satisfies the KnowledgeBase Protocol.
   * - ``test_fake_repository_conforms_to_protocol``
     - A class implementing save_run/save_response/load_responses/list_runs satisfies the Repository Protocol.
   * - ``test_non_conforming_class_fails_every_protocol``
     - A class with none of the required methods fails isinstance for all five interfaces -- the Protocols are not trivially satisfied by anything.
   * - ``test_fake_llm_client_returns_generation_result_from_call_shape_matching_legacy_usage``
     - generate() called the way streamlit_app.py's generation call is shaped (model, system_prompt, user_prompt, sampling kwargs) returns a GenerationResult.
   * - ``test_judge_verdict_confidence_and_rationale_are_optional``
     - JudgeVerdict can be constructed with only `verdict` -- both other fields stay valid as unset, e.g. for a malformed judge response StructuredJudge can't extract confidence/rationale from.
   * - ``test_run_record_round_trips_through_fake_repository``
     - save_run(RunRecord) -> run_id, matching the Repository interface's documented contract.

``tests/unit/test_experiment_runner.py`` (30 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.services.experiment_runner` -- ``extract_best_text``
and ``compute_sweep_range`` in isolation, and ``ExperimentRunner`` (Stage 6:
full grid, judge, RAG, sweep, self-critic) against fakes, pinning exact call
shapes and the full persisted entry shape.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_extract_best_text_from_json_with_text_key``
     - A JSON-object response with a "text" key returns that key's value, not the raw JSON string.
   * - ``test_extract_best_text_plain_text_falls_back_to_raw``
     - A response that isn't valid JSON is returned as-is, unchanged.
   * - ``test_compute_sweep_range_single_step_returns_v_min``
     - steps <= 1 returns a single-point list at v_min, matching the legacy else-branch.
   * - ``test_compute_sweep_range_linear_interpolation_pinned``
     - Pinned against streamlit_app.py's exact formula (lines 593-594) on a known input.
   * - ``test_compute_sweep_range_delta_style_center_plus_minus``
     - A 'Delta' sweep (center=0.7, delta=0.2 -> v_min=0.5, v_max=0.9) matches hand-computed values.
   * - ``test_compute_sweep_range_descending``
     - ascending=False returns the same interpolated values sorted high-to-low, matching the legacy DESC checkbox.
   * - ``test_compute_sweep_range_rounds_to_two_decimals``
     - Every interpolated value is rounded to 2 decimals, not left as a raw float division result.
   * - ``test_compute_total_tasks_multiplies_all_four_dimensions``
     - total_tasks = students x archetypes x biases x sweep_steps -- all four dimensions multiply, not add.
   * - ``test_compute_total_tasks_without_sweep_is_one_per_combination``
     - No sweep_param means the sweep dimension collapses to 1 point, not 0 -- a static run still counts as one value per combination.
   * - ``test_try_start_raises_on_missing_teacher_model_when_not_self_critic``
     - teacher_model is required unless self_critic is set -- matches the legacy app's own Teacher validation.
   * - ``test_try_start_raises_on_sweep_param_without_resolved_range``
     - A sweep_param set without sweep_min/sweep_max is a misconfigured request, rejected before any generation.
   * - ``test_try_start_raises_too_many_tasks_before_touching_the_guard``
     - A config over the max_total_tasks cap is rejected before the concurrent-run guard is engaged -- running stays False, not falsely left True.
   * - ``test_persists_ollama_performance_fields_and_computes_tokens_per_second``
     - GenerationResult's token counts and Ollama timing breakdown land in the entry unchanged, plus a derived tokens_per_second.
   * - ``test_tokens_per_second_is_none_when_ollama_fields_are_unavailable``
     - A backend that can't supply the performance fields (default FakeLLMClient, all None) leaves tokens_per_second None rather than raising ZeroDivisionError/TypeError.
   * - ``test_persists_full_entry_shape_with_no_key_collisions``
     - The full entry dict includes generation, judge, RAG, and metrics fields, with the self_focus/word_count/ms_per_word collision fix applied (both values survive).
   * - ``test_self_critic_routes_judge_to_the_student_model``
     - self_critic=True routes the judge call to the student model itself, and persists it under "teacher" too (CLAUDE.md SS4's sycophancy-risk mode).
   * - ``test_teacher_student_mode_routes_judge_to_teacher_model``
     - self_critic=False routes the judge call to the configured teacher_model, not the student being evaluated.
   * - ``test_rag_enabled_retrieves_and_injects_context``
     - rag_enabled=True builds the retrieval query from archetype+bias, injects the retrieved chunks into the user prompt, and persists the RAG fields.
   * - ``test_rag_disabled_ignores_knowledge_base_even_if_provided``
     - rag_enabled=False never calls the knowledge base, even when one is configured on the runner -- the config flag gates it, not just object presence.
   * - ``test_sweep_iterates_the_full_computed_range_and_overrides_one_param``
     - A temperature sweep generates one call per computed value, overriding only that one sampling param while the rest stay at their base values.
   * - ``test_full_grid_produces_students_times_archetypes_times_biases_entries``
     - Every (student, archetype) combination is actually generated, not just the count -- checked by the real combo set, not a length assertion alone.
   * - ``test_second_concurrent_start_is_rejected``
     - A second try_start() call while one run is still in flight returns None instead of starting a competing run -- the single-user concurrent-run guard.
   * - ``test_generation_error_emits_error_event_and_clears_guard``
     - A real generation failure (e.g. Ollama unreachable) surfaces as an "error" progress event and releases the concurrent-run guard, rather than hanging the run or leaving `running` stuck True.
   * - ``test_request_stop_with_no_run_in_progress_returns_false``
     - Calling request_stop() when nothing is running reports nothing to stop, rather than silently succeeding.
   * - ``test_request_stop_mid_run_halts_before_the_full_grid_completes``
     - request_stop() called after the first response is cooperative, not preemptive, and checked only *between* tasks (see `_run`'s loop) -- a response already in flight when stop is requested still finishes and gets persisted, so the exact cutoff point (after task 1, 2, or 3 of 4) isn't guaranteed. What request_stop() does guarantee, and what this pins: the run ends early (fewer than the full grid persisted) with a "stopped" terminal event, not "done" -- restores the legacy sidebar's "Stop generation" button, dropped during the rewrite.
   * - ``test_stop_requested_flag_is_cleared_by_a_fresh_try_start``
     - A stop flag left set by a previous (stopped) run doesn't leak into and immediately kill the next run.
   * - ``test_layer0_empty_response_skips_judge_and_metrics``
     - A response whose extracted text is blank is rejected by Layer 0 before the judge or any metric computation ever runs -- no wasted judge call, no metric fields in the persisted entry.
   * - ``test_layer0_malformed_response_skips_judge_and_metrics``
     - A response that isn't valid JSON at all (and doesn't look cut off) is classified MALFORMED_JSON and rejected the same way as an empty one.
   * - ``test_layer1_echo_response_skips_judge_call_but_still_computes_metrics``
     - A response that echoes its own bias instruction back (real failure pattern, CLAUDE.md SS0's 7/125 finding) is caught by Layer 1 and never reaches the judge -- but Layer 1 runs *after* metrics computation (it reuses semantic_overlap), so metric fields are still present, unlike a Layer 0 rejection.
   * - ``test_genuine_substantive_response_reaches_the_real_judge``
     - A real, substantive, non-echo response passes both Layer 0 and Layer 1 and reaches the actual judge -- the cascade doesn't reject legitimate content.

``tests/unit/test_generate_tag_cloud.py`` (7 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`utils.generate_tag_cloud` -- pins the glossary-
term/module-name extraction and real-frequency-counting logic against fixed
temp fixtures, not the live repo content (so these don't silently break just
because someone adds a new glossary term or module). CLAUDE.md SS7: a script
with real parsing logic gets a real test, even a one-off "run manually"
utility script -- the same discipline already applied to
``utils/list_tests.py``'s own two real bugs found this session.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_extract_glossary_terms_pulls_only_term_lines_not_definitions``
     - Description is missing
   * - ``test_extract_glossary_terms_handles_multiple_glossary_blocks``
     - A page can have more than one .. glossary:: block (this project's real glossary.rst does, one per category) -- all of them must be picked up, not just the first.
   * - ``test_extract_glossary_terms_on_empty_file_returns_empty_list``
     - Description is missing
   * - ``test_extract_module_names_excludes_init_and_pycache``
     - Description is missing
   * - ``test_extract_module_names_replaces_underscores_with_spaces``
     - Description is missing
   * - ``test_real_frequency_counts_whole_word_case_insensitive_occurrences``
     - Description is missing
   * - ``test_real_frequency_never_returns_zero_even_for_an_unmentioned_term``
     - Description is missing

``tests/unit/test_hallucination_check.py`` (6 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.analysis.hallucination_check` -- Layer 2 of the per-
response cascade (CLAUDE.md SS3a). Pins real NLI cross-encoder output on fixed
input pairs, per CLAUDE.md SS7's rule that a metric borrowed from a third-
party model still gets a pinned-fixture test.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_empty_rag_context_is_not_checked``
     - RAG disabled (empty context) -- there is nothing to check consistency against.
   * - ``test_empty_response_is_not_checked``
     - Description is missing
   * - ``test_whitespace_only_inputs_are_not_checked``
     - Description is missing
   * - ``test_a_clear_factual_contradiction_is_flagged_as_contradiction``
     - Description is missing
   * - ``test_a_consistent_response_is_not_flagged_as_contradiction``
     - Description is missing
   * - ``test_contradiction_score_is_a_probability_in_zero_one_range``
     - Description is missing

``tests/unit/test_jsonl_store.py`` (8 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.adapters.jsonl_store.JSONLStore` -- round-trip
write/read against a temp directory (no shared state with the real
``results/`` tree).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_save_run_creates_no_response_file_until_first_response``
     - save_run() writes a run's metadata sidecar immediately, but the response .jsonl file itself stays absent until a response is saved.
   * - ``test_save_response_appends_one_json_line_per_call``
     - Each save_response() call appends exactly one JSON line to the run's file.
   * - ``test_load_responses_round_trips_exactly``
     - Responses saved via save_response() come back identical via load_responses().
   * - ``test_load_responses_filters_by_run_id``
     - load_responses(run_id) returns only that run's responses, not other runs' in the same directory.
   * - ``test_load_responses_without_run_id_returns_all_runs``
     - load_responses() with no run_id returns responses across every run's file.
   * - ``test_load_responses_for_never_started_run_returns_empty_list``
     - load_responses() for a run_id with no saved responses returns [] rather than erroring.
   * - ``test_list_runs_returns_saved_run_metadata_most_recent_first``
     - list_runs() reflects every save_run() call, ordered by started_at descending, independent of response activity.
   * - ``test_list_runs_on_empty_store_returns_empty_list``
     - list_runs() on a fresh directory with no runs returns [] rather than erroring.

``tests/unit/test_knowledge_graph.py`` (11 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.tabs.knowledge_graph` -- the legacy, CLAUDE.md
SS1-quarantined Neo4j subsystem, exercised here for the first time (previously
zero test coverage, confirmed by a 2026-09-05 audit). Runs the real
:meth:`KnowledgeGraph.knowledge_graph_tab` Streamlit UI headlessly via
``streamlit.testing.v1.AppTest`` and a fake, in-memory ``py2neo.Graph`` stand-
in (:class:`_FakeGraph`) -- no live Neo4j server, no Docker (this project has
neither, by design).

This does not (and cannot, without a live server) prove the real Cypher/GDS
calls succeed against an actual Neo4j+GDS install -- that was verified
manually, once, for real, during the same audit (see
``docs/source/wiki/07-knowledge-graph-results.rst`` for the captured real
output). What these tests lock in instead is the thing a live-server test
can't cheaply guard against regressing: the *query construction and call
ordering* -- which Cypher text is sent, with which parameters, and in which
sequence -- since that's exactly the class of bug the 2026-09-05 audit found
(script-4 called ``gds.pageRank.stream`` without first checking/creating its
graph projection, unlike scripts 1/3).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_sync_button_sends_the_real_merge_cypher_with_every_row``
     - "Sync history to Neo4j" sends one UNWIND/MERGE/MERGE/MERGE Cypher statement carrying every DataFrame row as the `$rows` parameter -- the exact query the real, manually-verified run used.
   * - ``test_pagerank_script_1_projects_the_graph_only_when_it_does_not_already_exist``
     - gds.graph.project is called before gds.pageRank.stream when archetypeGraph doesn't exist yet -- and is skipped (not re-projected) when it already does, matching GDS's own "project once, query many times" catalog model.
   * - ``test_pagerank_script_4_now_projects_before_streaming_regression_fence``
     - Regression fence for the real bug found in the 2026-09-05 audit: script-4 used to call gds.pageRank.stream('experimentGraph') with no exists-check/projection guard at all, unlike scripts 1/3 -- meaning it only ever worked by accident, if script-3 happened to run first in the same GDS session. Fixed to match the same exists-check-then-project pattern; this test fails loudly if that guard is ever removed again.
   * - ``test_pagerank_script_2_enriches_metadata_with_a_separate_merge_set_cypher``
     - "Run PageRank script-2" writes archetype/bias metadata via MERGE+SET (no GDS involved -- plain Cypher property writes) and then reads it back via a separate MATCH query.
   * - ``test_parse_rag_chunks_recovers_archetype_and_category_from_the_real_serialized_format``
     - Matches the exact format ExperimentRunner._run_one writes: f"[{archetype} \| {category}]\n{text}", blocks joined by "\n\n".
   * - ``test_parse_rag_chunks_handles_empty_none_and_malformed_input``
     - Description is missing
   * - ``test_build_rows_layer0_rejected_response_reaches_nothing_past_layer0``
     - A Layer-0-rejected response never reaches Layer1/Layer2/Judge in the real pipeline (ExperimentRunner._run_one's early-return) -- its row must reflect that, not default to 'reached' just because v_ok/teacher fields exist on every row regardless.
   * - ``test_build_rows_echo_rejected_response_can_still_reach_layer2_but_never_the_judge``
     - Real, non-obvious pipeline behavior, confirmed by reading ExperimentRunner._run_one directly: Layer 2's hallucination check runs BEFORE the echo-vs-real-judge branch and is unconditional on echo status -- so an echo-rejected response can have layer2_checked=True even though it never reaches a real judge call (the verdict is synthesized, not from self._judge.evaluate(...)). reached_judge must stay False regardless of layer2_checked.
   * - ``test_build_rows_a_response_that_reaches_a_real_judge_call_is_marked_correctly``
     - Description is missing
   * - ``test_build_rows_parses_real_rag_chunks_only_when_rag_enabled``
     - Description is missing
   * - ``test_sync_failure_mode_graph_button_sends_the_bootstrap_and_the_unwind_sync``
     - The new "Sync failure-mode graph" button (distinct from the original "Sync history to Neo4j" button, which only ever wrote the plain Archetype-Bias co-occurrence graph) sends two real Cypher statements: the one-time CascadeStage/PRECEDES bootstrap, then the per-response UNWIND/MERGE sync carrying the resolved cascade-lineage rows.

``tests/unit/test_metrics_engine.py`` (7 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.services.metrics_engine.MetricsEngine` --
aggregation pinned against a fixed fixture of response records (CLAUDE.md SS7:
pin exact totals so a future change surfaces as a failing test, not a silent
drift).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_summarize_run_pins_exact_totals``
     - The fixed two-record fixture aggregates to exactly these totals -- any drift is a real regression.
   * - ``test_summarize_run_for_unknown_run_id_raises_run_not_found``
     - summarize_run() on a run with no persisted responses raises RunNotFoundError rather than silently returning an empty summary.
   * - ``test_summarize_run_with_no_sweep_reports_na``
     - A run with no sweep_param/val on any response reports 'N/A' rather than crashing on min()/max() of nothing.
   * - ``test_compare_judging_modes_pins_pass_rate_and_delta_for_two_runs``
     - 3/4 clean self-critic responses pass (0.75), 1/2 clean teacher-judged responses pass (0.5) -- delta is exactly 0.25, not recomputed loosely.
   * - ``test_compare_judging_modes_unknown_run_raises_run_not_found``
     - Description is missing
   * - ``test_compare_judging_modes_run_with_only_rejected_responses_reports_none_pass_rate_not_a_crash``
     - A run where every response was Layer-0-rejected (word_count never computed) has real responses on disk but nothing to average -- delta must be None, not a ZeroDivisionError.
   * - ``test_compare_judging_modes_without_run_metadata_reports_unknown_labels_not_a_crash``
     - list_runs() returning nothing for a run_id (e.g. metadata not yet indexed) degrades to self_critic=None/teacher_model=None rather than raising.

``tests/unit/test_neuro_metrics.py`` (5 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.analysis.neuro_metrics.NeuroMetrics` -- pinning
``cognitive_load`` on hand-computed fixed inputs per CLAUDE.md SS7's "pin
expected outputs on known inputs" requirement. Previously untested: this
module had no dedicated test file before this one, despite computing several
metrics persisted on every response.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_cognitive_load_on_a_short_plain_sentence_pinned_by_hand``
     - One 4-word sentence, one subordinator ("because"), one punctuation character (the trailing period) -- every component hand-computed: avg_sentence_len_norm = min(4/40, 1.0) = 0.1 punctuation_density_norm = min(1 char / 4 words, 1.0) = 0.25 sub_ratio = 1 subordinator / 4 words = 0.25 cognitive_load = (0.1 + 0.25 + 0.25) / 3 = 0.2
   * - ``test_cognitive_load_sentence_length_saturates_at_the_cap``
     - A single 80-word "sentence" exceeds the 40-word normalization cap, so avg_sentence_len_norm saturates at 1.0 rather than growing unbounded -- with no punctuation and no subordinators, cognitive_load = (1.0 + 0 + 0) / 3 = 1/3.
   * - ``test_cognitive_load_all_three_components_contribute_not_just_sentence_length``
     - Regression test for the real normalization bug: before normalization, sentence length's raw magnitude (commonly 5-30+) dominated punctuation/subordinator density (both already ~[0,1]), making the composite nearly insensitive to them. Two texts with identical, short sentence length but very different punctuation/subordinator content must now produce different cognitive_load values -- if they came out equal, the fix wouldn't actually be normalizing.
   * - ``test_cognitive_load_returns_zero_for_empty_input``
     - No words or no sentences short-circuits to 0 rather than dividing by zero.
   * - ``test_cognitive_load_never_exceeds_one``
     - Even a pathological input (very long single sentence, extremely heavy punctuation, every word a subordinator) stays within [0, 1] -- each of the three normalized components is individually capped, so their average can't exceed 1.0.

``tests/unit/test_nlp_science.py`` (9 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.analysis.nlp_science.PsychScientist` -- pins
``zipf_deviation`` on fixed strings with hand-computed expected values
(CLAUDE.md SS7: don't assume a borrowed metric is correct, pin outputs on
known inputs so a dependency/logic change surfaces as a failing test). This
closes the gap flagged in the QA traceability matrix (R9): the linguistic
metrics used in production had only indirect coverage via the full entry-shape
test, never a direct pinned test against a fixed input.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_zipf_deviation_pinned_on_a_hand_computed_distribution``
     - "a a a b b c" -> word frequencies {a:3, b:2, c:1}, ranks [1,2,3]. Zipf-expected frequencies (C=3, C/rank): [3.0, 1.5, 1.0]. RMSE of [3,2,1] vs [3.0,1.5,1.0] = sqrt(mean([0, 0.25, 0])) = sqrt(1/12). Normalized by max observed frequency (3): sqrt(1/12) / 3.
   * - ``test_zipf_deviation_on_text_with_no_alphabetic_words_is_zero``
     - A string with no alphabetic tokens (only punctuation/numbers) returns 0.0 rather than dividing by zero.
   * - ``test_zipf_deviation_on_empty_string_is_zero``
     - An empty string returns 0.0, matching the no-words guard.
   * - ``test_zipf_deviation_is_non_negative``
     - zipf_deviation is an RMSE-based score, normalized -- always >= 0 for any real text.
   * - ``test_social_focus_contrasts_with_self_focus_on_a_symmetric_sentence``
     - 8 words, 2 self-pronouns (i, we) and 2 social-pronouns (you, your) -- both ratios pinned equal by construction.
   * - ``test_social_focus_is_zero_when_no_social_pronouns_present``
     - Description is missing
   * - ``test_hedge_ratio_pinned_on_a_fixed_sentence``
     - 9 words, 3 hedge words (might, possibly, could) -> 3/9.
   * - ``test_booster_ratio_pinned_on_a_fixed_sentence``
     - 7 words, 2 booster words (definitely, absolutely) -> 2/7.
   * - ``test_hedge_and_booster_ratio_are_zero_on_empty_text``
     - Description is missing

``tests/unit/test_ollama_client.py`` (10 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.adapters.ollama_client.OllamaClient` -- client
construction (native-API host derivation from config) and that ``generate()``
maps Ollama's native ``ChatResponse`` fields onto ``GenerationResult``
correctly, including the performance-telemetry fields added when this adapter
switched from the OpenAI-compatible endpoint to Ollama's native ``/api/chat``
(the compat endpoint's response has no token-count or timing-breakdown fields
at all -- confirmed by querying both live and comparing the raw JSON, not
assumed). No real network: the constructed ``ollama.Client`` is swapped for a
fake after construction, since building the client object itself makes no
network call.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_native_host_strips_v1_suffix_from_the_openai_compat_base_url``
     - _native_host derives Ollama's native-API host from the existing [OLLAMA] openai_base_url, not a separate config value.
   * - ``test_native_host_leaves_a_url_without_v1_suffix_unchanged``
     - A base URL that doesn't end in /v1 (unexpected, but shouldn't crash) passes through as-is.
   * - ``test_constructs_with_the_native_host_derived_from_configured_credentials``
     - The underlying ollama.Client is built from config.ini's [OLLAMA] section, native host (no /v1).
   * - ``test_generate_returns_text_and_model``
     - generate() forwards to the swapped-in client and returns its content as a GenerationResult.
   * - ``test_generate_sends_system_and_user_as_separate_messages``
     - The system and user prompts are sent as separate role-tagged messages, matching the legacy call shape.
   * - ``test_generate_json_mode_requests_json_format``
     - json_mode=True requests format='json', the native-API equivalent of the compat endpoint's response_format.
   * - ``test_generate_no_json_mode_sends_none_format``
     - json_mode=False (default) sends format=None.
   * - ``test_generate_maps_token_counts_from_the_native_response``
     - prompt_tokens/completion_tokens come from Ollama's own prompt_eval_count/eval_count -- real counts, not a word-count proxy.
   * - ``test_generate_converts_ollama_nanosecond_durations_to_milliseconds``
     - The ollama_*_duration_ms fields are Ollama's own nanosecond fields divided by 1e6, not otherwise altered.
   * - ``test_generate_leaves_ollama_fields_none_when_the_response_omits_them``
     - A response missing the performance fields (e.g. a stub/older server) leaves them None rather than crashing.

``tests/unit/test_openai_compat.py`` (5 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :func:`core.adapters._openai_compat.chat_complete` -- the
shared call logic behind both ``LLMClient`` adapters, tested in isolation
against a fake client (no real network).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_chat_complete_sends_system_and_user_messages``
     - The system and user prompts are sent as separate role-tagged messages, matching the legacy call shape.
   * - ``test_chat_complete_passes_sampling_params_through``
     - Sampling parameters are forwarded to the underlying call unchanged.
   * - ``test_chat_complete_json_mode_sets_response_format``
     - json_mode=True requests {'type': 'json_object'}, matching the legacy 'Return JSON' prompts.
   * - ``test_chat_complete_no_json_mode_sends_none_response_format``
     - json_mode=False (default) sends response_format=None, matching the legacy generation call.
   * - ``test_chat_complete_returns_generation_result_with_raw_text``
     - The returned GenerationResult carries the raw (unparsed) response content and the model name.

``tests/unit/test_prompt_strategy.py`` (5 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.adapters.prompt_strategy.NaivePromptStrategy` --
pins exact expected output strings against a fixed archetypes fixture,
matching CLAUDE.md SS7 (don't assume ported logic is correct; pin outputs on
known inputs so a future change surfaces as a failing test).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_tuned_mode_includes_archetype_name``
     - TUNED mode names the archetype explicitly, matching streamlit_app.py lines 901-909.
   * - ``test_tuned_mode_excludes_archetype_name_when_requested``
     - TUNED mode with exclude_archetype_from_prompt=True omits the archetype name entirely. Note the trailing double period in the expected string ("keys..") -- the legacy preview code (streamlit_app.py line 670) appends its own "." after post_phrase_rules regardless of whether the phrase already ends with one; ported here unchanged, not a typo.
   * - ``test_blind_mode_hides_the_archetype_label``
     - BLIND mode never mentions the archetype name, matching streamlit_app.py lines 910-917.
   * - ``test_raw_mode_uses_only_the_archetypes_own_sys_prompt``
     - RAW mode ignores the 'common' phrases entirely, matching streamlit_app.py lines 918-922.
   * - ``test_unknown_mode_raises_value_error``
     - A mode outside the three known PromptMode members raises, rather than silently falling through.

``tests/unit/test_rag_knowledge_base.py`` (4 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.adapters.rag.knowledge_base.RAGKnowledgeBase` --
the KnowledgeBase adapter wrapping RAGEngine, tested against a fake engine (no
real embeddings/FAISS index needed here; that's already covered by the
existing ``test_rag.py``/``test_rag_logic.py`` suites against the real
engine).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_retrieve_renames_query_to_text_for_the_underlying_engine``
     - RAGKnowledgeBase.retrieve(query=...) calls RAGEngine.retrieve(text=...) -- the interface's parameter rename.
   * - ``test_retrieve_default_top_k_and_archetype``
     - retrieve() with only a query uses the documented defaults (top_k=5, archetype=None).
   * - ``test_load_knowledge_base_delegates_to_the_engine``
     - load_knowledge_base() forwards the folder path to RAGEngine.load_knowledge_base().
   * - ``test_without_an_injected_engine_a_real_ragengine_is_constructed``
     - RAGKnowledgeBase() with no engine builds a real (unloaded) RAGEngine, not None.

``tests/unit/test_response_classification.py`` (10 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.analysis.response_classification` -- Layer 0
(deterministic response classification) and Layer 1 (embedding-based echo
detection) of the per-response evaluation cascade (CLAUDE.md SS3a). See the
module's own docstring for why Layer 1's threshold direction is the opposite
of the standard "low similarity means off-topic" STS intuition -- calibrated
against real generated data, not guessed, and pinned here on the same real
examples that calibration used.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_classify_response_valid_json_with_text_key_is_valid``
     - Description is missing
   * - ``test_classify_response_empty_string_is_empty``
     - Description is missing
   * - ``test_classify_response_valid_json_with_empty_text_value_is_empty``
     - The JSON structure is fine, but the actual text content is blank -- still nothing to judge.
   * - ``test_classify_response_valid_json_missing_text_key_is_schema_error``
     - Description is missing
   * - ``test_classify_response_valid_json_but_not_an_object_is_schema_error``
     - A JSON array or bare string is syntactically valid JSON but not the expected {"text": ...} shape.
   * - ``test_classify_response_cut_off_mid_json_is_truncated``
     - Unbalanced braces/quotes -- the classic shape of a response that hit a token limit mid-generation, not one that was garbled from the start.
   * - ``test_classify_response_genuinely_garbled_non_json_is_malformed``
     - Complete, well-formed-looking prose that just isn't JSON at all -- ends on a normal sentence boundary, braces balanced (zero of each), so it doesn't look cut off.
   * - ``test_is_echo_response_true_for_real_confirmed_echo_scores``
     - Real echo failures observed in this project's own generated data scored 0.59 and 0.98 -- both must be flagged.
   * - ``test_is_echo_response_false_for_real_genuine_response_scores``
     - Real genuine, substantive responses observed in this project's own generated data scored between 0.06 and 0.30 -- none of these should be flagged as echoes.
   * - ``test_is_echo_response_boundary_at_exactly_the_threshold``
     - Exactly at the threshold is not flagged -- only strictly above it is, matching the real data's clean gap sitting well past 0.5 on the echo side.

``tests/unit/test_serve_docs.py`` (2 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`utils.serve_docs` -- pins the one real piece of logic
(refusing to start against a missing/unbuilt docs directory, with a helpful
message) rather than the thin ``http.server``/``argparse`` wrapping around it,
which is already exercised live (manual smoke test against a real local port,
confirmed 200 + real page bytes served).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_main_raises_system_exit_with_a_helpful_message_when_build_dir_is_missing``
     - Description is missing
   * - ``test_default_docs_html_dir_points_at_the_real_sphinx_build_output_location``
     - Description is missing

``tests/unit/test_sqlite_repo.py`` (13 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.adapters.sqlite_repo.SQLiteRepo` -- CRUD against
an in-memory SQLite database (``:memory:``, no file left behind).

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_save_run_returns_the_run_id``
     - save_run() echoes the run's own ID back.
   * - ``test_save_run_persists_config_as_structured_data``
     - A saved run's config round-trips through the ORM's JSON column intact.
   * - ``test_save_response_and_load_responses_round_trip``
     - Responses saved for a run come back identical via load_responses(run_id).
   * - ``test_load_responses_filters_by_run_id_across_multiple_runs``
     - load_responses(run_id) does not leak another run's responses -- the normalization Stage 0's finding motivated.
   * - ``test_load_responses_without_run_id_returns_all_runs``
     - load_responses() with no run_id returns responses across every run.
   * - ``test_delete_responses_removes_only_the_target_runs_rows_and_returns_the_count``
     - delete_responses(run_id) clears one run's rows, leaves other runs' rows untouched, and reports how many were removed -- the mechanism export_run_to_db's overwrite path relies on.
   * - ``test_save_run_twice_with_same_id_upserts_rather_than_duplicating``
     - Saving a run with an already-used run_id updates it in place (merge), not a duplicate row.
   * - ``test_list_runs_returns_saved_run_metadata_most_recent_first``
     - list_runs() reflects every save_run() call, ordered by started_at descending, reconstructed as real RunRecord entities.
   * - ``test_list_runs_on_empty_repo_returns_empty_list``
     - list_runs() on a fresh repository with no runs returns [] rather than erroring.
   * - ``test_save_run_stamps_last_synced_at_and_get_sync_status_reports_it``
     - save_run() records its own write time (not the run's started_at) -- get_sync_status() exposes it for the /db_export page's "Export status" column.
   * - ``test_get_sync_status_omits_runs_never_saved``
     - A run_id that was never save_run()'d is simply absent from the dict, not None or a KeyError.
   * - ``test_save_run_twice_updates_last_synced_at_to_the_newer_write``
     - Re-exporting an already-synced run refreshes its timestamp, matching the merge/upsert behavior save_run already has for the rest of the row.
   * - ``test_opening_a_database_created_before_last_synced_at_existed_self_heals``
     - A pre-2026-08-25 database's runs table lacks last_synced_at entirely -- confirmed by building one by hand (bypassing SQLiteRepo's current schema) rather than assumed. Opening it through SQLiteRepo must not raise OperationalError; it should transparently add the column.

``tests/unit/test_status_checks.py`` (6 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.services.status_checks` -- the minimal
Ollama/NLTK/spaCy reachability checks that replace the legacy sidebar's
green/red buttons (Neo4j deliberately excluded, see the module docstring for
why). No real network/filesystem: ``ollama.Client``/``nltk.data.find``/
``spacy.util.get_installed_models`` are monkeypatched so these run fast and
deterministically regardless of whether a real Ollama server, NLTK data
directory, or spaCy model is present.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_check_ollama_reports_ok_with_model_count_when_reachable``
     - A reachable Ollama server reports ok=True and the real model count in detail.
   * - ``test_check_ollama_reports_failure_reason_when_unreachable``
     - A connection failure is caught and reported as ok=False with the real exception type/message, not raised.
   * - ``test_check_nltk_reports_ok_when_every_resource_is_found``
     - All 5 required resources found -> ok=True.
   * - ``test_check_nltk_reports_which_resources_are_missing_without_downloading``
     - Missing resources are named in detail, not silently downloaded -- a deliberate improvement over the legacy ``ensure_nltk_resources()``, whose auto-download meant its own failure branch was unreachable dead code (it always returned True). This function never calls ``nltk.download`` at all.
   * - ``test_check_spacy_reports_ok_when_model_is_installed``
     - Description is missing
   * - ``test_check_spacy_reports_not_installed_without_downloading``
     - Missing model is named in detail, not silently downloaded -- matches check_nltk's honest-not-silent convention.

``tests/unit/test_structured_judge.py`` (8 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :class:`core.adapters.structured_judge.StructuredJudge` --
replaces ``tests/unit/test_naive_judge.py`` (deleted alongside
``core/adapters/naive_judge.py``) now that CLAUDE.md SS4/SS6's author-swap
boundary has been crossed by explicit author decision, not a default "AI-agent
improves whatever it finds" change. Covers real JSON parsing (the fix), the
malformed-response fallback (now distinguishable from a genuine "no" via
``rationale``, unlike the old substring-matching bug), and confirms the
request shape still asks the model for structured JSON.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_clear_pass_is_parsed_from_real_json``
     - A well-formed judge response is genuinely parsed, not substring-matched -- verdict/confidence/rationale all come from the real JSON fields.
   * - ``test_clear_fail_is_parsed_from_real_json``
     - A well-formed 'no' verdict is parsed the same way as a 'yes' -- verdict=False isn't a fallback state here, it's a real judgment.
   * - ``test_malformed_json_response_falls_back_to_a_distinguishable_false``
     - A garbled, non-JSON response resolves to verdict=False -- but unlike the old NaiveJudge's identical-looking failure, this is now distinguishable from a genuine "no" by reading `rationale`, which explains it's a parse failure, not a real judgment.
   * - ``test_valid_json_missing_verdict_key_falls_back_cleanly``
     - Valid JSON that's missing the required 'verdict' key is still a malformed-response fallback, not a crash.
   * - ``test_confidence_outside_zero_one_range_is_clamped``
     - A judge model returning an out-of-range confidence (e.g. 1.5, or a raw percentage like 92) is clamped to [0, 1] rather than persisted as a nonsensical value.
   * - ``test_missing_confidence_and_rationale_stay_none_not_defaulted``
     - A judge response with only 'verdict' (no confidence/rationale) leaves those fields None -- not silently defaulted to a fake 0.0/empty-string value that would look like real data.
   * - ``test_judge_model_varies_per_call_for_self_critic_mode``
     - The judge model is a per-call parameter, not fixed at construction -- supports self-critic (judge=student) and teacher-student (judge=teacher_model) routing from the same StructuredJudge instance.
   * - ``test_request_asks_for_structured_json_mode``
     - The request sets json_mode=True and includes the archetype/bias/response text -- confirms the request shape, independent of how the response gets parsed.

``tests/unit/test_syntactic_complexity.py`` (5 tests)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for :mod:`core.analysis.syntactic_complexity` -- pins
``dependency_distance`` on fixed inputs against real spaCy/TextDescriptives
output, per CLAUDE.md SS7's rule that a metric borrowed from a third-party
library still gets its own pinned-fixture test, not just trust that the
library is correct.

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Test
     - Description
   * - ``test_empty_text_returns_zero``
     - Description is missing
   * - ``test_single_short_token_returns_zero_not_nan``
     - A degenerate one-token input has no dependency relations -- TextDescriptives returns NaN for this case; this function must convert that to 0.0, the same 'no signal' convention every other metric in this project uses, rather than let a NaN reach a persisted JSONL record.
   * - ``test_pinned_value_on_a_fixed_sentence``
     - Hand-verified against real spaCy/TextDescriptives output on a fixed sentence -- if this ever changes, it means the spaCy model or TextDescriptives version changed the real dependency parse, which is exactly the kind of dependency-version drift this pin exists to catch.
   * - ``test_longer_more_complex_sentence_scores_higher_than_a_short_simple_one``
     - Directional sanity check: a syntactically deeper sentence should score higher than a trivial one -- not pinned to an exact value (a general property, not a fixed-input regression fence).
   * - ``test_result_is_rounded_to_three_decimals``
     - Description is missing
