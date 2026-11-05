"""Build the offline seed corpus from the public arXiv API.

Run:  python scripts/fetch_seed.py
Produces backend/data/seed_corpus.json (real titles, abstracts, authors, dates).
"""
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

OUT = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "seed_corpus.json")
API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

QUERIES = [
    "multi-agent large language models",
    "retrieval augmented generation",
    "citation recommendation",
    "scientific paper summarization",
    "dense retrieval semantic search",
    "knowledge graph embedding",
    "neural recommender systems",
    "explainable recommendation",
    "graph neural networks",
    "transformer language models",
    "contrastive representation learning",
    "abstractive text summarization",
    "scholarly document processing",
    "learning to rank",
    "in-context learning prompt",
    "large language model hallucination evaluation",
    "approximate nearest neighbor vector search",
    "research paper recommendation system",
    "scientific knowledge discovery",
    "question answering over documents",
]


def fetch(query: str, max_results: int = 8):
    params = {
        "search_query": f'all:"{query}"',
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "PaperRec/1.0 (research demo)"})
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    out = []
    for e in root.findall("a:entry", NS):
        def txt(tag):
            el = e.find(tag, NS)
            return (el.text or "").strip().replace("\n", " ") if el is not None else ""
        aid = txt("a:id")
        arxiv_id = aid.rsplit("/", 1)[-1]
        out.append({
            "paper_id": f"arxiv:{arxiv_id}",
            "source": "arxiv",
            "arxiv_id": arxiv_id,
            "title": " ".join(txt("a:title").split()),
            "abstract": " ".join(txt("a:summary").split()),
            "authors": [a.find("a:name", NS).text.strip() for a in e.findall("a:author", NS)],
            "published": txt("a:published")[:10],
            "updated": txt("a:updated")[:10],
            "categories": [c.get("term") for c in e.findall("a:category", NS)],
            "primary_category": (e.find("arxiv:primary_category", NS).get("term")
                                 if e.find("arxiv:primary_category", NS) is not None else ""),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            "citation_count": None,
            "venue": "arXiv",
        })
    return out


def main():
    seen, papers = set(), []
    for i, q in enumerate(QUERIES, 1):
        try:
            got = fetch(q)
            new = [p for p in got if p["paper_id"] not in seen and len(p["abstract"]) > 200]
            for p in new:
                seen.add(p["paper_id"])
                p["seed_query"] = q
            papers.extend(new)
            print(f"[{i}/{len(QUERIES)}] {q!r}: +{len(new)} (total {len(papers)})", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}/{len(QUERIES)}] {q!r}: FAILED {exc}", flush=True)
        time.sleep(3)  # arXiv rate-limit courtesy window

    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d"), "papers": papers}, f,
                  ensure_ascii=False, indent=1)
    print(f"\nSaved {len(papers)} papers -> {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
