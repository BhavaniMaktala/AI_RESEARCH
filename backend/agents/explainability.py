"""Agent 7 - Explainability.

Turns the score vector into plain-language justifications, so every
recommendation can be audited by the researcher instead of trusted blindly.
"""
from __future__ import annotations

from agents.base import AgentResult, BaseAgent


class ExplainabilityAgent(BaseAgent):
    key = "explainability"
    label = "Explainability"
    description = "Per-recommendation justification from every ranking signal"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        index = ctx["index"]
        analytics = index.analytics()
        influence = analytics.get("influence", {})
        weights = state.get("weights", {})
        candidates = {p["paper_id"]: p for p in state.get("candidates", [])}
        explanations: dict[str, dict] = {}

        for item in state.get("ranked", []):
            pid = item["paper_id"]
            paper = candidates.get(pid, {})
            comp = item.get("components", {})
            reasons: list[dict] = []

            if comp.get("semantic", 0) > 0:
                concepts = item.get("concepts") or []
                detail = (f"shares the concepts: {', '.join(concepts[:3])}"
                          if concepts else "close in embedding space to your query")
                reasons.append({
                    "type": "semantic",
                    "label": "Topical relevance",
                    "value": comp["semantic"],
                    "text": f"Semantic similarity {comp['semantic']:.2f} — {detail}",
                })

            rank_pct = self._percentile(pid, influence)
            if comp.get("influence", 0) > 0:
                reasons.append({
                    "type": "influence",
                    "label": "Graph influence",
                    "value": comp["influence"],
                    "text": (f"PageRank influence {comp['influence']:.2f} — top "
                             f"{max(1, round((1 - rank_pct) * 100))}% of the indexed corpus"),
                })

            citations = int(paper.get("citation_count") or 0)
            if citations:
                reasons.append({
                    "type": "citation",
                    "label": "Citation impact",
                    "value": comp.get("citation", 0),
                    "text": f"Cited {citations:,} times",
                })
            elif paper.get("year"):
                reasons.append({
                    "type": "citation",
                    "label": "Emerging work",
                    "value": comp.get("citation", 0),
                    "text": f"Recent work from {paper['year']} — citation signal still forming",
                })

            if comp.get("recency", 0) > 0:
                reasons.append({
                    "type": "recency",
                    "label": "Recency",
                    "value": comp["recency"],
                    "text": f"Published {paper.get('year', 'n/a')} · recency score {comp['recency']:.2f}",
                })

            if item.get("bridge", 0) > 0.02:
                reasons.append({
                    "type": "interdisciplinary",
                    "label": "Interdisciplinary bridge",
                    "value": item["bridge"],
                    "text": (f"Connects research communities "
                             f"({item.get('community_label') or 'multiple clusters'}) — "
                             f"bridge score {item['bridge']:.2f}"),
                })

            if comp.get("personal", 0) > 0.15:
                reasons.append({
                    "type": "personal",
                    "label": "Your profile",
                    "value": comp["personal"],
                    "text": f"Aligns with papers you saved or liked ({comp['personal']:.2f})",
                })

            if item.get("boost", 1.0) > 1.0:
                reasons.append({
                    "type": "intent",
                    "label": "Survey intent",
                    "value": item["boost"],
                    "text": "Survey/review style paper, matching your intent",
                })

            top = sorted(reasons, key=lambda r: -r.get("value", 0))[:2]
            headline = " + ".join(r["label"].lower() for r in top) if top else "semantic match"
            explanations[pid] = {
                "headline": headline,
                "reasons": reasons,
                "confidence": round(min(0.99, item.get("score", 0) * 1.15), 3),
                "weights_used": weights,
            }

        ctx["log"](self.key, f"Generated {len(explanations)} explanations "
                             f"({sum(len(e['reasons']) for e in explanations.values())} signals)")
        return AgentResult(
            update={"explanations": explanations},
            note=f"{len(explanations)} explanations · avg {self._avg(explanations):.1f} signals",
            metrics={"explanations": len(explanations)},
        )

    @staticmethod
    def _percentile(pid: str, influence: dict) -> float:
        if not influence:
            return 1.0
        value = influence.get(pid, 0.0)
        below = sum(1 for v in influence.values() if v <= value)
        return below / len(influence)

    @staticmethod
    def _avg(explanations: dict) -> float:
        if not explanations:
            return 0.0
        return sum(len(e["reasons"]) for e in explanations.values()) / len(explanations)
