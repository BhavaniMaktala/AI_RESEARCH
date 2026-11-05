"""Agent 5 - Recommendation Ranking.

Fuses five signals (semantic relevance, graph influence, citation impact,
recency, personal fit) into a single score, then applies Maximal Marginal
Relevance so the final list is diverse rather than twelve near-duplicates.
"""
from __future__ import annotations

import math
import re

import numpy as np

from agents.base import AgentResult, BaseAgent
from services.nlp import clamp, recency_score

_SURVEY_RE = re.compile(r"\b(survey|review|overview|taxonomy|state of the art)\b", re.IGNORECASE)


class RankingAgent(BaseAgent):
    key = "ranking"
    label = "Recommendation Ranking"
    description = "Hybrid scoring of 5 signals + MMR diversification"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        config = ctx["config"]
        index = ctx["index"]
        session = ctx.get("session") or {}
        vectors = ctx.get("vectors", {})
        graph = state.get("graph", {}).get("per_paper", {})
        understanding = state.get("understanding", {})
        intent = understanding.get("intent", {})
        top_k = int(state.get("top_k") or config.TOP_K)

        # personalisation weights learned by the Learning agent override defaults
        weights = dict(config.WEIGHTS)
        for key, value in (session.get("weights") or {}).items():
            if key in weights and isinstance(value, (int, float)):
                weights[key] = float(value)
        weights["recency"] *= float(intent.get("recency_bias", 1.0))
        total = sum(weights.values()) or 1.0
        weights = {k: round(v / total, 4) for k, v in weights.items()}

        candidates = {p["paper_id"]: p for p in state.get("candidates", [])}
        max_citations = max((int(p.get("citation_count") or 0) for p in candidates.values()), default=0)
        profile = session.get("profile")

        ranked: list[dict] = []
        for entry in state.get("scored", []):
            pid = entry["paper_id"]
            paper = candidates.get(pid)
            if not paper:
                continue
            graph_info = graph.get(pid, {})

            personal = 0.0
            if profile is not None:
                vec = vectors.get(pid)
                if vec is not None and len(vec) == len(profile):
                    personal = clamp(float(np.dot(profile, vec)))

            citations = int(paper.get("citation_count") or 0)
            components = {
                "semantic": entry["semantic"],
                "influence": float(graph_info.get("influence", 0.0)),
                "citation": (math.log1p(citations) / math.log1p(max_citations)
                             if max_citations > 1 else 0.0),
                "recency": recency_score(paper.get("year")),
                "personal": personal,
            }
            score = sum(weights[name] * components[name] for name in weights)

            boost = 1.0
            if intent.get("is_survey") and _SURVEY_RE.search(
                    f"{paper.get('title', '')} {paper.get('abstract', '')[:200]}"):
                boost = 1.12
            score = clamp(score * boost)

            ranked.append({
                "paper_id": pid,
                "score": round(score, 4),
                "components": {k: round(v, 4) for k, v in components.items()},
                "concepts": entry.get("concepts", []),
                "community": graph_info.get("community", -1),
                "community_label": graph_info.get("community_label", ""),
                "bridge": graph_info.get("bridge", 0.0),
                "boost": boost,
            })

        ranked.sort(key=lambda x: -x["score"])
        selected = self._mmr(ranked, vectors, top_k, config.MMR_LAMBDA)

        for rank, item in enumerate(selected, start=1):
            item["rank"] = rank

        ctx["log"](self.key, f"Scored {len(ranked)} papers with weights "
                             f"{', '.join(f'{k}={v}' for k, v in weights.items())}")
        ctx["log"](self.key, f"MMR diversified {len(selected)} results (lambda={config.MMR_LAMBDA})")

        note = f"{len(ranked)} scored → top {len(selected)} · weights {weights['semantic']:.2f}/{weights['influence']:.2f}/{weights['citation']:.2f}/{weights['recency']:.2f}/{weights['personal']:.2f}"
        return AgentResult(
            update={"ranked": selected, "weights": weights},
            note=note,
            metrics={"ranked": len(ranked), "returned": len(selected),
                     "top_score": selected[0]["score"] if selected else 0.0, "weights": weights},
        )

    @staticmethod
    def _mmr(ranked: list[dict], vectors: dict, top_k: int, lam: float) -> list[dict]:
        """Maximal Marginal Relevance: relevance minus redundancy."""
        pool = ranked[: max(top_k * 4, 24)]
        selected: list[dict] = []
        while pool and len(selected) < top_k:
            best_index, best_value = 0, -1e9
            for i, cand in enumerate(pool):
                vec = vectors.get(cand["paper_id"])
                redundancy = 0.0
                if vec is not None and selected:
                    sims = []
                    for chosen in selected:
                        other = vectors.get(chosen["paper_id"])
                        if other is not None and len(other) == len(vec):
                            sims.append(float(np.dot(vec, other)))
                    redundancy = max(sims) if sims else 0.0
                value = lam * cand["score"] - (1 - lam) * redundancy
                if value > best_value:
                    best_index, best_value = i, value
            chosen = pool.pop(best_index)
            chosen["mmr_value"] = round(best_value, 4)
            selected.append(chosen)
        return selected
