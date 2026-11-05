"""Classical NLP helpers: query understanding, keyword extraction,
extractive summarisation and contribution mining.

These are deliberately deterministic (no LLM required) so the platform works
offline; an LLM, when configured, only polishes the output.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = set("""
a about above after again against all am an and any are aren as at be because been before being
below between both but by can cannot could couldn did didn do does doesn doing don down during each
few for from further had hadn has hasn have haven having he her here hers herself him himself his
how i if in into is isn it its itself just me more most mustn my myself no nor not now of off on
once only or other ought our ours ourselves out over own same shan she should shouldn so some such
than that the their theirs them themselves then there these they this those through to too under
until up very was wasn we were weren what when where which while who whom why will with won would
wouldn you your yours yourself yourselves also using used use based paper work results approach
method methods show shows proposed propose new two three one many however thus therefore may can
""".split())

_ACRONYMS = {
    "llm": "large language model", "llms": "large language models",
    "rag": "retrieval augmented generation", "gnn": "graph neural network",
    "gnns": "graph neural networks", "kg": "knowledge graph", "kgs": "knowledge graphs",
    "nlp": "natural language processing", "ir": "information retrieval",
    "recsys": "recommender system", "xai": "explainable artificial intelligence",
    "sota": "state of the art", "ann": "approximate nearest neighbor",
    "nl": "natural language", "ml": "machine learning", "ai": "artificial intelligence",
    "marl": "multi agent reinforcement learning", "cot": "chain of thought",
    "ltr": "learning to rank", "mml": "multimodal learning",
}

_SYNONYMS = {
    "recommendation": ["recommender", "ranking", "personalisation", "personalization"],
    "recommender": ["recommendation", "ranking"],
    "summarization": ["summarisation", "abstractive summary", "text summarization"],
    "retrieval": ["search", "ranking", "dense retrieval", "information retrieval"],
    "citation": ["bibliographic", "reference", "scholarly"],
    "graph": ["network", "knowledge graph", "graph neural"],
    "explainable": ["interpretable", "transparency", "explanation"],
    "multi-agent": ["multiagent", "agent", "orchestration"],
    "embedding": ["representation", "vector", "encoder"],
    "transformer": ["attention", "language model"],
    "survey": ["review", "overview", "systematic literature review"],
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?!et al\.)(?=[A-Z0-9(\[])")


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9\-]{1,}", (text or "").lower()) if t not in STOPWORDS]


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


class TextAnalyzer:
    """TF-IDF based keyword extraction fitted on the paper corpus."""

    def __init__(self) -> None:
        self._vectorizer = None
        self._terms: list[str] = []

    def fit(self, documents: list[str]) -> None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1,
                                  max_features=50000, sublinear_tf=True)
            vec.fit([d or " " for d in documents])
            self._vectorizer = vec
            self._terms = list(vec.get_feature_names_out())
        except Exception:  # noqa: BLE001
            self._vectorizer = None

    def keywords(self, text: str, k: int = 8) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        if self._vectorizer is not None:
            try:
                matrix = self._vectorizer.transform([text])
                row = matrix.toarray()[0]
                idx = row.argsort()[::-1]
                out: list[str] = []
                for i in idx:
                    if row[i] <= 0 or len(out) >= k:
                        break
                    term = self._terms[i]
                    if len(term) < 3 or term in STOPWORDS:
                        continue
                    if any(term in prev.split() or prev in term.split() for prev in out):
                        continue
                    out.append(term)
                if out:
                    return out
            except Exception:  # noqa: BLE001
                pass
        counts = Counter(tokenize(text))
        return [t for t, _ in counts.most_common(k)]

    def idf(self, term: str) -> float:
        if self._vectorizer is None:
            return 1.0
        vocab = self._vectorizer.vocabulary_
        if term in vocab:
            return float(self._vectorizer.idf_[vocab[term]])
        return math.log(1.0 + len(self._terms)) if self._terms else 1.0


def expand_query(query: str, analyzer: TextAnalyzer) -> dict:
    """Normalise, expand and classify a user query."""
    raw = (query or "").strip()
    lowered = raw.lower()

    # acronym expansion (both directions)
    expansions: dict[str, list[str]] = {}
    tokens = re.findall(r"[a-z][a-z0-9\-]+", lowered)
    for tok in tokens:
        if tok in _ACRONYMS:
            expansions[tok] = [t for t in _ACRONYMS[tok].split() if t not in STOPWORDS]
    for short, long_form in _ACRONYMS.items():
        if long_form in lowered and short not in tokens:
            expansions[short] = [w for w in long_form.split() if w not in STOPWORDS]

    for tok in tokens:
        if tok in _SYNONYMS:
            expansions.setdefault(tok, []).extend(_SYNONYMS[tok][:3])

    expanded_terms: list[str] = []
    for tok, syns in expansions.items():
        expanded_terms.extend(s for s in syns if s not in lowered)

    expanded_text = " ".join([raw] + [" ".join(s) for s in expansions.values()]).strip()

    # filters
    year_from, year_to = None, None
    m = re.search(r"\b(?:after|since|from)\s+(19|20)\d{2}\b", lowered)
    if m:
        year_from = int(re.search(r"(19|20)\d{2}", m.group(0)).group(0))
    m = re.search(r"\b(19|20)\d{2}\s*(?:-|to|–)\s*((19|20)\d{2})\b", lowered)
    if m:
        year_from = int(m.group(1) + m.group(0)[2:4])
        year_to = int(m.group(2))
    m = re.search(r"\bbefore\s+((19|20)\d{2})\b", lowered)
    if m:
        year_to = int(m.group(1))

    # intent
    is_survey = bool(re.search(r"\b(survey|review|overview|state of the art|sota)\b", lowered))
    intent_type = "general"
    if is_survey:
        intent_type = "survey"
    elif re.search(r"\b(compare|comparison|versus|vs|benchmark)\b", lowered):
        intent_type = "comparison"
    elif re.search(r"\b(dataset|corpus|annotation)\b", lowered):
        intent_type = "dataset"
    elif re.search(r"\b(how|approach|architecture|framework|method|technique|algorithm)\b", lowered):
        intent_type = "method"

    recency_bias = 1.0
    if re.search(r"\b(latest|recent|new|cutting[- ]edge|sota|state of the art|2024|2025|2026)\b", lowered):
        recency_bias = 1.6
    if is_survey:
        recency_bias *= 0.9

    keywords = analyzer.keywords(expanded_text or raw, k=10)

    return {
        "raw": raw,
        "normalized": " ".join(raw.split()),
        "tokens": tokens,
        "keywords": keywords,
        "expansions": expansions,
        "expanded_text": expanded_text,
        "intent": {"type": intent_type, "is_survey": is_survey, "recency_bias": round(recency_bias, 3)},
        "filters": {"year_from": year_from, "year_to": year_to},
    }


_CONTRIB_PATTERNS = re.compile(
    r"\b(we (?:propose|present|introduce|develop|design|show|demonstrate|find)|"
    r"this (?:paper|work|study) (?:proposes|presents|introduces|studies)|"
    r"our (?:approach|method|framework|model|results|experiments))\b",
    re.IGNORECASE,
)


def extract_contributions(abstract: str, limit: int = 3) -> list[str]:
    out: list[str] = []
    for sent in split_sentences(abstract):
        if _CONTRIB_PATTERNS.search(sent):
            out.append(sent)
        if len(out) >= limit:
            break
    return out


def extractive_summary(abstract: str, focus_terms: list[str] | None = None,
                       max_sentences: int = 3, analyzer: TextAnalyzer | None = None) -> str:
    """Score sentences by query focus, position and informativeness."""
    sentences = split_sentences(abstract)
    if not sentences:
        return (abstract or "").strip()
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    focus = set()
    for term in (focus_terms or []):
        focus.update(tokenize(term))

    scored: list[tuple[float, int, str]] = []
    for i, sent in enumerate(sentences):
        toks = tokenize(sent)
        if not toks:
            continue
        overlap = len(focus & set(toks)) / (1 + len(focus)) if focus else 0.0
        weight = 0.0
        if analyzer is not None:
            weight = sum(analyzer.idf(t) for t in toks[:40]) / (len(toks) ** 0.5)
        position = 1.0 if i == 0 else (0.6 if i == 1 else 0.3)
        length_pen = 1.0 - abs(len(toks) - 22) / 60.0
        score = 2.0 * overlap + 0.35 * position + 0.25 * length_pen + 0.05 * weight
        scored.append((score, i, sent))

    scored.sort(key=lambda x: -x[0])
    chosen = sorted(scored[:max_sentences], key=lambda x: x[1])
    return " ".join(s for _, _, s in chosen)


def recency_score(year: int | None, current_year: int = 2026) -> float:
    if not year:
        return 0.4
    age = max(0, current_year - int(year))
    return float(math.exp(-age / 8.0))


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
