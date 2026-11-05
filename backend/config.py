"""Central configuration.

Every external dependency is optional: if a backend (Neo4j, FAISS,
sentence-transformers, an LLM key) is unavailable the app degrades to a
self-contained implementation instead of crashing.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:  # optional, only for local .env files
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:  # pragma: no cover - dotenv is a convenience only
    pass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # --- app -------------------------------------------------------------
    ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # Bind to loopback for local use, but to all interfaces when a hosting
    # platform injects PORT (Render, Railway, Fly, Heroku...). Without this the
    # container listens on 127.0.0.1 only and the platform's port scan fails.
    HOST = os.getenv("HOST") or ("0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    PORT = _int("PORT", 7000)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    JSON_SORT_KEYS = False

    # --- storage ---------------------------------------------------------
    DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
    SEED_CORPUS = DATA_DIR / "seed_corpus.json"
    DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "paperrec.sqlite3"))
    GRAPH_SNAPSHOT = str(DATA_DIR / "graph_snapshot.json")

    # MongoDB takes priority over SQLite when MONGO_URI is set.
    MONGO_URI = os.getenv("MONGO_URI", "")
    MONGO_DB = os.getenv("MONGO_DB", "paperrec")

    # Neo4j takes priority over the in-process NetworkX graph when set.
    NEO4J_URI = os.getenv("NEO4J_URI", "")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

    # --- retrieval -------------------------------------------------------
    # auto  -> probe the network once, use live APIs when reachable
    # on    -> always call live APIs
    # off   -> offline only (seed corpus)
    ONLINE_MODE = os.getenv("ONLINE_MODE", "auto").lower()
    ARXIV_ENABLED = _bool("ARXIV_ENABLED", True)
    S2_ENABLED = _bool("S2_ENABLED", True)
    S2_API_KEY = os.getenv("S2_API_KEY", "")
    HTTP_TIMEOUT = _float("HTTP_TIMEOUT", 6.0)
    LIVE_RESULT_LIMIT = _int("LIVE_RESULT_LIMIT", 25)

    # --- AI --------------------------------------------------------------
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "auto").lower()  # auto|sentence-transformers|tfidf
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_DIM = _int("EMBEDDING_DIM", 384)
    VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "auto").lower()  # auto|faiss|numpy

    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()  # none|gemini|openai|groq
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "")

    # --- recommendation --------------------------------------------------
    TOP_K = _int("TOP_K", 12)
    CANDIDATE_LIMIT = _int("CANDIDATE_LIMIT", 120)
    MMR_LAMBDA = _float("MMR_LAMBDA", 0.75)
    # floor for kNN similarity edges (each paper links to its k most similar peers)
    SIMILARITY_EDGE_THRESHOLD = _float("SIMILARITY_EDGE_THRESHOLD", 0.02)
    SIMILARITY_KNN = _int("SIMILARITY_KNN", 6)

    WEIGHTS = {
        "semantic": _float("W_SEMANTIC", 0.52),
        "influence": _float("W_INFLUENCE", 0.14),
        "citation": _float("W_CITATION", 0.12),
        "recency": _float("W_RECENCY", 0.12),
        "personal": _float("W_PERSONAL", 0.10),
    }

    CACHE_TTL = _int("CACHE_TTL", 300)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024


config = Config()
