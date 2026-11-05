"""Persistence layer.

Default: SQLite (zero setup, ships with Python).
Optional: MongoDB when MONGO_URI is set and pymongo is installed.

Both implementations expose the same interface, so routes and agents never
know which one is active.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default if default is not None else []


class BaseRepository:
    kind = "base"

    def init(self) -> None: ...
    def upsert_paper(self, paper: dict) -> None: ...
    def get_paper(self, paper_id: str) -> dict | None: ...
    def list_papers(self, limit: int = 50, offset: int = 0) -> list[dict]: ...
    def log_search(self, session_id: str, query: str, result_count: int, latency_ms: int) -> None: ...
    def record_feedback(self, session_id: str, paper_id: str, action: str, query: str | None = None) -> None: ...
    def get_session(self, session_id: str) -> dict: ...
    def save_session(self, session_id: str, profile: np.ndarray | None, weights: dict) -> None: ...
    def add_to_library(self, session_id: str, paper_id: str, list_name: str = "Reading list") -> None: ...
    def remove_from_library(self, session_id: str, paper_id: str) -> None: ...
    def get_library(self, session_id: str) -> list[dict]: ...
    def feedback_counts(self, session_id: str) -> dict: ...
    def recent_queries(self, session_id: str, limit: int = 8) -> list[dict]: ...
    def clear_history(self, session_id: str) -> None: ...
    def save_note(self, session_id: str, paper_id: str, body: str) -> None: ...
    def get_notes(self, session_id: str) -> dict: ...
    def delete_note(self, session_id: str, paper_id: str) -> None: ...
    def insights(self) -> dict: ...
    def stats(self) -> dict: ...


class SQLiteRepository(BaseRepository):
    kind = "sqlite"

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    abstract TEXT,
                    authors TEXT,
                    year INTEGER,
                    venue TEXT,
                    url TEXT,
                    pdf_url TEXT,
                    categories TEXT,
                    source TEXT,
                    citation_count INTEGER DEFAULT 0,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    profile BLOB,
                    weights TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    paper_id TEXT,
                    action TEXT,
                    query TEXT,
                    ts TEXT
                );
                CREATE TABLE IF NOT EXISTS library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    paper_id TEXT,
                    list_name TEXT,
                    ts TEXT,
                    UNIQUE(session_id, paper_id, list_name)
                );
                CREATE TABLE IF NOT EXISTS search_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    query TEXT,
                    result_count INTEGER,
                    latency_ms INTEGER,
                    ts TEXT
                );
                CREATE TABLE IF NOT EXISTS notes (
                    session_id TEXT,
                    paper_id TEXT,
                    body TEXT,
                    ts TEXT,
                    PRIMARY KEY (session_id, paper_id)
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
                CREATE INDEX IF NOT EXISTS idx_library_session ON library(session_id);
                CREATE INDEX IF NOT EXISTS idx_search_ts ON search_log(ts);
                """
            )

    # -- papers -----------------------------------------------------------
    def upsert_paper(self, paper: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO papers (paper_id, title, abstract, authors, year, venue, url, pdf_url,
                                    categories, source, citation_count, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    title=excluded.title, abstract=excluded.abstract, authors=excluded.authors,
                    year=excluded.year, venue=excluded.venue, url=excluded.url,
                    pdf_url=excluded.pdf_url, categories=excluded.categories,
                    source=excluded.source, citation_count=excluded.citation_count,
                    updated_at=excluded.updated_at
                """,
                (
                    paper["paper_id"], paper.get("title", ""), paper.get("abstract", ""),
                    _dumps(paper.get("authors", [])), paper.get("year"),
                    paper.get("venue", ""), paper.get("url", ""), paper.get("pdf_url", ""),
                    _dumps(paper.get("categories", [])), paper.get("source", ""),
                    int(paper.get("citation_count") or 0), _now(),
                ),
            )

    def _row_to_paper(self, row: sqlite3.Row) -> dict:
        return {
            "paper_id": row["paper_id"], "title": row["title"], "abstract": row["abstract"],
            "authors": _loads(row["authors"]), "year": row["year"], "venue": row["venue"],
            "url": row["url"], "pdf_url": row["pdf_url"], "categories": _loads(row["categories"]),
            "source": row["source"], "citation_count": row["citation_count"],
        }

    def get_paper(self, paper_id: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
            return self._row_to_paper(row) if row else None

    def list_papers(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM papers ORDER BY citation_count DESC, year DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [self._row_to_paper(r) for r in rows]

    def all_papers(self) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM papers").fetchall()
            return [self._row_to_paper(r) for r in rows]

    # -- activity ---------------------------------------------------------
    def log_search(self, session_id: str, query: str, result_count: int, latency_ms: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO search_log (session_id, query, result_count, latency_ms, ts) VALUES (?,?,?,?,?)",
                (session_id, query[:400], int(result_count), int(latency_ms), _now()),
            )

    def record_feedback(self, session_id: str, paper_id: str, action: str, query: str | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback (session_id, paper_id, action, query, ts) VALUES (?,?,?,?,?)",
                (session_id, paper_id, action, (query or "")[:400], _now()),
            )

    # -- session profile --------------------------------------------------
    def get_session(self, session_id: str) -> dict:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO sessions (session_id, profile, weights, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (session_id, None, _dumps({}), _now(), _now()),
                )
                return {"session_id": session_id, "profile": None, "weights": {}}
            profile = None
            if row["profile"]:
                profile = np.frombuffer(row["profile"], dtype="float32").copy()
            return {"session_id": session_id, "profile": profile, "weights": _loads(row["weights"], {})}

    def save_session(self, session_id: str, profile: np.ndarray | None, weights: dict) -> None:
        blob = profile.astype("float32").tobytes() if profile is not None else None
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, profile, weights, created_at, updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                    profile=excluded.profile, weights=excluded.weights, updated_at=excluded.updated_at
                """,
                (session_id, blob, _dumps(weights), _now(), _now()),
            )

    # -- library ----------------------------------------------------------
    def add_to_library(self, session_id: str, paper_id: str, list_name: str = "Reading list") -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO library (session_id, paper_id, list_name, ts) VALUES (?,?,?,?)""",
                (session_id, paper_id, list_name or "Reading list", _now()),
            )

    def remove_from_library(self, session_id: str, paper_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM library WHERE session_id = ? AND paper_id = ?", (session_id, paper_id))

    def get_library(self, session_id: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT l.paper_id, l.list_name, l.ts AS added_at, p.title, p.authors, p.year,
                          p.venue, p.url, p.pdf_url, p.categories, p.citation_count
                   FROM library l LEFT JOIN papers p ON p.paper_id = l.paper_id
                   WHERE l.session_id = ? ORDER BY l.ts DESC""",
                (session_id,),
            ).fetchall()
            out = []
            for r in rows:
                out.append({
                    "paper_id": r["paper_id"], "list_name": r["list_name"], "added_at": r["added_at"],
                    "title": r["title"] or r["paper_id"], "authors": _loads(r["authors"]),
                    "year": r["year"], "venue": r["venue"], "url": r["url"], "pdf_url": r["pdf_url"],
                    "categories": _loads(r["categories"]), "citation_count": r["citation_count"] or 0,
                })
            return out

    def feedback_counts(self, session_id: str) -> dict:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT action, COUNT(*) c FROM feedback WHERE session_id = ? GROUP BY action",
                (session_id,),
            ).fetchall()
            return {r["action"]: r["c"] for r in rows}

    def recent_queries(self, session_id: str, limit: int = 8) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT query, COUNT(*) AS count, MAX(ts) AS last_seen, MAX(id) AS last_id
                   FROM search_log WHERE session_id = ? AND query <> ''
                   GROUP BY query ORDER BY last_id DESC LIMIT ?""",
                (session_id, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]

    def clear_history(self, session_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM search_log WHERE session_id = ?", (session_id,))

    # -- notes ------------------------------------------------------------
    def save_note(self, session_id: str, paper_id: str, body: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO notes (session_id, paper_id, body, ts) VALUES (?,?,?,?)
                   ON CONFLICT(session_id, paper_id) DO UPDATE SET
                       body=excluded.body, ts=excluded.ts""",
                (session_id, paper_id, body[:4000], _now()),
            )

    def get_notes(self, session_id: str) -> dict:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT paper_id, body, ts FROM notes WHERE session_id = ?", (session_id,)
            ).fetchall()
            return {r["paper_id"]: {"body": r["body"], "ts": r["ts"]} for r in rows}

    def delete_note(self, session_id: str, paper_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM notes WHERE session_id = ? AND paper_id = ?",
                         (session_id, paper_id))

    # -- analytics --------------------------------------------------------
    def insights(self) -> dict:
        with self._lock, self._connect() as conn:
            papers = conn.execute("SELECT COUNT(*) c FROM papers").fetchone()["c"]
            searches = conn.execute("SELECT COUNT(*) c FROM search_log").fetchone()["c"]
            avg_latency = conn.execute("SELECT COALESCE(AVG(latency_ms),0) a FROM search_log").fetchone()["a"]
            sessions = conn.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"]
            library_count = conn.execute("SELECT COUNT(*) c FROM library").fetchone()["c"]
            top_queries = [dict(r) for r in conn.execute(
                """SELECT query, COUNT(*) AS count, MAX(ts) AS last_seen FROM search_log
                   WHERE query <> '' GROUP BY query ORDER BY count DESC, last_seen DESC LIMIT 8"""
            ).fetchall()]
            feedback = {r["action"]: r["c"] for r in conn.execute(
                "SELECT action, COUNT(*) c FROM feedback GROUP BY action"
            ).fetchall()}
            recent = [dict(r) for r in conn.execute(
                """SELECT query, result_count, latency_ms, ts FROM search_log
                   ORDER BY id DESC LIMIT 10"""
            ).fetchall()]
            cat_rows = conn.execute("SELECT categories FROM papers").fetchall()

        categories: dict[str, int] = {}
        for r in cat_rows:
            for cat in _loads(r["categories"])[:2]:
                categories[cat] = categories.get(cat, 0) + 1
        top_categories = sorted(categories.items(), key=lambda kv: -kv[1])[:8]

        return {
            "papers": papers, "searches": searches, "sessions": sessions,
            "library_items": library_count,
            "avg_latency_ms": round(float(avg_latency), 1),
            "top_queries": top_queries, "feedback": feedback, "recent_searches": recent,
            "top_categories": [{"category": c, "count": n} for c, n in top_categories],
        }

    def stats(self) -> dict:
        return {"backend": self.kind, "path": self.path}


