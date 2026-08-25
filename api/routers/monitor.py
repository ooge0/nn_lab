"""
api.routers.monitor
======================

Stage 13 -- scoped port of ``tab_debug``'s "Schema check" block
(``streamlit_app.py:3411-3415``), the one piece of the legacy
``tab_monitor``/``tab_debug`` pair that's actually a low-risk,
Repository-data introspection view. Deliberately narrower than those two
legacy tabs -- confirmed with the author before building anything:

- ``tab_monitor`` itself (``streamlit_app.py:3189-3387``) turned out to be
  Ollama model *management* (subprocess ``ollama pull``, ``ollama.delete``)
  -- a different risk profile (subprocess execution, destructive delete)
  than the rest of this read-only analysis app, and out of scope here.
- ``tab_debug``'s other half (``st.json(st.session_state.to_dict())``) is a
  raw dump of Streamlit's own session-state object -- a Streamlit-specific
  concept with no equivalent in this stateless FastAPI app (every request
  here is backed by :class:`~core.domain.interfaces.Repository`, not an
  in-memory session).

The legacy Arrow-compatibility coercion around the schema-check dataframe
(``fillna``/``astype(object)`` per column, to appease Streamlit's Arrow-based
table renderer) is also not ported -- it's a Streamlit rendering-engine
workaround, not a `Repository`-data concern, and plain ``DataFrame.to_html()``
has no such requirement.
"""

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore

router = APIRouter(prefix="/monitor", tags=["monitor"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()

_PREVIEW_ROWS = 20


def _build_context(run_id: str, full: bool = False) -> dict:
    """
    Load one run's responses and build the schema/preview tables, or an
    empty-state context if the run has none.

    Parameters
    ----------
    full : bool, optional
        If ``True``, ``preview_table`` includes every row, not just the
        first ``_PREVIEW_ROWS`` -- the actual "view the raw JSONL as a
        table" replacement for the legacy Streamlit app's own
        ``st.dataframe(df_display, ...)`` full-table view, one click away
        rather than a separate page.
    """
    responses = _repository.load_responses(run_id)
    if not responses:
        return {"selected_run_id": run_id, "has_data": False}

    df = pd.json_normalize(responses)
    dtypes_df = df.dtypes.reset_index()
    dtypes_df.columns = ["column", "dtype"]
    dtypes_df["dtype"] = dtypes_df["dtype"].astype(str)

    preview_df = df if full else df.head(_PREVIEW_ROWS)

    return {
        "selected_run_id": run_id,
        "has_data": True,
        "row_count": len(df),
        "column_count": len(df.columns),
        "dtypes_table": dtypes_df.to_html(index=False),
        "preview_table": preview_df.to_html(index=False),
        "full": full,
        "preview_rows": _PREVIEW_ROWS,
    }


@router.get("", response_class=HTMLResponse)
def monitor_page(request: Request) -> HTMLResponse:
    """Render the run picker plus the most recently started run's schema check, if any runs exist."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    context = {"runs": runs, "selected_run_id": None, "has_data": False}
    if selected_run_id:
        context.update(_build_context(selected_run_id))
        context["runs"] = runs
    return templates.TemplateResponse(request, "monitor.html", context)


@router.get("/schema", response_class=HTMLResponse)
def monitor_schema(request: Request, run_id: str, full: bool = False) -> HTMLResponse:
    """
    Return the ``#monitor-schema`` fragment for one run -- used by the
    picker's htmx swap, and by the "Show all N rows" / "Show first 20"
    toggle within that fragment (``full`` re-fetches the same fragment
    with every row instead of just a preview).

    Returns
    -------
    HTMLResponse
        200, with the rendered dtype/preview tables, if the run has
        persisted responses.
    HTMLResponse
        404, if the run has no persisted responses.
    """
    context = _build_context(run_id, full=full)
    status_code = 200 if context["has_data"] else 404
    return templates.TemplateResponse(request, "_monitor_schema.html", context, status_code=status_code)
