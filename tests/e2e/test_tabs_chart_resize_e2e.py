"""
Playwright E2E test for the tabbed-page Plotly-width bug: a chart rendered inside a hidden
(``display: none``) ``.tab-panel`` gets measured by Plotly at zero/collapsed width the moment its
``Plotly.newPlot()`` call runs (before ``tabs.js`` has applied ``.active`` to make the panel
visible), and never recovers until something fires a real browser ``resize`` event -- reported by
the author from a real screenshot: charts rendered narrower than their container, fixed only by
nudging the browser's zoom level. Server-rendered ``TestClient`` assertions cannot see this (the
HTML string is identical either way; only real browser layout geometry shows the collapsed width),
so this needs a real browser, same as the ``/db_export`` OOB-swap bug in
:mod:`tests.e2e.test_db_export_e2e`.

Uses a real run already on disk (created by the author, not this suite) if one exists with a
useful response count; skipped otherwise rather than fabricating one, since NLP charts need a real
multi-response run to render meaningfully. See ``tests/e2e/conftest.py`` for ``live_server``/``page``.
"""

import pytest

from core.adapters.jsonl_store import JSONLStore


def _find_a_real_run_with_responses(min_responses: int = 5):
    store = JSONLStore()
    for run in store.list_runs():
        responses = store.load_responses(run.run_id)
        if len(responses) >= min_responses:
            return run.run_id
    return None


@pytest.fixture
def real_run_id():
    run_id = _find_a_real_run_with_responses()
    if run_id is None:
        pytest.skip("No real run with enough responses on disk to render NLP charts meaningfully.")
    return run_id


def test_charts_in_the_default_and_a_switched_tab_both_render_at_full_container_width(live_server, page, real_run_id):
    """Regression test for the reported bug: fixed by tabs.js explicitly calling
    Plotly.Plots.resize() on a panel's charts the moment that panel becomes .active, both on
    initial load (the default tab) and on every later click (a previously-hidden tab)."""
    page.goto(f"{live_server}/nlp")
    page.locator("select[name='run_id']").select_option(real_run_id)
    page.wait_for_selector(".plotly-graph-div")

    default_panel = page.locator("#nlp-1")
    default_chart = default_panel.locator(".plotly-graph-div").first
    default_ratio = default_chart.bounding_box()["width"] / default_panel.bounding_box()["width"]
    assert default_ratio > 0.85, f"default tab's chart is narrower than its panel: ratio={default_ratio:.2f}"

    page.get_by_role("button", name="NLP-2", exact=False).click()
    page.wait_for_function("document.getElementById('nlp-2').classList.contains('active')")

    switched_panel = page.locator("#nlp-2")
    switched_chart = switched_panel.locator(".plotly-graph-div").first
    switched_ratio = switched_chart.bounding_box()["width"] / switched_panel.bounding_box()["width"]
    assert switched_ratio > 0.85, f"switched tab's chart is narrower than its panel: ratio={switched_ratio:.2f}"
