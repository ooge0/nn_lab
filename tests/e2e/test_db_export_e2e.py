"""
Playwright E2E test for ``/db_export``'s "Export status" column -- specifically the
htmx out-of-band (``hx-swap-oob``) update after a successful export.

Why this needs a real browser and not ``TestClient``: the original bug (found by the author from a
real screenshot, not hypothetical) was a bare ``<td hx-swap-oob="true">`` in the AJAX response --
valid as a string of HTML, but a ``<td>`` at the top level of a fragment (outside any
``<table>``/``<tr>`` context) gets mangled by the *browser's own* HTML table-parsing rules, so the
out-of-band swap silently failed to replace the existing cell content -- the old "Not synced" badge
and the new timestamp ended up stacked instead of one replacing the other, until a full page reload
re-parsed everything correctly. ``TestClient``-based integration tests (``test_db_export_api.py``)
only ever assert against the raw HTTP response text and structurally cannot catch this class of bug
-- they were green even with the broken ``<td>`` version, since the OOB element's id/attributes
were present in the string either way. Only a real browser DOM, inspected after real parsing,
proves the swap actually replaced the cell rather than appending to it.
"""

import time

import pytest

from core.adapters.jsonl_store import JSONLStore
from core.adapters.sqlite_repo import SQLiteRepo
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord

_RUN_ID = "run-e2e-db-export-fixture"


@pytest.fixture
def real_run_with_one_response():
    """
    Writes one small, real run into the live server's actual JSONLStore directory (the same
    process, so the background server thread sees it too) and cleans up both the JSONL files and
    the SQLite row afterward -- this test needs a real run reachable over real HTTP, which a fake
    repository (as the integration tests use) can't provide for an actual browser session.
    """
    store = JSONLStore()
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["formal"],
        prompt_mode=PromptMode.TUNED,
    )
    store.save_run(RunRecord(run_id=_RUN_ID, started_at="2026-08-25T00:00:00Z", config=config, total_tasks=1))
    store.save_response(_RUN_ID, {"student": "qwen:latest", "v_ok_numeric": 1, "output": "e2e fixture response"})

    yield _RUN_ID

    meta_path = store._results_dir / f"{_RUN_ID}.meta.json"
    jsonl_path = store._results_dir / f"lab_export_{_RUN_ID}.jsonl"
    meta_path.unlink(missing_ok=True)
    jsonl_path.unlink(missing_ok=True)
    target = SQLiteRepo()
    target.delete_responses(_RUN_ID)
    # Also clear the runs-table row itself, not just its responses -- get_sync_status() reports a
    # run as "synced" purely from its presence in `runs`, so leaving that row behind would make
    # this fixture's run start pre-synced on the *next* test run, defeating the "starts as Not
    # synced" precondition this test relies on.
    target.delete_run(_RUN_ID)


def test_export_status_cell_shows_only_the_new_timestamp_not_stacked_with_not_synced(
    live_server, page, real_run_with_one_response
):
    """
    Regression test for the exact bug reported: after clicking "Send to DB", the "Export status"
    cell must show only the fresh timestamp -- not "Not synced" and the timestamp both visible at
    once, which is what a mis-parsed out-of-band <td> swap produces.
    """
    run_id = real_run_with_one_response
    page.goto(f"{live_server}/db_export")

    row = page.locator("tr", has=page.locator(f"code:text-is('{run_id}')"))
    sync_cell = row.locator("td").last
    assert "Not synced" in sync_cell.inner_text()

    row.get_by_role("button", name="Send to DB").click()
    # Wait for the real timestamp to appear (real htmx round-trip against the live server).
    page.wait_for_function(
        "el => el.innerText.includes('UTC')",
        arg=sync_cell.element_handle(),
        timeout=5000,
    )

    cell_text = sync_cell.inner_text()
    assert "UTC" in cell_text, f"expected a real timestamp, got: {cell_text!r}"
    assert "Not synced" not in cell_text, f"stale 'Not synced' still present alongside the new timestamp: {cell_text!r}"
    # Date and time render on two separate lines (CSS white-space: pre-line honoring the embedded
    # newline _format_synced_at inserts), not run together on one line -- Playwright's inner_text()
    # reflects real rendered line breaks, not just the raw HTML string.
    lines = cell_text.strip().splitlines()
    assert len(lines) == 2, f"expected a 2-line timestamp (date, then time+zone), got: {lines!r}"
    assert lines[1].endswith("UTC")


def test_reexport_updates_the_sync_status_cell_to_the_new_timestamp_not_the_old_one(
    live_server, page, real_run_with_one_response
):
    """
    Regression test for the author's follow-up report: re-exporting an already-exported run (the
    "Re-export (overwrite)" button, a *different* element than the original "Send to DB" button,
    with its own hx-post/hx-target) must update the "Export status" cell to the new timestamp, not
    leave the old one in place or stack both.
    """
    run_id = real_run_with_one_response
    page.goto(f"{live_server}/db_export")

    row = page.locator("tr", has=page.locator(f"code:text-is('{run_id}')"))
    sync_cell = row.locator("td").last

    # First export -- establishes an initial real timestamp.
    row.get_by_role("button", name="Send to DB").click()
    page.wait_for_function("el => el.innerText.includes('UTC')", arg=sync_cell.element_handle(), timeout=5000)
    first_timestamp = sync_cell.inner_text()
    assert "UTC" in first_timestamp

    # Second export without overwrite -- expected to be refused; the cell must still show the
    # first timestamp (nothing changed in the database yet).
    row.get_by_role("button", name="Send to DB").click()
    row.get_by_role("button", name="Re-export (overwrite)").wait_for(timeout=5000)
    assert sync_cell.inner_text() == first_timestamp

    # A real clock tick so a second, genuinely later timestamp is possible to distinguish from the first.
    time.sleep(1.1)

    # Re-export (overwrite=true) -- must actually replace the cell with a new, later timestamp.
    row.get_by_role("button", name="Re-export (overwrite)").click()
    page.wait_for_function(
        "([el, prev]) => el.innerText.includes('UTC') && el.innerText !== prev",
        arg=[sync_cell.element_handle(), first_timestamp],
        timeout=5000,
    )

    second_timestamp = sync_cell.inner_text()
    assert "UTC" in second_timestamp
    assert second_timestamp != first_timestamp, "re-export did not update the sync timestamp at all"
    assert (
        first_timestamp not in second_timestamp
    ), f"old and new timestamps both present, stacked: {second_timestamp!r}"
