# PaperRec — AI Research Paper Recommendation System

**Multi-agent research discovery platform.** Eight specialist AI agents understand a research
question, retrieve candidate papers from Semantic Scholar / arXiv / a bundled corpus, score them
semantically, measure their position in a citation-similarity graph, rank and diversify them, summarise
them, and explain every recommendation — streaming the whole process to the browser in real time.

Team No. 4 · Domain: AI & ML with NLP and Multi-Agent AI

---

## Highlights

- **8-agent pipeline** — query understanding, retrieval, semantic analysis, citation-graph intelligence,
  ranking, summarisation, explainability, continuous learning.
- **Hybrid retrieval** — BM25 + dense vector search + live academic APIs, de-duplicated by title.
- **Graph intelligence** — PageRank influence, modularity-based communities, interdisciplinary bridge
  scores, interactive force-directed explorer.
- **Explainable by construction** — the ranking score is a transparent weighted sum of five named
  signals, so explanations are read-outs, not guesses.
- **Real-time UI** — Server-Sent Events stream each agent's start/end/log events into a live stepper.
- **Runs anywhere** — every external dependency is optional and degrades gracefully. No API key, no
  database server, no internet connection required.

| Dependency | Preferred | Automatic fallback |
|---|---|---|
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, 384-d) | TF-IDF + Truncated SVD |
| Vector index | FAISS `IndexFlatIP` | NumPy matrix (exact cosine) |
| Graph store | Neo4j | in-process NetworkX |
| Database | MongoDB | SQLite (zero setup) |
| Paper sources | Semantic Scholar + arXiv | bundled 132-paper arXiv corpus |
| Summaries | Gemini / OpenAI / Groq | deterministic extractive NLG |

---

## Quick start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:7000** — the Flask process serves both the API and the interface.

The first start fits the embedding model and builds the index (a few seconds). Later starts reuse the
papers stored in SQLite.

### Production server (optional)

`python app.py` runs the Flask development server — perfect for a demo. For a
real deployment use Waitress (pure Python, works on Windows):

```bash
pip install waitress
python serve.py          # prints "server: waitress x8"
```

### Optional upgrades

```bash
# Real transformer embeddings (best quality). On Windows without an NVIDIA GPU:
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers

pip install faiss-cpu               # faster vector index
pip install neo4j                   # persistent graph database (set NEO4J_URI + NEO4J_PASSWORD)
pip install pymongo                 # MongoDB instead of SQLite (set MONGO_URI)
cp .env.example .env                # then edit: S2_API_KEY, LLM_PROVIDER, weights, ...
```

An LLM key only changes the *wording* of summaries and explanations. Every feature works without one.

---

## What you can do in the UI

| View | What it does |
|---|---|
| **Discover** | Ask a question in plain English. Browse ranked cards with summaries, "why this paper" chips and a match score. A personalised feed and recent searches greet you on arrival. |
| **Paper drawer** | Full explanation, key contributions, concepts, graph metrics, neighbourhood graph, related papers, per-paper **notes**, and citation export (BibTeX / RIS / APA). |
| **Compare** | Select up to four papers and view them side by side. |
| **Command palette** | `Ctrl/⌘ + K` — jump to any view, rerun a recent query, toggle the theme, export the library. |
| **Library** | Saved papers grouped into reading lists, exportable as BibTeX or RIS. |
| **Citation Graph** | Whole-corpus force-directed network — node size = PageRank influence, colour = community. Click any node to inspect the paper. |
| **Insights** | Searches, latency trend, feedback mix, top queries, corpus composition, and which backend each component is actually using. |
| **Themes** | Light, dark or follow the system — applied before first paint, remembered per browser. |
| **Agent activity** | Off by default. Switch it on in Settings to watch all eight agents run in real time (handy for a demo). |

Shareable search links: `/?q=retrieval+augmented+generation`.

---

## Architecture

```
Browser (HTML/CSS/JS, no framework, no CDN)
   │  fetch + EventSource
   ▼
Flask API  ── /api/search · /api/search/stream (SSE) · /api/papers/* · /api/graph/* · /api/library · /api/insights
   ▼
Agent orchestrator (state graph, per-node events, failure isolation)
   1 Query Understanding → 2 Retrieval → 3 Semantic → 4 Citation Graph
   → 5 Ranking → 6 Summarisation → 7 Explainability → 8 Learning ─┐
   ▲                                                               │
   └──────────────── profile + weight feedback ────────────────────┘
   ▼
Services: embeddings · vector store · BM25 · graph analytics · repository · paper sources · LLM
   ▼
Data: SQLite/MongoDB · FAISS/NumPy · Neo4j/NetworkX · Semantic Scholar · arXiv · seed corpus
```

More detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + active backends |
| GET | `/api/config` | Full capability report |
| GET | `/api/agents` | Agent registry |
| POST | `/api/search` | Run the pipeline, return the full payload |
| GET | `/api/search/stream?q=…` | Same pipeline as Server-Sent Events |
| GET | `/api/papers/{id}` | Detail, summary, related, subgraph |
| GET | `/api/papers/{id}/graph` | Neighbourhood subgraph |
| POST | `/api/papers/{id}/summary` | Deep (LLM) summary |
| GET | `/api/graph/overview` | Whole-corpus graph |
| GET | `/api/library` · POST · DELETE | Reading lists |
| POST | `/api/feedback` | `like` / `save` / `dismiss` / `open` |
| GET | `/api/insights` | Usage + latency analytics |
| GET | `/api/suggest?q=` | Type-ahead suggestions |
| GET | `/api/for-you` | Personalised feed from the interest profile |
| GET / DELETE | `/api/history` | Recent queries for the session |
| GET | `/api/papers/{id}/cite?style=` | APA / IEEE / BibTeX / RIS citation string |
| GET | `/api/papers/{id}/export?format=` | Download one paper as `.bib` or `.ris` |
| GET / PUT / DELETE | `/api/papers/{id}/note` | Per-paper notes |
| GET | `/api/library/export?format=` | Download the whole library |