class MongoRepository(BaseRepository):
    """MongoDB adapter (used when MONGO_URI is configured)."""

    kind = "mongodb"

    def __init__(self, uri: str, db_name: str = "paperrec"):
        from pymongo import MongoClient

        self.client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        self.db = self.client[db_name]

    def init(self) -> None:
        self.db.papers.create_index("paper_id", unique=True)
        self.db.feedback.create_index([("session_id", 1), ("ts", -1)])
        self.db.library.create_index([("session_id", 1), ("paper_id", 1)], unique=True)
        self.db.search_log.create_index([("ts", -1)])

    def upsert_paper(self, paper: dict) -> None:
        doc = {k: paper.get(k) for k in ("paper_id", "title", "abstract", "authors", "year", "venue",
                                         "url", "pdf_url", "categories", "source")}
        doc["citation_count"] = int(paper.get("citation_count") or 0)
        doc["updated_at"] = _now()
        self.db.papers.update_one({"paper_id": paper["paper_id"]}, {"$set": doc}, upsert=True)

    def get_paper(self, paper_id: str) -> dict | None:
        doc = self.db.papers.find_one({"paper_id": paper_id}, {"_id": 0})
        return doc

    def list_papers(self, limit: int = 50, offset: int = 0) -> list[dict]:
        cur = self.db.papers.find({}, {"_id": 0}).sort([("citation_count", -1), ("year", -1)]).skip(offset).limit(limit)
        return list(cur)

    def all_papers(self) -> list[dict]:
        return list(self.db.papers.find({}, {"_id": 0}))

    def log_search(self, session_id: str, query: str, result_count: int, latency_ms: int) -> None:
        self.db.search_log.insert_one({"session_id": session_id, "query": query[:400],
                                       "result_count": int(result_count), "latency_ms": int(latency_ms),
                                       "ts": _now()})

    def record_feedback(self, session_id: str, paper_id: str, action: str, query: str | None = None) -> None:
        self.db.feedback.insert_one({"session_id": session_id, "paper_id": paper_id,
                                     "action": action, "query": (query or "")[:400], "ts": _now()})

    def get_session(self, session_id: str) -> dict:
        doc = self.db.sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not doc:
            self.db.sessions.insert_one({"session_id": session_id, "profile": None, "weights": {},
                                         "created_at": _now(), "updated_at": _now()})
            return {"session_id": session_id, "profile": None, "weights": {}}
        profile = np.frombuffer(doc["profile"], dtype="float32").copy() if doc.get("profile") else None
        return {"session_id": session_id, "profile": profile, "weights": doc.get("weights") or {}}

    def save_session(self, session_id: str, profile: np.ndarray | None, weights: dict) -> None:
        blob = profile.astype("float32").tobytes() if profile is not None else None
        self.db.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"profile": blob, "weights": weights, "updated_at": _now()},
             "$setOnInsert": {"created_at": _now()}},
            upsert=True,
        )

    def add_to_library(self, session_id: str, paper_id: str, list_name: str = "Reading list") -> None:
        self.db.library.update_one(
            {"session_id": session_id, "paper_id": paper_id},
            {"$set": {"list_name": list_name or "Reading list", "ts": _now()}},
            upsert=True,
        )

    def remove_from_library(self, session_id: str, paper_id: str) -> None:
        self.db.library.delete_one({"session_id": session_id, "paper_id": paper_id})

    def get_library(self, session_id: str) -> list[dict]:
        rows = list(self.db.library.find({"session_id": session_id}, {"_id": 0}).sort("ts", -1))
        out = []
        for r in rows:
            paper = self.db.papers.find_one({"paper_id": r["paper_id"]}, {"_id": 0}) or {}
            out.append({
                "paper_id": r["paper_id"], "list_name": r.get("list_name", "Reading list"),
                "added_at": r.get("ts"), "title": paper.get("title", r["paper_id"]),
                "authors": paper.get("authors", []), "year": paper.get("year"),
                "venue": paper.get("venue", ""), "url": paper.get("url", ""),
                "pdf_url": paper.get("pdf_url", ""), "categories": paper.get("categories", []),
                "citation_count": paper.get("citation_count", 0),
            })
        return out

    def feedback_counts(self, session_id: str) -> dict:
        return {d["_id"]: d["c"] for d in self.db.feedback.aggregate([
            {"$match": {"session_id": session_id}},
            {"$group": {"_id": "$action", "c": {"$sum": 1}}}])}

    def recent_queries(self, session_id: str, limit: int = 8) -> list[dict]:
        return [{"query": d["_id"], "count": d["count"], "last_seen": d.get("last_seen")}
                for d in self.db.search_log.aggregate([
                    {"$match": {"session_id": session_id, "query": {"$ne": ""}}},
                    {"$group": {"_id": "$query", "count": {"$sum": 1}, "last_seen": {"$max": "$ts"},
                                "last_id": {"$max": "$_id"}}},
                    {"$sort": {"last_id": -1}}, {"$limit": int(limit)}])]

    def clear_history(self, session_id: str) -> None:
        self.db.search_log.delete_many({"session_id": session_id})

    def save_note(self, session_id: str, paper_id: str, body: str) -> None:
        self.db.notes.update_one(
            {"session_id": session_id, "paper_id": paper_id},
            {"$set": {"body": body[:4000], "ts": _now()}}, upsert=True)

    def get_notes(self, session_id: str) -> dict:
        return {d["paper_id"]: {"body": d.get("body", ""), "ts": d.get("ts")}
                for d in self.db.notes.find({"session_id": session_id}, {"_id": 0})}

    def delete_note(self, session_id: str, paper_id: str) -> None:
        self.db.notes.delete_one({"session_id": session_id, "paper_id": paper_id})

    def insights(self) -> dict:
        papers = self.db.papers.count_documents({})
        searches = self.db.search_log.count_documents({})
        sessions = self.db.sessions.count_documents({})
        library_count = self.db.library.count_documents({})
        agg = list(self.db.search_log.aggregate([{"$group": {"_id": None, "avg": {"$avg": "$latency_ms"}}}]))
        avg_latency = agg[0]["avg"] if agg else 0
        top_queries = [{"query": d["_id"], "count": d["count"], "last_seen": d.get("last_seen")}
                       for d in self.db.search_log.aggregate([
                           {"$match": {"query": {"$ne": ""}}},
                           {"$group": {"_id": "$query", "count": {"$sum": 1}, "last_seen": {"$max": "$ts"}}},
                           {"$sort": {"count": -1}}, {"$limit": 8}])]
        feedback = {d["_id"]: d["c"] for d in self.db.feedback.aggregate(
            [{"$group": {"_id": "$action", "c": {"$sum": 1}}}])}
        recent = [{"query": d["query"], "result_count": d["result_count"], "latency_ms": d["latency_ms"],
                   "ts": d["ts"]} for d in self.db.search_log.find({}, {"_id": 0}).sort("_id", -1).limit(10)]
        cats: dict[str, int] = {}
        for doc in self.db.papers.find({}, {"categories": 1}):
            for c in (doc.get("categories") or [])[:2]:
                cats[c] = cats.get(c, 0) + 1
        return {
            "papers": papers, "searches": searches, "sessions": sessions,
            "library_items": library_count, "avg_latency_ms": round(float(avg_latency or 0), 1),
            "top_queries": top_queries, "feedback": feedback, "recent_searches": recent,
            "top_categories": [{"category": c, "count": n}
                               for c, n in sorted(cats.items(), key=lambda kv: -kv[1])[:8]],
        }

    def stats(self) -> dict:
        return {"backend": self.kind}


def build_repository(db_path: str, mongo_uri: str = "", mongo_db: str = "paperrec") -> BaseRepository:
    if mongo_uri:
        try:
            repo = MongoRepository(mongo_uri, mongo_db)
            repo.init()
            log.info("Database backend: MongoDB")
            return repo
        except Exception as exc:  # noqa: BLE001
            log.warning("MongoDB unavailable (%s); falling back to SQLite", exc)
    repo = SQLiteRepository(db_path)
    repo.init()
    log.info("Database backend: SQLite (%s)", db_path)
    return repo
