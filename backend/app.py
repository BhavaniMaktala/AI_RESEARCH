"""PaperRec - entrypoint.

    cd backend
    python app.py            # serves the API and the frontend on :7000
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import create_app  # noqa: E402
from api.banner import print_banner  # noqa: E402
from config import config  # noqa: E402

app = create_app(config)

if __name__ == "__main__":
    print_banner(app, config, server="flask (dev)")
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True, use_reloader=False)
