"""Benchmark the pipeline: latency, diversity (MMR effect), retrieval overlap
and graph statistics. Writes docs/benchmark.json used by the report.

Run:  python scripts/benchmark.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, "/scratch/work/paperrec/backend")

from api import create_app  # noqa: E402
from config import config  # noqa: E402

QUERIES = [
    "multi-agent LLM systems for scientific literature review",
    "retrieval augmented generation for scientific question answering",
    "citation graph based paper recommendation",
    "survey of explainable recommendation systems",
    "knowledge graph embedding techniques",
    "abstractive summarization of research papers",
    "dense retrieval with transformer embeddings",
    "contrastive learning for representation learning",
    "graph neural networks for ranking",
    "learning to rank for academic search",
    "detecting hallucination in large language models",
    "personalized research paper recommender systems",
]


def mean_pairwise_distance(vectors: list[np.ndarray]) -> float:
    if len(vectors) < 2:
        return 0.0
    sims = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            sims.append(float(np.dot(vectors[i], vectors[j])))
    return 1.0 - float(np.mean(sims))


def main() -> None:
    app = create_app(config)
    container = app.extensions["container"]
    service = container.search
    index = container.index

    latencies, agent_times, counts = [], {}, []
    diversity_mmr, diversity_plain = [], []
    overlap_bm25 = []
    per_query = []

    for query in QUERIES:
        t0 = time.perf_counter()
        payload = service.search(query, "benchmark-session", top_k=10)
        elapsed = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed)
        counts.append(len(payload["results"]))
        for agent, ms in payload["timings"].items():
            agent_times.setdefault(agent, []).append(ms)

        top_ids = [r["paper_id"] for r in payload["results"]]
        vectors = [index.vector_of(pid) for pid in top_ids]
        vectors = [v for v in vectors if v is not None]
        diversity_mmr.append(mean_pairwise_distance(vectors))

        # lexical baseline overlap
        lexical = [pid for pid, _ in index.lexical_search(query, k=20)]
        overlap_bm25.append(len(set(top_ids) & set(lexical)) / max(1, len(top_ids)))

        per_query.append({
            "query": query,
            "latency_ms": round(elapsed, 1),
            "results": len(payload["results"]),
            "top_titles": [r["paper"]["title"][:80] for r in payload["results"][:5]],
            "top_scores": [r["score"] for r in payload["results"][:5]],
            "candidates": payload["meta"]["candidates"],
        })
        print(f"  {elapsed:7.1f} ms  {len(payload['results']):2d} results  {query[:58]}")

    # MMR off (lambda = 1.0) for the diversity comparison
    config.MMR_LAMBDA = 1.0
    for query in QUERIES:
        payload = service.search(query, "benchmark-session-mmr", top_k=10)
        vectors = [index.vector_of(r["paper_id"]) for r in payload["results"]]
        vectors = [v for v in vectors if v is not None]
        diversity_plain.append(mean_pairwise_distance(vectors))
    config.MMR_LAMBDA = 0.75

    analytics = index.analytics()
    graph = index.graph.stats()
    import networkx as nx

    modularity = 0.0
    try:
        g = index.graph.graph if hasattr(index.graph, "graph") else None
        if g is not None and g.number_of_edges():
            communities = list(nx.community.greedy_modularity_communities(g, weight="weight"))
            modularity = nx.community.modularity(g, communities, weight="weight")
    except Exception:  # noqa: BLE001
        pass

    latencies_sorted = sorted(latencies)
    p95 = latencies_sorted[min(len(latencies_sorted) - 1, int(0.95 * len(latencies_sorted)))]

    report = {
        "queries": len(QUERIES),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 1),
            "median": round(statistics.median(latencies), 1),
            "p95": round(p95, 1),
            "min": round(min(latencies), 1),
            "max": round(max(latencies), 1),
        },
        "agent_latency_ms": {
            agent: {"mean": round(statistics.mean(times), 1),
                    "max": round(max(times), 1),
                    "share": round(100 * sum(times) / sum(sum(v) for v in agent_times.values()), 1)}
            for agent, times in agent_times.items()
        },
        "results_per_query": round(statistics.mean(counts), 2),
        "diversity": {
            "with_mmr": round(statistics.mean(diversity_mmr), 4),
            "without_mmr": round(statistics.mean(diversity_plain), 4),
            "gain_pct": round(100 * (statistics.mean(diversity_mmr) - statistics.mean(diversity_plain))
                              / max(1e-9, statistics.mean(diversity_plain)), 2),
        },
        "lexical_overlap": round(statistics.mean(overlap_bm25), 4),
        "graph": {**graph, "communities": analytics["communities"], "modularity": round(modularity, 4)},
        "corpus": {
            "papers": len(index.papers),
            "embedding": index.embedder.info(),
            "vector_backend": index.vector_store.info(),
        },
        "per_query": per_query,
    }

    out = "/scratch/work/paperrec/docs/benchmark.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)

    print("\nLatency  mean %.1f ms | median %.1f ms | p95 %.1f ms" % (
        report["latency_ms"]["mean"], report["latency_ms"]["median"], report["latency_ms"]["p95"]))
    print("Diversity MMR %.4f vs plain %.4f (%.1f%%)" % (
        report["diversity"]["with_mmr"], report["diversity"]["without_mmr"], report["diversity"]["gain_pct"]))
    print("Lexical overlap %.3f | communities %s | modularity %.3f" % (
        report["lexical_overlap"], analytics["communities"], modularity))
    print("Saved ->", out)


if __name__ == "__main__":
    main()
