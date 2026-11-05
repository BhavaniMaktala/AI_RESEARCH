"""Feedback endpoint - drives the continuous-learning loop."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from api.deps import container, error, session_id

bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")

VALID_ACTIONS = {"like", "dismiss", "save", "open", "click"}


@bp.post("")
def submit_feedback():
    body = request.get_json(silent=True) or {}
    paper_id = (body.get("paper_id") or "").strip()
    action = (body.get("action") or "").strip().lower()
    if not paper_id:
        return error("paper_id is required")
    if action not in VALID_ACTIONS:
        return error(f"action must be one of {sorted(VALID_ACTIONS)}")

    c = container()
    sid = session_id()
    c.repo.record_feedback(sid, paper_id, action, body.get("query"))
    learning = c.search.apply_feedback(sid, paper_id, action)
    return jsonify({"ok": True, "action": action, "paper_id": paper_id, "learning": learning})
