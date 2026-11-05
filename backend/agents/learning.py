"""Agent 8 - Continuous Learning.

Persists the interaction, drifts the session interest profile towards what
the researcher is currently searching for, and adapts ranking weights from
explicit feedback (save / like / dismiss).
"""
from __future__ import annotations

import numpy as np

from agents.base import AgentResult, BaseAgent
from services.nlp import clamp

PROFILE_MOMENTUM = 0.85  # old profile weight; 0.15 goes to the new query


class LearningAgent(BaseAgent):
    key = "learning"
    label = "Continuous Learning"
    description = "Interest-profile drift, weight adaptation and interaction logging"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        repo = ctx["repo"]
        index = ctx["index"]
        session_id = state["session_id"]
        session = ctx.get("session") or {}
        total_ms = int(sum(state.get("timings", {}).values()))

        # 1. log the search
        try:
            repo.log_search(session_id, state["query"], len(state.get("ranked", [])), total_ms)
        except Exception:  # noqa: BLE001 - logging must never break a search
            ctx["log"](self.key, "Could not persist search log")

        # 2. drift the interest profile towards the current query
        understanding = state.get("understanding", {})
        query_vector = index.embed(understanding.get("expanded_text") or state["query"])
        profile = session.get("profile")
        if profile is not None and len(profile) == len(query_vector):
            updated = PROFILE_MOMENTUM * np.asarray(profile, dtype="float32") + \
                      (1 - PROFILE_MOMENTUM) * query_vector
        else:
            updated = np.asarray(query_vector, dtype="float32")
        norm = float(np.linalg.norm(updated)) or 1.0
        updated = (updated / norm).astype("float32")

        # 3. adapt weights from explicit feedback
        weights = dict(state.get("weights") or ctx["config"].WEIGHTS)
        try:
            counts = repo.feedback_counts(session_id)
        except Exception:  # noqa: BLE001
            counts = {}
        positive = counts.get("like", 0) + counts.get("save", 0)
        negative = counts.get("dismiss", 0)
        delta = 0.0
        if positive or negative:
            delta = clamp(0.005 * (positive - negative), -0.06, 0.06)
            weights["personal"] = round(max(0.02, min(0.35, weights.get("personal", 0.1) + delta)), 4)
            weights["semantic"] = round(max(0.2, min(0.75, weights.get("semantic", 0.52) - delta / 2)), 4)
            total = sum(weights.values()) or 1.0
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        try:
            repo.save_session(session_id, updated, weights)
        except Exception:  # noqa: BLE001
            ctx["log"](self.key, "Could not persist session profile")

        ctx["log"](self.key, f"Profile updated ({len(updated)} dims) · "
                             f"feedback +{positive}/-{negative} · weight drift {delta:+.3f}")
        ctx["log"](self.key, f"Search persisted in {total_ms} ms")

        return AgentResult(
            update={"learning": {"profile_dims": int(len(updated)),
                                 "weights": weights,
                                 "feedback": counts,
                                 "latency_ms": total_ms}},
            note=f"profile updated · {positive} positive / {negative} negative signals",
            metrics={"profile_dims": int(len(updated)), "feedback": counts},
        )
