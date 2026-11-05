"""Reading lists (library) endpoints."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from api.deps import container, error, session_id
from services.citation import MEDIA_TYPES

bp = Blueprint("library", __name__, url_prefix="/api/library")


@bp.get("")
def get_library():
    items = container().repo.get_library(session_id())
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(item.get("list_name") or "Reading list", []).append(item)
    return jsonify({"items": items, "groups": grouped, "count": len(items)})


@bp.post("")
def add_to_library():
    body = request.get_json(silent=True) or {}
    paper_id = (body.get("paper_id") or "").strip()
    if not paper_id:
        return error("paper_id is required")
    c = container()
    if not (c.index.get(paper_id) or c.repo.get_paper(paper_id)):
        return error("Unknown paper_id", 404)
    list_name = (body.get("list_name") or "Reading list").strip()[:80]
    sid = session_id()
    c.repo.add_to_library(sid, paper_id, list_name)
    c.repo.record_feedback(sid, paper_id, "save", body.get("query"))
    c.search.apply_feedback(sid, paper_id, "save")
    return jsonify({"ok": True, "paper_id": paper_id, "list_name": list_name})


@bp.delete("/<path:paper_id>")
def remove_from_library(paper_id: str):
    container().repo.remove_from_library(session_id(), paper_id)
    return jsonify({"ok": True, "paper_id": paper_id})


@bp.get("/export")
def export_library():
    fmt = (request.args.get("format") or "bibtex").lower()
    text, ext = container().search.export(session_id(), None, fmt)
    return Response(text, mimetype=MEDIA_TYPES.get(fmt, "text/plain"),
                    headers={"Content-Disposition": f'attachment; filename="paperrec-library.{ext}"'})
