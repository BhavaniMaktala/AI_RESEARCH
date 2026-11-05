"""Paper detail, related work, subgraph and deep (LLM) summary endpoints."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from api.deps import container, error, parse_int, session_id
from services.citation import EXTENSIONS, MEDIA_TYPES

bp = Blueprint("papers", __name__, url_prefix="/api/papers")


@bp.get("/<path:paper_id>")
def detail(paper_id: str):
    deep = request.args.get("deep", "0") in {"1", "true", "yes"}
    query = (request.args.get("q") or "").strip()
    payload = container().search.paper_detail(paper_id, session_id(), query=query, deep=deep)
    if not payload:
        return error("Paper not found", 404)
    return jsonify(payload)


@bp.get("/<path:paper_id>/graph")
def graph(paper_id: str):
    index = container().index
    if not index.get(paper_id):
        return error("Paper not found", 404)
    depth = parse_int(request.args.get("depth"), 1) or 1
    limit = parse_int(request.args.get("limit"), 40) or 40
    payload = index.graph.neighbors(paper_id, depth=min(depth, 2), limit=limit)
    analytics = index.analytics()
    for node in payload["nodes"]:
        node["influence"] = round(float(analytics["influence"].get(node["id"], 0.0)), 4)
        node["community"] = int(analytics["community"].get(node["id"], -1))
    return jsonify(payload)


@bp.get("/<path:paper_id>/related")
def related(paper_id: str):
    index = container().index
    if not index.get(paper_id):
        return error("Paper not found", 404)
    limit = parse_int(request.args.get("limit"), 8) or 8
    analytics = index.analytics()
    out = []
    for rid, sim in index.similar_to(paper_id, k=limit):
        paper = index.get(rid) or {}
        out.append({
            "paper_id": rid, "title": paper.get("title", rid), "year": paper.get("year"),
            "authors": (paper.get("authors") or [])[:3], "similarity": round(sim, 4),
            "influence": round(float(analytics["influence"].get(rid, 0.0)), 4),
            "community": int(analytics["community"].get(rid, -1)),
        })
    return jsonify({"related": out})


@bp.post("/<path:paper_id>/summary")
def deep_summary(paper_id: str):
    """Generate an LLM summary on demand (falls back to extractive)."""
    payload = container().search.paper_detail(paper_id, session_id(), deep=True)
    if not payload:
        return error("Paper not found", 404)
    return jsonify({"paper_id": paper_id, "summary": payload["summary"],
                    "method": payload["summary_method"],
                    "contributions": payload["contributions"]})


@bp.get("/<path:paper_id>/export")
def export_paper(paper_id: str):
    fmt = (request.args.get("format") or "bibtex").lower()
    c = container()
    paper = c.index.get(paper_id) or c.repo.get_paper(paper_id)
    if not paper:
        return error("Paper not found", 404)
    text, ext = c.search.export(session_id(), [paper_id], fmt)
    return Response(text, mimetype=MEDIA_TYPES.get(fmt, "text/plain"),
                    headers={"Content-Disposition": f'attachment; filename="paperrec-{paper_id.replace(":", "-")}.{ext}"'})


@bp.get("/<path:paper_id>/cite")
def cite(paper_id: str):
    """Plain-text citation in the requested style (for the copy button)."""
    from services import citation

    style = (request.args.get("style") or "apa").lower()
    c = container()
    paper = c.index.get(paper_id) or c.repo.get_paper(paper_id)
    if not paper:
        return error("Paper not found", 404)
    text = {"apa": citation.to_apa, "ieee": citation.to_ieee,
            "bibtex": citation.to_bibtex, "ris": citation.to_ris}.get(style, citation.to_apa)(paper)
    return jsonify({"paper_id": paper_id, "style": style, "citation": text})


@bp.get("/<path:paper_id>/note")
def get_note(paper_id: str):
    notes = container().repo.get_notes(session_id())
    return jsonify({"paper_id": paper_id, "note": notes.get(paper_id)})


@bp.put("/<path:paper_id>/note")
def put_note(paper_id: str):
    body = (request.get_json(silent=True) or {}).get("body", "")
    c = container()
    if not (c.index.get(paper_id) or c.repo.get_paper(paper_id)):
        return error("Paper not found", 404)
    if not str(body).strip():
        c.repo.delete_note(session_id(), paper_id)
        return jsonify({"ok": True, "deleted": True})
    c.repo.save_note(session_id(), paper_id, str(body))
    return jsonify({"ok": True, "paper_id": paper_id, "length": len(str(body))})


@bp.delete("/<path:paper_id>/note")
def delete_note(paper_id: str):
    container().repo.delete_note(session_id(), paper_id)
    return jsonify({"ok": True})
