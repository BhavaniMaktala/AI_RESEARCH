"""Search endpoints: REST + Server-Sent Events for the live agent trace."""
from __future__ import annotations

import json
import queue
import threading

from flask import Blueprint, Response, jsonify, request, stream_with_context

from api.deps import container, error, parse_int, session_id

bp = Blueprint("search", __name__, url_prefix="/api")


def _read_query() -> tuple[str, dict, int | None]:
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or request.args.get("q") or "").strip()
    filters = body.get("filters") or {}
    if request.args.get("year_from"):
        filters["year_from"] = parse_int(request.args.get("year_from"))
    if request.args.get("year_to"):
        filters["year_to"] = parse_int(request.args.get("year_to"))
    top_k = parse_int(body.get("top_k") or request.args.get("top_k"), None)
    return query, filters, top_k


@bp.post("/search")
def search():
    query, filters, top_k = _read_query()
    if not query:
        return error("A query is required")
    if len(query) > 600:
        return error("Query is too long (max 600 characters)")
    payload = container().search.search(query, session_id(), filters, top_k)
    return jsonify(payload)


@bp.get("/search/stream")
def stream_search():
    """Same pipeline, but every agent emits an event as it finishes."""
    query, filters, top_k = _read_query()
    if not query:
        return error("A query is required")
    sid = session_id()
    service = container().search

    def generate():
        events: "queue.Queue[dict | None]" = queue.Queue()

        def emitter(event: dict) -> None:
            events.put(event)

        def work() -> None:
            try:
                service.search(query, sid, filters, top_k, emitter=emitter)
            except Exception as exc:  # noqa: BLE001
                events.put({"event": "error", "message": str(exc)})
                events.put({"event": "done", "total_ms": 0})

        threading.Thread(target=work, daemon=True, name="agent-pipeline").start()

        while True:
            try:
                item = events.get(timeout=90)
            except queue.Empty:
                yield 'data: {"event": "error", "message": "Pipeline timed out"}\n\n'
                break
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"
            if item.get("event") in {"done", "error"}:
                break

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers=headers)


@bp.get("/suggest")
def suggest():
    prefix = (request.args.get("q") or "").strip()
    return jsonify({"suggestions": container().search.suggestions(prefix)})


@bp.get("/for-you")
def for_you():
    limit = parse_int(request.args.get("limit"), 6) or 6
    return jsonify(container().search.for_you(session_id(), limit=min(limit, 20)))


@bp.get("/history")
def history():
    return jsonify(container().search.history(session_id()))


@bp.delete("/history")
def clear_history():
    container().repo.clear_history(session_id())
    return jsonify({"ok": True})


@bp.get("/trending")
def trending():
    return jsonify({"papers": container().search.trending(limit=parse_int(request.args.get("limit"), 6))})
