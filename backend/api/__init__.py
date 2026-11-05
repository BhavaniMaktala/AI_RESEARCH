"""Flask application factory."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

from api.container import ServiceContainer
from api.routes import register_routes

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app(cfg=None) -> Flask:
    from config import config as default_config

    cfg = cfg or default_config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    # FAISS logs an INFO-level ModuleNotFoundError while probing for an AVX2
    # build; it is harmless (the standard build loads next) but looks alarming.
    logging.getLogger("faiss.loader").setLevel(logging.ERROR)

    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    app.config.update(
        SECRET_KEY=cfg.SECRET_KEY,
        MAX_CONTENT_LENGTH=cfg.MAX_CONTENT_LENGTH,
        JSON_SORT_KEYS=False,
        PROPAGATE_EXCEPTIONS=False,
    )
    app.json.sort_keys = False
    CORS(app, resources={r"/api/*": {"origins": cfg.CORS_ORIGINS}}, expose_headers=["X-Session-Id"])

    container = ServiceContainer(cfg)
    app.extensions["container"] = container
    register_routes(app)

    # -- frontend ---------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/favicon.ico")
    def favicon():
        path = FRONTEND_DIR / "assets" / "favicon.svg"
        if path.exists():
            return send_from_directory(FRONTEND_DIR / "assets", "favicon.svg",
                                       mimetype="image/svg+xml")
        return ("", 204)

    # -- errors -----------------------------------------------------------
    @app.errorhandler(404)
    def not_found(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found", "path": request.path}), 404
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.errorhandler(413)
    def too_large(err):
        return jsonify({"error": "Request body too large"}), 413

    @app.errorhandler(500)
    def server_error(err):
        app.logger.exception("Unhandled error")
        return jsonify({"error": "Internal server error"}), 500

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if getattr(g, "new_session", False) and getattr(g, "session_id", None):
            response.set_cookie("paperrec_session", g.session_id, max_age=60 * 60 * 24 * 180,
                                samesite="Lax", httponly=False)
        return response

    return app
