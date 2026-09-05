"""
web.plotting.mpl_render
==========================

Renders a matplotlib figure as an embeddable ``<img>`` tag. Stage 10 is the
first stage needing this -- every earlier stage's charts were pure Plotly.
``hdbscan``'s minimum-spanning-tree and condensed-tree plots are
matplotlib-only (no Plotly equivalent), so this is a genuinely new
rendering path, not a Plotly-vs-matplotlib inconsistency.
"""

import base64
import io

import matplotlib

matplotlib.use("Agg")  # non-interactive backend -- this runs inside a web server, not a desktop app
import matplotlib.pyplot as plt

# Matches web/static/style.css's :root tokens exactly (--surface/--text/--border,
# plus the :root[data-theme="light"] override) -- matplotlib's own default
# figure/axes styling is black-on-white, which would render as a bright white
# (or, once dark-forced, a jarring dark) box mismatched against whichever
# chrome theme is actually active.
_PALETTES = {
    "dark": {"bg": "#252526", "text": "#d4d4d4", "grid": "#3c3c3c"},
    "light": {"bg": "#f3f3f3", "text": "#1e1e1e", "grid": "#d4d4d4"},
}

# See web.plotting.render's identical module-level default for why this is a
# plain global, not thread-local/contextvar state: CLAUDE.md's own "strictly
# single-user, one session at a time" constraint, set once per request from
# the "nn_lab_theme" cookie ui.js writes.
_current_theme = "dark"


def set_chart_theme(theme: str) -> None:
    """Set the palette used by every subsequent `figure_to_img_tag` call in this process, until changed again."""
    global _current_theme
    _current_theme = theme if theme in _PALETTES else "dark"


def _theme_figure(fig: "plt.Figure") -> None:
    """Apply the current palette to every Axes on a figure, generically (works regardless of how the caller built the figure)."""
    palette = _PALETTES[_current_theme]
    fig.set_facecolor(palette["bg"])
    for ax in fig.get_axes():
        ax.set_facecolor(palette["bg"])
        ax.tick_params(colors=palette["text"], labelcolor=palette["text"])
        ax.xaxis.label.set_color(palette["text"])
        ax.yaxis.label.set_color(palette["text"])
        ax.title.set_color(palette["text"])
        for spine in ax.spines.values():
            spine.set_color(palette["grid"])
        legend = ax.get_legend()
        if legend is not None:
            legend.get_frame().set_facecolor(palette["bg"])
            legend.get_frame().set_edgecolor(palette["grid"])
            for text in legend.get_texts():
                text.set_color(palette["text"])
    # matplotlib has no public accessor for the suptitle's Text object (only get_suptitle(), which
    # returns the string) -- `_suptitle` is the standard, if private, way to recolor it and is used
    # this way across the matplotlib ecosystem itself.
    if fig._suptitle is not None:  # type: ignore[attr-defined]
        fig._suptitle.set_color(palette["text"])  # type: ignore[attr-defined]


def figure_to_img_tag(fig: "plt.Figure", *, alt: str = "") -> str:
    """
    Render a matplotlib figure as a base64-embedded PNG ``<img>`` tag,
    themed to match the app's current light/dark chrome (see
    `set_chart_theme`).

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to render. Mutated in place (colors only) before
        rendering -- callers don't need to theme their own figures.
    alt : str, optional
        Alt text for the image tag.

    Returns
    -------
    str
        An ``<img src="data:image/png;base64,...">`` tag, safe to embed
        directly in a template. The figure is closed after rendering (via
        ``plt.close``) so repeated calls don't leak memory across requests.
    """
    _theme_figure(fig)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return f'<img alt="{alt}" src="data:image/png;base64,{encoded}">'
