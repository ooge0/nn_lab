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
    "dark": {"bg": "#16171c", "text": "#e6e6e9", "grid": "#262832"},
    "light": {"bg": "#f6f7f9", "text": "#1b1d23", "grid": "#dfe1e6"},
}
_CHART_FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'

# Qualitative trace/marker palette -- previously every chart fell through to
# Plotly's own default colorway (bright blue/red/green), which fought the
# muted VS Code-adjacent chrome instead of sitting in it. Same hue families as
# style.css's --pass/--fail/--warning/--link tokens, plus two new muted hues
# (teal, violet) so a chart needing more than 4 series doesn't run out. The
# --fail-family hue is placed last on purpose -- Plotly assigns colors to
# traces in the order they're added, so a 2-3-series chart won't accidentally
# read a mid-series color as "this one = error".
QUALITATIVE_PALETTE = [
    "#6f9bd8",  # --link family
    "#d9a94f",  # --warning family
    "#4fb8bf",  # new: muted teal
    "#b98fd1",  # new: muted violet
    "#6bbf7b",  # --pass family
    "#d9727a",  # --fail family -- last, deliberately
]

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
        colorway=QUALITATIVE_PALETTE,
    )
    # update_xaxes/update_yaxes (not update_layout(xaxis=...)) so this reaches every
    # axis on a figure with subplots/facets (e.g. the scatter matrices), not just x1/y1.
    fig.update_xaxes(gridcolor=palette["grid"], zerolinecolor=palette["grid"], linecolor=palette["grid"])
    fig.update_yaxes(gridcolor=palette["grid"], zerolinecolor=palette["grid"], linecolor=palette["grid"])
    return fig.to_html(include_plotlyjs=False, full_html=False, div_id=f"chart-{next(_counter)}")
