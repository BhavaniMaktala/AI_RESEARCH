"""Agent contracts.

Every specialist agent receives the shared pipeline state, returns a partial
update, and reports a human-readable note that is streamed to the UI as part
of the live agent trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentResult:
    update: dict = field(default_factory=dict)
    note: str = ""
    metrics: dict = field(default_factory=dict)


class BaseAgent:
    key: str = "agent"
    label: str = "Agent"
    description: str = ""

    def run(self, state: dict, ctx: dict) -> AgentResult:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> dict:
        return {"key": self.key, "label": self.label, "description": self.description}


def new_state(query: str, session_id: str, filters: dict | None = None, top_k: int = 12) -> dict:
    return {
        "request_id": "",
        "session_id": session_id,
        "query": query,
        "filters": filters or {},
        "top_k": top_k,
        "understanding": {},
        "candidates": [],
        "pool_size": 0,
        "source_report": {},
        "scored": [],
        "ranked": [],
        "summaries": {},
        "explanations": {},
        "graph": {},
        "timings": {},
        "trace": [],
        "errors": [],
    }
