"""Citation export: BibTeX, RIS and plain-text citation strings."""
from __future__ import annotations

import re


def _surname(author: str) -> str:
    parts = [p for p in re.split(r"\s+", (author or "").strip()) if p]
    return parts[-1] if parts else "anon"


def _key(paper: dict) -> str:
    authors = paper.get("authors") or []
    surname = _surname(authors[0]) if authors else "anon"
    year = paper.get("year") or "n.d."
    word = re.sub(r"[^A-Za-z0-9]", "", (paper.get("title") or "paper").split()[0] if paper.get("title") else "paper")
    return f"{surname.lower()}{year}{word.lower()}"[:40]


def _escape(text: str) -> str:
    return (text or "").replace("{", "\\{").replace("}", "\\}").replace("&", "\\&")


def to_bibtex(paper: dict) -> str:
    authors = " and ".join(paper.get("authors") or []) or "Unknown"
    arxiv_id = (paper.get("paper_id") or "").replace("arxiv:", "")
    is_preprint = paper.get("source") == "arxiv" or not paper.get("venue")
    fields = [
        ("title", _escape(paper.get("title", ""))),
        ("author", _escape(authors)),
        ("year", str(paper.get("year") or "")),
    ]
    if paper.get("venue"):
        fields.append(("journal" if not is_preprint else "howpublished", _escape(paper["venue"])))
    if paper.get("url"):
        fields.append(("url", paper["url"]))
    if paper.get("citation_count"):
        fields.append(("note", f"Cited {paper['citation_count']} times"))
    if arxiv_id and is_preprint:
        fields.append(("eprint", arxiv_id))
        fields.append(("archivePrefix", "arXiv"))

    entry = "misc" if is_preprint else "article"
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields if value)
    return f"@{entry}{{{_key(paper)},\n{body}\n}}\n"


def to_ris(paper: dict) -> str:
    lines = ["TY  - GEN" if paper.get("source") == "arxiv" else "TY  - JOUR"]
    lines.append(f"TI  - {paper.get('title', '')}")
    for author in paper.get("authors") or []:
        lines.append(f"AU  - {author}")
    if paper.get("year"):
        lines.append(f"PY  - {paper['year']}")
    if paper.get("venue"):
        lines.append(f"JO  - {paper['venue']}")
    if paper.get("abstract"):
        lines.append(f"AB  - {paper['abstract'][:1200]}")
    if paper.get("url"):
        lines.append(f"UR  - {paper['url']}")
    if paper.get("pdf_url"):
        lines.append(f"L1  - {paper['pdf_url']}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def to_apa(paper: dict) -> str:
    authors = paper.get("authors") or []
    if not authors:
        names = "Unknown"
    elif len(authors) == 1:
        names = authors[0]
    elif len(authors) <= 3:
        names = ", ".join(authors[:-1]) + " & " + authors[-1]
    else:
        names = authors[0] + " et al."
    year = paper.get("year") or "n.d."
    title = paper.get("title", "")
    venue = paper.get("venue") or "arXiv preprint"
    url = paper.get("url") or ""
    tail = f" {url}" if url else ""
    return f"{names} ({year}). {title}. {venue}.{tail}"


def to_ieee(paper: dict) -> str:
    authors = paper.get("authors") or []
    names = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
    return (f"{names}, \"{paper.get('title', '')},\" {paper.get('venue') or 'arXiv preprint'}, "
            f"{paper.get('year') or 'n.d.'}. [Online]. Available: {paper.get('url', '')}")


def export(papers: list[dict], fmt: str = "bibtex") -> str:
    fmt = (fmt or "bibtex").lower()
    if fmt == "ris":
        return "\n".join(to_ris(p) for p in papers)
    if fmt in {"txt", "apa"}:
        return "\n\n".join(to_apa(p) for p in papers) + "\n"
    if fmt == "ieee":
        return "\n\n".join(to_ieee(p) for p in papers) + "\n"
    return "\n".join(to_bibtex(p) for p in papers)


MEDIA_TYPES = {
    "bibtex": "application/x-bibtex",
    "ris": "application/x-research-info-systems",
    "apa": "text/plain; charset=utf-8",
    "ieee": "text/plain; charset=utf-8",
}

EXTENSIONS = {"bibtex": "bib", "ris": "ris", "apa": "txt", "ieee": "txt"}
