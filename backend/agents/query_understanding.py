"""Agent 1 - Query Understanding.

Turns a free-text research question into a structured search plan: intent,
expanded concepts, acronyms and filters.
"""
from __future__ import annotations

from agents.base import AgentResult, BaseAgent
from services.nlp import expand_query


class QueryUnderstandingAgent(BaseAgent):
    key = "query_understanding"
    label = "Query Understanding"
    description = "Parses intent, expands acronyms and synonyms, extracts year filters"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        analyzer = ctx["analyzer"]
        understanding = expand_query(state["query"], analyzer)

        # explicit request filters win over inferred ones
        requested = state.get("filters") or {}
        for key in ("year_from", "year_to"):
            if requested.get(key):
                understanding["filters"][key] = requested[key]

        ctx["log"](self.key, f"Intent detected: {understanding['intent']['type']}")
        for short, expansion in list(understanding["expansions"].items())[:3]:
            ctx["log"](self.key, f'Expanded "{short}" -> {" ".join(expansion[:4])}')

        concepts = understanding["keywords"][:8]
        note = (f"{understanding['intent']['type']} intent · {len(concepts)} concepts · "
                f"{len(understanding['expansions'])} expansions")
        return AgentResult(
            update={"understanding": understanding},
            note=note,
            metrics={"concepts": concepts, "intent": understanding["intent"]["type"],
                     "expansions": len(understanding["expansions"])},
        )
