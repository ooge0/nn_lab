"""
api.routers.faq
==================

Stage 14 -- ``tab_faq`` parity: serves ``faq_eng.md``/``faq_ua.md`` (the
same two files the legacy tab reads) as rendered HTML via
:class:`markdown_it.MarkdownIt` instead of Streamlit's built-in
``st.markdown``. Trivial, static content -- no persisted-run data involved.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt

from api._paths import REPO_ROOT, TEMPLATES_DIR

router = APIRouter(prefix="/faq", tags=["faq"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_FAQ_FILES = {"English": REPO_ROOT / "faq_eng.md", "Українська": REPO_ROOT / "faq_ua.md"}
_md = MarkdownIt()


@router.get("", response_class=HTMLResponse)
def faq_page(request: Request, lang: str = "English") -> HTMLResponse:
    """
    Render the FAQ page for one language.

    Parameters
    ----------
    lang : str, optional
        ``"English"`` (default) or ``"Українська"`` -- matches the legacy
        tab's own ``st.segmented_control`` options exactly.

    Returns
    -------
    HTMLResponse
        200, with the selected file rendered to HTML, if it exists.
        200, with an inline "file not found" message (matching the legacy
        tab's own ``st.error`` fallback, not a 404 -- the *page* exists and
        renders fine, only the requested language's file is missing) if it
        does not, or if ``lang`` isn't a known option (falls back to the
        "not found" message rather than a 400 -- an unrecognised value in
        this deliberately small, fixed set is equivalent to a missing
        file).
    """
    path = _FAQ_FILES.get(lang)
    content_html = None
    error = None
    if path is not None and path.exists():
        content_html = _md.render(path.read_text(encoding="utf-8"))
    else:
        error = f"File not found for language: {lang}"

    return templates.TemplateResponse(
        request, "faq.html", {"lang": lang, "languages": list(_FAQ_FILES), "content_html": content_html, "error": error}
    )
