"""Agent 2 - Paper Retrieval.

Hybrid candidate generation: BM25 + dense vector search over the local index,
plus live Semantic Scholar / arXiv lookups when the network allows.
"""
from __future__ import annotations

from agents.base import AgentResult, BaseAgent
from services.nlp import normalize_title


class RetrievalAgent(BaseAgent):
    key = "retrieval"
    label = "Paper Retrieval"
    description = "Hybrid BM25 + dense retrieval across local index, Semantic Scholar and arXiv"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        index = ctx["index"]
        sources = ctx["sources"]
        config = ctx["config"]
        understanding = state["understanding"]

        query_text = understanding.get("expanded_text") or state["query"]
        filters = state.get("filters") or {}

        # --- local hybrid retrieval -------------------------------------
        pool: dict[str, dict] = {}
        query_vector = index.embed(query_text)
        for pid, score in index.lexical_search(query_text, k=config.CANDIDATE_LIMIT):
            pool.setdefault(pid, {})["lexical"] = score
        for pid, score in index.vector_search(query_vector, k=config.CANDIDATE_LIMIT):
            pool.setdefault(pid, {})["dense"] = score
        ctx["log"](self.key, f"Local hybrid search hit {len(pool)} indexed papers")

        candidates: list[dict] = []
        for pid, scores in pool.items():
            paper = index.get(pid)
            if not paper:
                continue
            candidates.append({**paper, "_lexical": scores.get("lexical", 0.0),
                               "_dense": scores.get("dense", 0.0), "_live": False})

        # --- live retrieval ---------------------------------------------
        live_papers, report = sources.gather(
            state["query"], understanding.get("keywords", []), limit=config.LIVE_RESULT_LIMIT
        )
        known_titles = {normalize_title(c["title"]) for c in candidates}
        live_added = 0
        for paper in live_papers:
            title_key = normalize_title(paper["title"])
            if title_key in known_titles:
                continue
            known_titles.add(title_key)
            candidates.append({**paper, "_lexical": 0.0, "_dense": 0.0, "_live": True})
            live_added += 1

        if report.live:
            ctx["log"](self.key, f"Live APIs returned {live_added} new papers "
                                 f"({', '.join(report.used)})")
        else:
            ctx["log"](self.key, "Offline mode - using the bundled arXiv corpus")

        # --- filters ------------------------------------------------------
        before = len(candidates)
        candidates = self._apply_filters(candidates, filters, understanding)
        if before != len(candidates):
            ctx["log"](self.key, f"Filters removed {before - len(candidates)} papers")

        candidates.sort(key=lambda p: max(p.get("_dense", 0.0), p.get("_lexical", 0.0)), reverse=True)
        candidates = candidates[: config.CANDIDATE_LIMIT]

        note = (f"{len(candidates)} candidates · {len(pool)} indexed · "
                f"{live_added} live · {'online' if report.live else 'offline'}")
        return AgentResult(
            update={"candidates": candidates, "pool_size": len(candidates),
                    "source_report": report.as_dict()},
            note=note,
            metrics={"candidates": len(candidates), "live_added": live_added,
                     "sources": report.used},
        )

    @staticmethod
    def _apply_filters(candidates: list[dict], filters: dict, understanding: dict) -> list[dict]:
        year_from = filters.get("year_from") or understanding["filters"].get("year_from")
        year_to = filters.get("year_to") or understanding["filters"].get("year_to")
        categories = [c.lower() for c in (filters.get("categories") or [])]
        min_citations = filters.get("min_citations") or 0

        out = []
        for paper in candidates:
            year = paper.get("year")
            if year_from and (not year or year < int(year_from)):
                continue
            if year_to and (not year or year > int(year_to)):
                continue
            if min_citations and int(paper.get("citation_count") or 0) < int(min_citations):
                continue
            if categories:
                cats = " ".join(paper.get("categories") or []).lower()
                if not any(c in cats for c in categories):
                    continue
            out.append(paper)
        return out
