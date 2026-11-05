"""Application service layer: runs the agent pipeline and shapes API payloads."""
from __future__ import annotations

import logging
import time
import uuid

import numpy as np

from agents.base import new_state
from agents.orchestrator import build_orchestrator
from services.nlp import expand_query, extract_contributions, extractive_summary

log = logging.getLogger(__name__)

PAPER_FIELDS = ("paper_id", "title", "abstract", "authors", "year", "venue", "url",
                "pdf_url", "categories", "citation_count", "source")


def _public_paper(paper: dict) -> dict:
    return {k: paper.get(k) for k in PAPER_FIELDS}


class SearchService:
    def __init__(self, container):
        self.c = container

    # ------------------------------------------------------------------ search
    def search(self, query: str, session_id: str, filters: dict | None = None,
               top_k: int | None = None, emitter=None) -> dict:
        config = self.c.config
        started = time.perf_counter()
        state = new_state(query, session_id, filters or {}, int(top_k or config.TOP_K))
        state["request_id"] = uuid.uuid4().hex[:12]

        session = self.c.repo.get_session(session_id)
        ctx = {
            "index": self.c.index,
            "sources": self.c.sources,
            "analyzer": self.c.analyzer,
            "config": config,
            "repo": self.c.repo,
            "llm": self.c.llm,
            "session": session,
        }

        orchestrator = build_orchestrator(emitter=emitter)
        state = orchestrator.run(state, ctx)
        total_ms = round((time.perf_counter() - started) * 1000, 1)

        payload = self._build_payload(state, total_ms)
        if emitter:
            emitter({"event": "result", "data": payload})
            emitter({"event": "done", "total_ms": total_ms})
        return payload

    def _build_payload(self, state: dict, total_ms: float) -> dict:
        candidates = {p["paper_id"]: p for p in state.get("candidates", [])}
        results = []
        for item in state.get("ranked", []):
            pid = item["paper_id"]
            paper = candidates.get(pid, {})
            results.append({
                **item,
                "paper": _public_paper(paper),
                "summary": state.get("summaries", {}).get(pid, {}),
                "explanation": state.get("explanations", {}).get(pid, {}),
            })

        understanding = state.get("understanding", {})
        graph = state.get("graph", {})
        return {
            "request_id": state.get("request_id"),
            "query": state.get("query"),
            "session_id": state.get("session_id"),
            "understanding": {
                "intent": understanding.get("intent", {}),
                "keywords": understanding.get("keywords", []),
                "expansions": understanding.get("expansions", {}),
                "filters": understanding.get("filters", {}),
            },
            "results": results,
            "trace": state.get("trace", []),
            "timings": state.get("timings", {}),
            "total_ms": total_ms,
            "weights": state.get("weights", {}),
            "graph": {"stats": graph.get("stats", {}),
                      "communities": graph.get("communities", 0),
                      "community_labels": graph.get("community_labels", {})},
            "sources": state.get("source_report", {}),
            "learning": state.get("learning", {}),
            "meta": {
                "candidates": state.get("pool_size", 0),
                "returned": len(results),
                "embedding": self.c.index.embedder.kind,
                "vector_backend": self.c.index.vector_store.backend,
                "graph_backend": self.c.index.graph.kind,
                "online": bool(state.get("source_report", {}).get("live")),
                "errors": state.get("errors", []),
            },
        }

    # ------------------------------------------------------------ paper detail
    def paper_detail(self, paper_id: str, session_id: str, query: str = "",
                     deep: bool = False) -> dict | None:
        index = self.c.index
        paper = index.get(paper_id) or self.c.repo.get_paper(paper_id)
        if not paper:
            return None

        analyzer = self.c.analyzer
        focus = expand_query(query, analyzer)["keywords"] if query else []
        abstract = paper.get("abstract") or ""
        summary = extractive_summary(abstract, focus, max_sentences=4, analyzer=analyzer)

        method = "extractive-query-focused" if query else "extractive"
        if deep and self.c.llm.enabled and abstract:
            generated = self.c.llm.generate(
                prompt=(f"Summarise this research paper for a researcher in 3 short bullet points.\n"
                        f"Title: {paper.get('title')}\nAbstract: {abstract[:2500]}"),
                system="You are a precise scientific summariser. No filler, no repetition.",
                max_tokens=320,
            )
            if generated:
                summary, method = generated, f"llm:{self.c.llm.model}"

        analytics = index.analytics()
        community = int(analytics["community"].get(paper_id, -1))
        related = []
        for rid, sim in index.similar_to(paper_id, k=8):
            rel = index.get(rid)
            if rel:
                related.append({**_public_paper(rel), "similarity": round(sim, 4),
                                "community": int(analytics["community"].get(rid, -1))})

        graph_payload = index.graph.neighbors(paper_id, depth=1, limit=40)
        citation_titles = self.c.sources.references_for(paper_id, limit=15)

        explanation = []
        if query:
            from services.nlp import clamp, tokenize
            query_vector = index.embed(query)
            vec = index.vector_of(paper_id)
            if vec is not None:
                sim = clamp(float(query_vector @ vec))
                matched = sorted({t for t in tokenize(f"{paper.get('title')} {abstract}")}
                                 & set(tokenize(query)))
                explanation.append({"label": "Query match", "value": round(sim, 3),
                                    "text": f"Semantic similarity {sim:.2f} with your query"})
                if matched:
                    explanation.append({"label": "Shared terms", "value": len(matched),
                                        "text": "Shares: " + ", ".join(matched[:6])})

        return {
            "paper": _public_paper(paper),
            "summary": summary,
            "summary_method": method,
            "contributions": extract_contributions(abstract, limit=3),
            "keywords": analyzer.keywords(f"{paper.get('title')} {abstract}", k=8),
            "metrics": {
                "influence": round(float(analytics["influence"].get(paper_id, 0.0)), 4),
                "bridge": round(float(analytics["bridge"].get(paper_id, 0.0)), 4),
                "community": community,
                "community_label": analytics["community_labels"].get(community, ""),
                "citation_count": int(paper.get("citation_count") or 0),
                "degree": len(graph_payload.get("edges", [])),
            },
            "related": related,
            "graph": graph_payload,
            "citation_titles": citation_titles,
            "explanation": explanation,
        }

    # --------------------------------------------------------------- feedback
    def apply_feedback(self, session_id: str, paper_id: str, action: str) -> dict:
        """Immediate profile update on explicit feedback (like/save/dismiss)."""
        import numpy as np

        index = self.c.index
        session = self.c.repo.get_session(session_id)
        profile = session.get("profile")
        weights = dict(session.get("weights") or {})
        vector = index.vector_of(paper_id)
        delta = 0.0

        if vector is not None:
            if action in {"like", "save"}:
                base = profile if profile is not None and len(profile) == len(vector) else np.zeros_like(vector)
                updated = 0.88 * np.asarray(base, dtype="float32") + 0.12 * vector
                norm = float(np.linalg.norm(updated)) or 1.0
                profile, delta = (updated / norm).astype("float32"), 0.012
            elif action == "dismiss" and profile is not None and len(profile) == len(vector):
                updated = np.asarray(profile, dtype="float32") - 0.06 * vector
                norm = float(np.linalg.norm(updated)) or 1.0
                profile, delta = (updated / norm).astype("float32"), -0.006

        if delta:
            base_weights = weights or dict(self.c.config.WEIGHTS)
            personal = max(0.02, min(0.40, float(base_weights.get("personal", 0.1)) + delta))
            weights = {**base_weights, "personal": round(personal, 4)}
            total = sum(weights.values()) or 1.0
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        self.c.repo.save_session(session_id, profile, weights)
        return {"action": action, "personal_weight": weights.get("personal", 0.1),
                "profile_updated": bool(delta)}

    # ------------------------------------------------------------------ graph
    def graph_overview(self, limit: int = 120, community: int | None = None) -> dict:
        index = self.c.index
        analytics = index.analytics()
        influence = analytics["influence"]
        community_map = analytics["community"]

        ids = sorted(index.papers.keys(), key=lambda p: -influence.get(p, 0.0))
        if community is not None:
            ids = [p for p in ids if int(community_map.get(p, -1)) == int(community)]
        ids = ids[:limit]

        payload = index.graph.subgraph(ids)
        for node in payload["nodes"]:
            pid = node["id"]
            paper = index.papers.get(pid, {})
            node.update({
                "influence": round(float(influence.get(pid, 0.0)), 4),
                "community": int(community_map.get(pid, -1)),
                "community_label": analytics["community_labels"].get(int(community_map.get(pid, -1)), ""),
                "bridge": round(float(analytics["bridge"].get(pid, 0.0)), 4),
                "authors": (paper.get("authors") or [])[:3],
                "url": paper.get("url", ""),
            })
        return {
            "nodes": payload["nodes"],
            "edges": payload["edges"],
            "communities": analytics["communities"],
            "labels": analytics["community_labels"],
            "stats": index.graph.stats(),
        }


    # ------------------------------------------------------------- discovery
    def for_you(self, session_id: str, limit: int = 6) -> dict:
        """Personalised feed: interest-profile similarity blended with influence."""
        index = self.c.index
        analytics = index.analytics()
        session = self.c.repo.get_session(session_id)
        profile = session.get("profile")
        weights = session.get("weights") or {}

        scored = []
        for pid, paper in index.papers.items():
            vector = index.vector_of(pid)
            personal = 0.0
            if profile is not None and vector is not None and len(profile) == len(vector):
                personal = float(np.clip(np.dot(profile, vector), 0.0, 1.0))
            influence = float(analytics["influence"].get(pid, 0.0))
            year = paper.get("year") or 0
            recency = max(0.0, 1.0 - max(0, 2026 - year) / 12.0) if year else 0.3
            score = 0.60 * personal + 0.25 * influence + 0.15 * recency
            if paper.get("citation_count"):
                score += min(0.08, paper["citation_count"] / 20000)
            scored.append({
                "paper": _public_paper(paper),
                "score": round(score, 4),
                "personal": round(personal, 4),
                "influence": round(influence, 4),
                "community_label": analytics["community_labels"].get(
                    int(analytics["community"].get(pid, -1)), ""),
            })

        scored.sort(key=lambda item: -item["score"])
        return {
            "papers": scored[:limit],
            "personalised": profile is not None,
            "personal_weight": weights.get("personal", self.c.config.WEIGHTS["personal"]),
        }

    def history(self, session_id: str, limit: int = 8) -> dict:
        return {
            "queries": self.c.repo.recent_queries(session_id, limit),
            "notes": len(self.c.repo.get_notes(session_id)),
        }

    # ---------------------------------------------------------------- export
    def export(self, session_id: str, paper_ids: list[str] | None, fmt: str = "bibtex") -> tuple[str, str]:
        from services import citation

        if paper_ids:
            papers = [p for p in (self.c.index.get(pid) or self.c.repo.get_paper(pid) for pid in paper_ids) if p]
        else:
            papers = [item for item in self.c.repo.get_library(session_id)]
            papers = [{**p, "abstract": (self.c.index.get(p["paper_id"]) or {}).get("abstract", "")}
                      for p in papers]
        return citation.export(papers, fmt), citation.EXTENSIONS.get(fmt, "bib")

    # -------------------------------------------------------------- discovery
    def suggestions(self, prefix: str, limit: int = 8) -> list[dict]:
        index = self.c.index
        prefix = (prefix or "").strip()
        if len(prefix) < 2:
            return []
        hits = index.lexical_search(prefix, k=limit * 2) or index.vector_search(index.embed(prefix), k=limit * 2)
        out, seen = [], set()
        for pid, _ in hits:
            paper = index.get(pid)
            if not paper:
                continue
            title = paper.get("title", "")
            key = title.lower()[:40]
            if key in seen:
                continue
            seen.add(key)
            out.append({"paper_id": pid, "title": title, "year": paper.get("year")})
            if len(out) >= limit:
                break
        return out

    def trending(self, limit: int = 6) -> list[dict]:
        index = self.c.index
        analytics = index.analytics()
        ranked = sorted(index.papers.values(),
                        key=lambda p: -(analytics["influence"].get(p["paper_id"], 0.0)
                                        + (p.get("citation_count") or 0) / 10000.0))
        return [{**_public_paper(p),
                 "influence": round(float(analytics["influence"].get(p["paper_id"], 0.0)), 4),
                 "community_label": analytics["community_labels"].get(
                     int(analytics["community"].get(p["paper_id"], -1)), "")}
                for p in ranked[:limit]]