Example:

```bash
curl -X POST http://127.0.0.1:7000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"multi-agent LLM systems for literature review","top_k":5}'
```

---

## Project layout

```
backend/
  app.py                  entrypoint
  config.py               env-driven configuration (everything optional)
  api/                    app factory, service container, blueprints
    routes/               health, search, papers, graph, library, feedback, insights
  agents/                 one module per agent + orchestrator + shared state
  services/               embeddings, vectorstore, lexical, graphstore, repository,
                          papersources, nlp, llm, index, search_service
  data/seed_corpus.json   132 real arXiv papers (offline dataset)
  tests/                  pytest unit tests
frontend/
  index.html · css/style.css (light + dark tokens)
  js/{api,theme,graph,charts,app}.js
scripts/
  fetch_seed.py           re-harvest the arXiv corpus
  benchmark.py            run the evaluation → docs/benchmark.json
  make_figures.py         regenerate report figures
  smoke_test.py           30 end-to-end HTTP + SSE checks
docs/
  ARCHITECTURE.md · benchmark.json · figures/
```

---

## Testing

```bash
cd backend && pytest -q          # 13 unit tests (nlp, BM25, embeddings, repository, notes, citation, graph, orchestrator)
python scripts/smoke_test.py     # 30 end-to-end checks incl. the SSE stream
python scripts/benchmark.py      # 12-query latency/diversity benchmark
```

Measured on the reference machine (offline config, 132 papers, top_k = 10):

| Metric | Value |
|---|---|
| End-to-end latency | mean **95.6 ms**, median 70.1 ms, p95 351 ms (cold first request) |
| Graph | 132 nodes, 531 edges, 9 communities, modularity **0.677** |
| Hybrid behaviour | 83.3 % of the final top-10 also in the BM25 top-20 |
| Unit / integration | 13 / 13 passing · 30 / 30 passing |

---

## Deploying to Render / Railway / Fly

The app binds to `127.0.0.1` locally but automatically switches to `0.0.0.0` whenever the
platform provides a `PORT` variable — that is what makes a container deploy reachable.

**Render (git repo):**

| Setting | Value |
|---|---|
| Runtime | Python 3 |
| Build command | `pip install -r backend/requirements.txt` |
| Start command | `python backend/serve.py` |
| Health check path | `/api/health` |
| Root directory | *(leave blank — the repo root)* |

Or just commit the included `render.yaml` and Render configures itself.

Two things that catch people out:

- If the log says `Running on http://127.0.0.1:<port>`, the app is on loopback and the
  platform's port scan will fail with *"No open ports detected on 0.0.0.0"*. Fix: make sure
  the `HOST` variable is either unset (auto-detection handles it) or set to `0.0.0.0`.
- Render's free tier has an ephemeral disk, so the SQLite file resets on every deploy. That is
  harmless here — the 132-paper corpus ships in the repository and is reloaded on boot. For
  durable reading lists and notes, attach a persistent disk or point `MONGO_URI` at Atlas.

## Configuration

Everything lives in `backend/.env` (see `backend/.env.example`). The most useful knobs:

| Variable | Default | Effect |
|---|---|---|
| `ONLINE_MODE` | `auto` | `auto` probes the network, `on` always uses live APIs, `off` is corpus-only |
| `EMBEDDING_PROVIDER` | `auto` | `auto` \| `sentence-transformers` \| `tfidf` |
| `VECTOR_BACKEND` | `auto` | `auto` \| `faiss` \| `numpy` |
| `S2_API_KEY` | – | Raises Semantic Scholar rate limits |
| `LLM_PROVIDER` / `LLM_API_KEY` | `none` | `gemini` \| `openai` \| `groq` |
| `TOP_K` / `CANDIDATE_LIMIT` | `12` / `120` | Result count and candidate pool |
| `MMR_LAMBDA` | `0.75` | Relevance ↔ diversity trade-off |
| `W_SEMANTIC … W_PERSONAL` | `0.52 … 0.10` | Ranking weights (renormalised at runtime) |

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Could not load library with AVX2 support … faiss.swigfaiss_avx2` | Harmless. FAISS probes for an AVX2 build, does not find one, and loads the standard build on the next line. Now silenced in the log. |
| `sentence-transformers not installed` | Optional package missing, so TF-IDF + SVD is used. Install it for stronger semantic matching. |
| `LLM: deterministic fallback` | No LLM key configured — summaries are extractive instead of LLM-written. Optional. |
| `WARNING: This is a development server` | You ran `app.py`. Use `python serve.py` (Waitress) for a production server. |
| First search takes ~350 ms | Graph analytics are computed and cached on the first request. |
| Port 7000 busy | set `PORT=7001` in `backend/.env`. |
| Empty results | Try a broader query, or reset the year / citation filters. |

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl/⌘ + K` | Command palette |
| `/` | Focus the search box |
| `t` | Toggle light / dark |
| `Esc` | Close palette, drawer or settings |

## License

Academic project — free to use and extend for coursework and research.
