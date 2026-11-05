"""Agent 3 - Semantic Analysis.

Embeds the query and every candidate, scores cosine similarity, merges the
lexical signal, and extracts the concepts each paper actually matches.
"""
from __future__ import annotations

import numpy as np

from agents.base import AgentResult, BaseAgent
from services.nlp import clamp, tokenize


class SemanticAgent(BaseAgent):
    key = "semantic"
    label = "Semantic Analysis"
    description = "Transformer/LSA embeddings, cosine ranking and concept matching"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        index = ctx["index"]
        understanding = state["understanding"]
        candidates = state["candidates"]

        if not candidates:
            return AgentResult(update={"scored": []}, note="no candidates to embed")

        query_text = understanding.get("expanded_text") or state["query"]
        query_vector = index.embed(query_text)
        concepts = [c for c in understanding.get("keywords", []) if len(c) > 2][:8]
        concept_tokens = {t for c in concepts for t in tokenize(c)}

        # embed anything not already in the index (live results)
        vectors: dict[str, np.ndarray] = {}
        missing = [p for p in candidates if index.vector_of(p["paper_id"]) is None]
        if missing:
            texts = [f"{p.get('title', '')} . {p.get('abstract', '')}" for p in missing]
            try:
                matrix = index.embedder.embed_documents(texts)
                for paper, vec in zip(missing, matrix):
                    vectors[paper["paper_id"]] = vec
            except Exception:  # noqa: BLE001 - embedding failure degrades to lexical only
                for paper in missing:
                    vectors[paper["paper_id"]] = np.zeros(len(query_vector), dtype="float32")

        max_lexical = max((p.get("_lexical", 0.0) for p in candidates), default=0.0) or 1.0
        scored = []
        for paper in candidates:
            pid = paper["paper_id"]
            vec = index.vector_of(pid)
            if vec is None:
                vec = vectors.get(pid)
            semantic = float(np.dot(query_vector, vec)) if vec is not None else 0.0
            semantic = clamp(semantic)
            lexical = clamp(paper.get("_lexical", 0.0) / max_lexical)
            relevance = 0.78 * semantic + 0.22 * lexical

            haystack = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
            matched = [c for c in concepts if c.lower() in haystack]
            if not matched:
                paper_tokens = set(tokenize(haystack)) & concept_tokens
                matched = sorted(paper_tokens)[:4]

            vectors[pid] = vec
            scored.append({
                "paper_id": pid,
                "semantic": round(semantic, 4),
                "lexical": round(lexical, 4),
                "relevance": round(relevance, 4),
                "concepts": matched[:6],
            })

        scored.sort(key=lambda x: -x["relevance"])
        ctx["vectors"] = vectors
        top = scored[0] if scored else None
        ctx["log"](self.key, f"Embedded {len(candidates)} candidates "
                             f"({index.embedder.kind}, {len(query_vector)} dims)")
        if top:
            ctx["log"](self.key, f"Best cosine match {top['semantic']:.3f} on {top['paper_id']}")

        note = f"{len(scored)} papers scored · best match {top['semantic']:.2f}" if top else "nothing scored"
        return AgentResult(
            update={"scored": scored},
            note=note,
            metrics={"scored": len(scored), "embedding": index.embedder.kind,
                     "top_semantic": top["semantic"] if top else 0.0},
        )
