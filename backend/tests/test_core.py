"""Unit tests for the deterministic core.

    cd backend && pytest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.base import AgentResult, BaseAgent, new_state  # noqa: E402
from agents.orchestrator import AgentOrchestrator  # noqa: E402
from services.embeddings import TfidfSvdEmbedder  # noqa: E402
from services.graphstore import NetworkXGraphStore  # noqa: E402
from services.lexical import BM25Index  # noqa: E402
from services.nlp import (TextAnalyzer, expand_query, extractive_summary,  # noqa: E402
                          split_sentences)
from services.citation import export, to_apa, to_bibtex, to_ris  # noqa: E402
from services.repository import SQLiteRepository  # noqa: E402

CORPUS = [
    "Multi-agent large language models coordinate specialised agents for complex research tasks.",
    "Retrieval augmented generation improves factual accuracy of language models with external documents.",
    "Citation graph neural networks recommend scientific papers using bibliographic structure.",
    "Explainable recommendation systems justify their suggestions to end users.",
]


# --------------------------------------------------------------------- nlp
def test_acronym_expansion_and_intent():
    analyzer = TextAnalyzer()
    analyzer.fit(CORPUS)
    parsed = expand_query("survey of RAG for scientific QA since 2021", analyzer)
    assert parsed["intent"]["is_survey"] is True
    assert parsed["filters"]["year_from"] == 2021
    assert "rag" in parsed["expansions"]
    assert any("retrieval" in t for t in parsed["expansions"]["rag"])
    assert parsed["keywords"]


def test_extractive_summary_is_bounded():
    text = " ".join(CORPUS)
    summary = extractive_summary(text, ["retrieval", "citation"], max_sentences=2)
    assert 0 < len(summary) <= len(text)
    assert len(split_sentences(summary)) <= 2


def test_sentence_split_keeps_sentences():
    sentences = split_sentences("First sentence about agents here. Second one about graphs, also here!")
    assert len(sentences) == 2


# ----------------------------------------------------------------- lexical
def test_bm25_ranks_matching_document_first():
    index = BM25Index()
    index.build([(f"d{i}", doc) for i, doc in enumerate(CORPUS)])
    hits = index.search("citation graph papers", k=3)
    assert hits, "expected at least one lexical hit"
    assert hits[0][0] == "d2"


def test_bm25_returns_nothing_for_unknown_terms():
    index = BM25Index()
    index.build([(f"d{i}", doc) for i, doc in enumerate(CORPUS)])
    assert index.search("zzzqqq", k=3) == []


# -------------------------------------------------------------- embeddings
def test_embeddings_are_normalised():
    embedder = TfidfSvdEmbedder(dim=32)
    embedder.fit(CORPUS)
    matrix = embedder.embed_documents(CORPUS)
    assert matrix.shape[0] == len(CORPUS)
    norms = np.linalg.norm(matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)
    query = embedder.embed_query("citation graph")
    assert query.shape[0] == matrix.shape[1]


# -------------------------------------------------------------- repository
def test_repository_roundtrip(tmp_path):
    repo = SQLiteRepository(str(tmp_path / "test.sqlite3"))
    repo.init()

    paper = {"paper_id": "arxiv:1", "title": "A paper", "abstract": "abs", "authors": ["A", "B"],
             "year": 2024, "venue": "arXiv", "categories": ["cs.AI"], "citation_count": 3}
    repo.upsert_paper(paper)
    repo.upsert_paper(paper)  # idempotent
    stored = repo.get_paper("arxiv:1")
    assert stored["title"] == "A paper"
    assert stored["authors"] == ["A", "B"]
    assert len(repo.all_papers()) == 1

    repo.add_to_library("s1", "arxiv:1", "Reading list")
    repo.add_to_library("s1", "arxiv:1", "Reading list")  # idempotent
    assert len(repo.get_library("s1")) == 1
    repo.remove_from_library("s1", "arxiv:1")
    assert repo.get_library("s1") == []

    repo.record_feedback("s1", "arxiv:1", "like")
    repo.record_feedback("s1", "arxiv:1", "save")
    assert repo.feedback_counts("s1") == {"like": 1, "save": 1}

    profile = np.array([0.1, 0.2, 0.3], dtype="float32")
    repo.save_session("s1", profile, {"personal": 0.2})
    session = repo.get_session("s1")
    assert np.allclose(session["profile"], profile)
    assert session["weights"]["personal"] == 0.2

    repo.log_search("s1", "citation graph", 5, 120)
    insights = repo.insights()
    assert insights["searches"] == 1
    assert insights["papers"] == 1
    assert insights["avg_latency_ms"] == 120.0


# ------------------------------------------------------------------- graph
def test_graph_analytics():
    store = NetworkXGraphStore()
    for i in range(4):
        store.upsert_paper({"paper_id": f"p{i}", "title": f"Paper {i}", "year": 2020 + i,
                            "categories": ["cs.AI"], "citation_count": i})
    store.add_edge("p0", "p1", "similar_to", 0.9)
    store.add_edge("p1", "p2", "similar_to", 0.8)
    store.add_edge("p2", "p3", "similar_to", 0.7)

    stats = store.stats()
    assert stats["nodes"] == 4
    assert stats["edges"] == 3

    analytics = store.analytics()
    assert len(analytics["pagerank"]) == 4
    assert abs(sum(analytics["pagerank"].values()) - 1.0) < 1e-6
    assert set(analytics["community"]) == {"p0", "p1", "p2", "p3"}

    neighbours = store.neighbors("p1", depth=1)
    assert "p0" in {n["id"] for n in neighbours["nodes"]}


# ------------------------------------------------------------ orchestrator
class _OkAgent(BaseAgent):
    key = "ok"
    label = "OK agent"

    def run(self, state, ctx):
        return AgentResult(update={"ok": True}, note="fine")


class _BoomAgent(BaseAgent):
    key = "boom"
    label = "Boom agent"

    def run(self, state, ctx):
        raise RuntimeError("intentional failure")


def test_orchestrator_survives_failing_agent():
    events = []
    orchestrator = AgentOrchestrator([_OkAgent(), _BoomAgent(), _OkAgent()], emitter=events.append)
    state = orchestrator.run(new_state("q", "s"), {"config": None})

    assert state["ok"] is True
    assert len(state["trace"]) == 3
    assert state["errors"] and state["errors"][0]["agent"] == "boom"
    assert any(e["event"] == "agent_error" for e in events)
    assert sum(1 for e in events if e["event"] == "agent_start") == 3


# ------------------------------------------------------------- notes/history
def test_notes_and_history(tmp_path):
    repo = SQLiteRepository(str(tmp_path / "notes.sqlite3"))
    repo.init()
    repo.upsert_paper({"paper_id": "arxiv:9", "title": "Note paper", "abstract": "a",
                       "authors": ["X"], "year": 2024, "categories": ["cs.AI"]})

    repo.save_note("s1", "arxiv:9", "method looks promising")
    repo.save_note("s1", "arxiv:9", "updated note")
    notes = repo.get_notes("s1")
    assert notes["arxiv:9"]["body"] == "updated note"

    repo.delete_note("s1", "arxiv:9")
    assert repo.get_notes("s1") == {}

    repo.log_search("s1", "graph recommendation", 5, 90)
    repo.log_search("s1", "graph recommendation", 5, 80)
    repo.log_search("s1", "dense retrieval", 5, 70)
    queries = repo.recent_queries("s1", limit=5)
    assert len(queries) == 2
    assert queries[0]["query"] == "dense retrieval"

    repo.clear_history("s1")
    assert repo.recent_queries("s1") == []


# ------------------------------------------------------------ citation export
PAPER = {"paper_id": "arxiv:2401.00001", "title": "A Study of Citation Graphs",
         "authors": ["Ada Lovelace", "Alan Turing"], "year": 2024, "venue": "arXiv",
         "url": "https://arxiv.org/abs/2401.00001", "source": "arxiv",
         "abstract": "We study citation graphs.", "citation_count": 12}


def test_bibtex_export():
    bib = to_bibtex(PAPER)
    assert bib.startswith("@misc{lovelace2024a")
    assert "Ada Lovelace and Alan Turing" in bib
    assert "eprint = {2401.00001}" in bib
    assert bib.count("{") == bib.count("}")


def test_ris_and_apa_export():
    ris = to_ris(PAPER)
    assert ris.startswith("TY  -")
    assert "AU  - Ada Lovelace" in ris
    assert ris.strip().endswith("ER  -")
    apa = to_apa(PAPER)
    assert "Lovelace" in apa and "(2024)" in apa


def test_export_bundle():
    text = export([PAPER, PAPER], "ris")
    assert text.count("TY  -") == 2
    assert export([PAPER], "unknown-format").startswith("@")
