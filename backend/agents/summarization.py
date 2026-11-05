"""Agent 6 - Paper Summarization.

Extractive, query-focused summaries and contribution mining. Runs in
milliseconds and needs no API key; an LLM, when configured, is used for the
deeper per-paper summary on the detail endpoint.
"""
from __future__ import annotations

from agents.base import AgentResult, BaseAgent
from services.nlp import extract_contributions, extractive_summary


class SummarizationAgent(BaseAgent):
    key = "summarization"
    label = "Paper Summarization"
    description = "Query-focused extractive summaries and contribution extraction"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        analyzer = ctx["analyzer"]
        understanding = state.get("understanding", {})
        focus = understanding.get("keywords", [])[:8]
        summaries: dict[str, dict] = {}

        for item in state.get("ranked", []):
            paper = next((p for p in state["candidates"] if p["paper_id"] == item["paper_id"]), None)
            if not paper:
                continue
            abstract = paper.get("abstract") or ""
            summary = extractive_summary(abstract, focus, max_sentences=3, analyzer=analyzer)
            summaries[paper["paper_id"]] = {
                "summary": summary,
                "contributions": extract_contributions(abstract, limit=3),
                "word_count": len(summary.split()),
                "method": "extractive-query-focused",
            }

        avg = (sum(s["word_count"] for s in summaries.values()) / len(summaries)) if summaries else 0
        ctx["log"](self.key, f"Summarised {len(summaries)} papers (avg {avg:.0f} words)")
        return AgentResult(
            update={"summaries": summaries},
            note=f"{len(summaries)} summaries · avg {avg:.0f} words",
            metrics={"summaries": len(summaries), "avg_words": round(avg, 1)},
        )
