"""Agent orchestrator: a LangGraph-style state machine with live event
streaming.

Each node is an independent agent. Nodes share one mutable state dict, may
emit log lines, and never abort the pipeline: a failing agent records an
error and the graph continues with reduced capability.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Iterable

from agents.base import BaseAgent

log = logging.getLogger(__name__)

Emitter = Callable[[dict], None]


class AgentOrchestrator:
    def __init__(self, agents: Iterable[BaseAgent], emitter: Emitter | None = None):
        self.agents: list[BaseAgent] = list(agents)
        self.emitter = emitter

    def describe(self) -> list[dict]:
        return [a.describe() for a in self.agents]

    def _emit(self, payload: dict) -> None:
        if self.emitter:
            try:
                self.emitter(payload)
            except Exception:  # noqa: BLE001 - a dead stream must not kill a search
                log.debug("Emitter failed", exc_info=True)

    def run(self, state: dict, ctx: dict) -> dict:
        total = len(self.agents)
        ctx.setdefault("emit", self._emit)

        def log_line(agent_key: str, message: str) -> None:
            self._emit({"event": "log", "agent": agent_key, "message": message})

        ctx["log"] = log_line

        for index, agent in enumerate(self.agents):
            started = time.perf_counter()
            self._emit({
                "event": "agent_start", "agent": agent.key, "label": agent.label,
                "index": index, "total": total, "description": agent.description,
            })
            try:
                result = agent.run(state, ctx)
                state.update(result.update or {})
                duration = round((time.perf_counter() - started) * 1000, 1)
                state["timings"][agent.key] = duration
                entry = {
                    "agent": agent.key, "label": agent.label, "ms": duration,
                    "note": result.note, "status": "ok", "metrics": result.metrics,
                }
                state["trace"].append(entry)
                self._emit({"event": "agent_end", **entry, "index": index, "total": total})
            except Exception as exc:  # noqa: BLE001 - degrade, never crash
                duration = round((time.perf_counter() - started) * 1000, 1)
                state["timings"][agent.key] = duration
                message = f"{type(exc).__name__}: {exc}"
                state["errors"].append({"agent": agent.key, "error": message})
                entry = {"agent": agent.key, "label": agent.label, "ms": duration,
                         "note": "skipped after error", "status": "error", "metrics": {}}
                state["trace"].append(entry)
                log.exception("Agent %s failed", agent.key)
                self._emit({"event": "agent_error", **entry, "index": index, "total": total,
                            "message": message})
        return state


def build_orchestrator(emitter: Emitter | None = None) -> AgentOrchestrator:
    from agents.citation import CitationAgent
    from agents.explainability import ExplainabilityAgent
    from agents.learning import LearningAgent
    from agents.query_understanding import QueryUnderstandingAgent
    from agents.ranking import RankingAgent
    from agents.retrieval import RetrievalAgent
    from agents.semantic import SemanticAgent
    from agents.summarization import SummarizationAgent

    return AgentOrchestrator(
        [
            QueryUnderstandingAgent(),
            RetrievalAgent(),
            SemanticAgent(),
            CitationAgent(),
            RankingAgent(),
            SummarizationAgent(),
            ExplainabilityAgent(),
            LearningAgent(),
        ],
        emitter=emitter,
    )
