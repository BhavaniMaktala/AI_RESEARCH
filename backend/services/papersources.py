"""Paper sources: Semantic Scholar, arXiv and the bundled offline corpus.

Live sources are probed once and cached; if the network is unavailable the
platform keeps working from the seed corpus, so a demo never breaks.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

from services.cache import TTLCache
from services.nlp import normalize_title

log = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

S2_FIELDS = ("title,abstract,year,authors,venue,citationCount,externalIds,url,"
             "referenceCount,fieldsOfStudy,publicationDate,openAccessPdf")


def _year_from(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


def normalize_paper(raw: dict) -> dict:
    """Force every source into one canonical paper schema."""
    paper_id = str(raw.get("paper_id") or raw.get("id") or "").strip()
    if not paper_id:
        paper_id = "title:" + normalize_title(raw.get("title", ""))[:80]
    authors = raw.get("authors") or []
    if authors and isinstance(authors[0], dict):
        authors = [a.get("name", "") for a in authors]
    return {
        "paper_id": paper_id,
        "source": raw.get("source", "unknown"),
        "title": " ".join(str(raw.get("title", "")).split()),
        "abstract": " ".join(str(raw.get("abstract") or "").split()),
        "authors": [a for a in authors if a][:12],
        "year": raw.get("year") or _year_from(raw.get("published")),
        "venue": raw.get("venue") or "",
        "url": raw.get("url") or "",
        "pdf_url": raw.get("pdf_url") or "",
        "categories": list(raw.get("categories") or [])[:6],
        "citation_count": int(raw.get("citation_count") or 0),
        "published": raw.get("published") or "",
    }


@dataclass
class SourceReport:
    used: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    live: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"sources_used": self.used, "sources_failed": self.failed,
                "live": self.live, "notes": self.notes}


class SeedCorpusSource:
    name = "local-corpus"

    def __init__(self, path: str):
        self.path = path
        self._papers: list[dict] = []
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                payload = json.load(fh)
            self._papers = [normalize_paper(p) for p in payload.get("papers", [])]
            log.info("Loaded %s seed papers from %s", len(self._papers), self.path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load seed corpus: %s", exc)
            self._papers = []

    @property
    def papers(self) -> list[dict]:
        return self._papers


class ArxivSource:
    name = "arxiv"

    def __init__(self, timeout: float = 6.0, enabled: bool = True):
        self.timeout = timeout
        self.enabled = enabled

    def _query_string(self, keywords: list[str], raw: str) -> str:
        terms = [k for k in keywords[:4] if len(k) > 2] or [raw]
        parts = []
        for t in terms:
            t = t.replace('"', "").strip()
            parts.append(f'all:"{t}"' if " " in t else f"all:{t}")
        return " AND ".join(parts)

    def search(self, raw_query: str, keywords: list[str], limit: int = 20) -> list[dict]:
        if not self.enabled:
            return []
        params = {
            "search_query": self._query_string(keywords, raw_query),
            "start": 0,
            "max_results": min(max(limit, 1), 50),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
        resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "PaperRec/1.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        papers = []
        for entry in root.findall("a:entry", NS):
            def txt(tag: str) -> str:
                el = entry.find(tag, NS)
                return (el.text or "").strip() if el is not None else ""

            link = txt("a:id")
            arxiv_id = link.rsplit("/", 1)[-1] if link else ""
            pdf = ""
            for ln in entry.findall("a:link", NS):
                if ln.get("title") == "pdf":
                    pdf = ln.get("href", "")
            papers.append(normalize_paper({
                "paper_id": f"arxiv:{arxiv_id}",
                "source": "arxiv",
                "title": txt("a:title"),
                "abstract": txt("a:summary"),
                "authors": [a.find("a:name", NS).text for a in entry.findall("a:author", NS)],
                "published": txt("a:published"),
                "venue": "arXiv",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": pdf or f"https://arxiv.org/pdf/{arxiv_id}",
                "categories": [c.get("term") for c in entry.findall("a:category", NS)],
                "citation_count": 0,
            }))
        return [p for p in papers if p["title"] and len(p["abstract"]) > 60]


class SemanticScholarSource:
    name = "semantic-scholar"

    def __init__(self, api_key: str = "", timeout: float = 6.0, enabled: bool = True):
        self.api_key = api_key
        self.timeout = timeout
        self.enabled = enabled

    def _headers(self) -> dict:
        headers = {"User-Agent": "PaperRec/1.0"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def probe(self) -> bool:
        if not self.enabled:
            return False
        try:
            resp = requests.get(f"{S2_API}/paper/search", params={"query": "retrieval", "limit": 1,
                                                                  "fields": "title"},
                                timeout=min(self.timeout, 3.5), headers=self._headers())
            return resp.status_code < 500
        except Exception:  # noqa: BLE001
            return False

    def search(self, query: str, limit: int = 20) -> list[dict]:
        if not self.enabled:
            return []
        resp = requests.get(
            f"{S2_API}/paper/search",
            params={"query": query, "limit": min(max(limit, 1), 50), "fields": S2_FIELDS},
            timeout=self.timeout, headers=self._headers(),
        )
        if resp.status_code == 429:
            raise RuntimeError("rate limited")
        resp.raise_for_status()
        papers = []
        for item in resp.json().get("data", []) or []:
            ext = item.get("externalIds") or {}
            pid = f"s2:{item['paperId']}" if item.get("paperId") else f"doi:{ext.get('DOI', '')}"
            papers.append(normalize_paper({
                "paper_id": pid,
                "source": "semantic-scholar",
                "title": item.get("title"),
                "abstract": item.get("abstract") or "",
                "authors": item.get("authors") or [],
                "year": item.get("year"),
                "venue": item.get("venue") or "",
                "url": item.get("url") or "",
                "pdf_url": ((item.get("openAccessPdf") or {}) or {}).get("url", ""),
                "categories": item.get("fieldsOfStudy") or [],
                "citation_count": item.get("citationCount") or 0,
            }))
        return [p for p in papers if p["title"]]

    def references(self, paper_id: str, limit: int = 40) -> list[str]:
        """Titles of papers this one cites (used to build real citation edges)."""
        if not paper_id.startswith("s2:"):
            return []
        sid = paper_id[3:]
        try:
            resp = requests.get(
                f"{S2_API}/paper/{sid}/references",
                params={"fields": "title,year", "limit": limit},
                timeout=self.timeout, headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return [d["citedPaper"]["title"] for d in resp.json().get("data", [])
                    if d.get("citedPaper") and d["citedPaper"].get("title")]
        except Exception:  # noqa: BLE001
            return []


class PaperSourceManager:
    """Aggregates every source, dedupes, and reports what was actually used."""

    def __init__(self, config, cache: TTLCache):
        self.config = config
        self.cache = cache
        self.seed = SeedCorpusSource(str(config.SEED_CORPUS))
        self.arxiv = ArxivSource(config.HTTP_TIMEOUT, config.ARXIV_ENABLED)
        self.s2 = SemanticScholarSource(config.S2_API_KEY, config.HTTP_TIMEOUT, config.S2_ENABLED)
        self._online_state: bool | None = None
        self._online_checked_at = 0.0

    # -- availability -----------------------------------------------------
    def online(self) -> bool:
        mode = (self.config.ONLINE_MODE or "auto").lower()
        if mode == "off":
            return False
        if mode == "on":
            return True
        now = time.time()
        if self._online_state is None or now - self._online_checked_at > 120:
            self._online_state = self.s2.probe()
            self._online_checked_at = now
            log.info("Live paper APIs reachable: %s", self._online_state)
        return bool(self._online_state)

    # -- retrieval --------------------------------------------------------
    def gather(self, query: str, keywords: list[str], limit: int = 40) -> tuple[list[dict], SourceReport]:
        report = SourceReport()
        collected: list[dict] = []
        report.used.append("local-corpus")

        if self.online():
            report.live = True
            live_budget = min(limit, self.config.LIVE_RESULT_LIMIT)
            for source, call in (
                (self.s2, lambda: self.s2.search(query, live_budget)),
                (self.arxiv, lambda: self.arxiv.search(query, keywords, live_budget)),
            ):
                key = ("search", source.name, query, live_budget)
                cached = self.cache.get(key)
                if cached is not None:
                    collected.extend(cached)
                    report.used.append(source.name)
                    continue
                try:
                    found = call()
                    self.cache.set(key, found)
                    collected.extend(found)
                    report.used.append(source.name)
                except Exception as exc:  # noqa: BLE001
                    report.failed.append(source.name)
                    report.notes.append(f"{source.name}: {exc}")
                    log.info("%s unavailable: %s", source.name, exc)
        else:
            report.notes.append("Offline mode: using the bundled arXiv corpus only")

        return collected, report

    def references_for(self, paper_id: str, limit: int = 40) -> list[str]:
        if not self.online():
            return []
        return self.cache.get_or_set(("refs", paper_id), lambda: self.s2.references(paper_id, limit))
