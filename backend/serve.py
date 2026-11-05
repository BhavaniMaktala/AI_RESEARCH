"""Production entrypoint.

    pip install waitress
    python serve.py

Uses the Waitress WSGI server (pure Python, works on Windows) instead of the
Flask development server, which removes the "development server" warning and
handles concurrent requests properly. Falls back to Flask if waitress is not
installed, so the command always works.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import create_app  # noqa: E402
from api.banner import print_banner  # noqa: E402
from config import config  # noqa: E402

app = create_app(config)


def main() -> None:
    threads = int(os.getenv("THREADS", "8"))
    try:
        from waitress import serve
    except ImportError:
        print_banner(app, config, server="flask (dev)")
        print("  waitress is not installed - install it for a production server:")
        print("      pip install waitress\n")
        app.run(host=config.HOST, port=config.PORT, threaded=True, use_reloader=False)
        return

    print_banner(app, config, server=f"waitress x{threads}")
    serve(app, host=config.HOST, port=config.PORT, threads=threads)


if __name__ == "__main__":
    main()
