"""Request helpers shared by the route modules."""
from __future__ import annotations

import uuid

from flask import current_app, g, jsonify, request


def container():
    return current_app.extensions["container"]


def session_id() -> str:
    """Anonymous session, supplied by the browser via X-Session-Id.

    Falls back to a cookie so plain curl / REST clients keep one identity
    across requests.
    """
    existing = getattr(g, "session_id", None)
    if existing:
        return existing

    sid = request.headers.get("X-Session-Id")
    if not sid:
        body = request.get_json(silent=True) or {}
        sid = body.get("session_id") or request.args.get("session_id")
    if not sid:
        sid = request.cookies.get("paperrec_session")
    if not sid:
        sid = uuid.uuid4().hex
        g.new_session = True
    sid = str(sid)[:64]
    g.session_id = sid
    return sid


def error(message: str, status: int = 400):
    return jsonify({"error": message, "status": status}), status


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
