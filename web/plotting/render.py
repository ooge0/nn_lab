"""
web.plotting.render
======================

Shared helper turning a Plotly figure into an embeddable HTML fragment.
"""

import itertools

import plotly.graph_objects as go

_counter = itertools.count()

# Matches web/static/style.css's :root tokens exactly (--surface/--text/--border,
# plus the :root[data-theme="light"] override) -- Plotly's own built-in
# "plotly_dark"/default templates use different hues, so every chart would
# otherwise fight the surrounding VS Code Dark+/Light+ chrome instead of sitting
# in it. Deliberately theming only background/font/gridlines here, not
# trace/marker colors or colorscales -- the qualitative data-color palette
# (clusters, pass/fail) is a separate, not-yet-implemented decision, see
# docs/source/features.rst.
_PALETTES = {
    "dark": {"bg": "#252526", "text": "#d4d4d4", "grid": "#3c3c3c"},
    "light": {"bg": "#f3f3f3", "text": "#1e1e1e", "grid": "#d4d4d4"},
}
_CHART_FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'

# Charts are rendered server-side (baked-in colors), but the light/dark theme
# toggle (web/static/ui.js) is a purely client-side preference with no page
# reload -- there's no per-request "theme" value otherwise available where
# chart-building code runs, several call layers below the route handler. A
# module-level default, set once near the top of each chart-serving route from
# the "nn_lab_theme" cookie ui.js also writes, is deliberately not thread-safe
# against concurrent requests -- acceptable per CLAUDE.md's own "strictly
# single-user, one session at a time" constraint (the same assumption
# ExperimentRunner's single-run guard already relies on), not a general
# solution for a multi-user deployment.
_current_theme = "dark"


def set_chart_theme(theme: str) -> None:
    """Set the palette used by every subsequent `figure_to_div` call in this process, until changed again."""
    global _current_theme
    _current_theme = theme if theme in _PALETTES else "dark"


def figure_to_div(fig: go.Figure) -> str:
    """
    Render a Plotly figure as a ``<div>``+``<script>`` fragment, themed to
    match the app's current light/dark chrome (see `set_chart_theme`).

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
        The figure to render. Mutated in place (``update_layout``) before
        rendering -- callers don't need to theme their own figures.

    Returns
    -------
    str
        HTML safe to embed directly in a template -- ``include_plotlyjs`` is
        always ``False`` since ``plotly.min.js`` is loaded once per page from
        ``/static/vendor/plotly/plotly.min.js`` (vendored locally, matching
        the htmx precedent -- no CDN dependency), not re-bundled per chart.
    """
    palette = _PALETTES[_current_theme]
    fig.update_layout(
        paper_bgcolor=palette["bg"],
        plot_bgcolor=palette["bg"],
        font=dict(color=palette["text"], family=_CHART_FONT),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=50),
    )
    # update_xaxes/update_yaxes (not update_layout(xaxis=...)) so this reaches every
    # axis on a figure with subplots/facets (e.g. the scatter matrices), not just x1/y1.
    fig.update_xaxes(gridcolor=palette["grid"], zerolinecolor=palette["grid"], linecolor=palette["grid"])
    fig.update_yaxes(gridcolor=palette["grid"], zerolinecolor=palette["grid"], linecolor=palette["grid"])
    return fig.to_html(include_plotlyjs=False, full_html=False, div_id=f"chart-{next(_counter)}")
