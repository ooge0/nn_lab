#!/usr/bin/env python3
"""
serve_docs.py

One-off wrapper (matches ``utils/list_tests.py``/``utils/generate_tag_cloud.py``'s convention --
run manually, not a Sphinx build-time step) around the standard library's ``http.server`` for
``docs/source/_build/html``.

Why this exists: Sphinx's built-in client-side search (``searchtools.js``) does a real ``fetch()``
per result to build the context snippet shown under each hit. Opened directly as a ``file://`` URL,
that fetch is blocked by the browser's own CORS policy -- search still finds pages (it matches
against a pre-built local index), but every result renders with no snippet, just a bare title. This
is a browser security restriction on the ``file://`` scheme, not a Sphinx configuration problem or
bug in this project's build -- serving over real HTTP (even loopback-only, no network exposure
beyond localhost) is what Sphinx's own docs recommend, and the fix here.
"""

import argparse
import functools
import http.server
import pathlib
import socketserver
import webbrowser

_DOCS_HTML_DIR = pathlib.Path(__file__).resolve().parent.parent / "docs" / "source" / "_build" / "html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab.")
    args = parser.parse_args()

    if not (_DOCS_HTML_DIR / "index.html").exists():
        raise SystemExit(
            f"{_DOCS_HTML_DIR / 'index.html'} not found -- build the docs first: " "cd docs/source && make html"
        )

    # functools.partial binds the served directory per-instance, avoiding a global os.chdir()
    # (SimpleHTTPRequestHandler's own recommended pattern for serving a directory other than cwd).
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(_DOCS_HTML_DIR))
    url = f"http://127.0.0.1:{args.port}/"
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving {_DOCS_HTML_DIR} at {url} (search snippets now work; Ctrl+C to stop)")
        if not args.no_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
