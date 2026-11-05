# Architecture notes

## Request flow

1. The browser calls `GET /api/search/stream?q=…` (SSE) or `POST /api/search` (plain JSON).
2. `api/routes/search.py` validates input, resolves the anonymous session (`X-Session-Id` header or cookie)
   and hands the request to `SearchService`.
3. `SearchService.search()` creates a shared state dict (`agents/base.new_state`) and runs the orchestrator.
4. Each agent reads the state, writes a partial update and returns a short note. The orchestrator times it,
   appends a trace entry and emits an event (`agent_start`, `log`, `agent_end`, `agent_error`).
5. When all nodes finish, `SearchService._build_payload()` assembles results, trace, timings, weights,
   graph stats and metadata, then emits `result` and `done`.

A failing agent never aborts the pipeline: the error is recorded in `state["errors"]`, the step is marked
failed in the UI and downstream agents degrade to the signals they still have.

## Agent contracts

```python
class BaseAgent:
    key: str          # stable id used by the UI
    label: str        # display name
    description: str  # tooltip / registry text
    def run(self, state: dict, ctx: dict) -> AgentResult: ...
```

`ctx` carries the shared services: `index`, `sources`, `analyzer`, `config`, `repo`, `llm`, `session`,
plus `log(agent_key, message)` and `emit(event)` injected by the orchestrator.

## Service interfaces

| Service | Interface | Implementations |
|---|---|---|
| Embeddings | `fit`, `embed_documents`, `embed_query`, `info` | `SentenceTransformerEmbedder`, `TfidfSvdEmbedder` |
| Vector store | `build`, `search`, `info` | `FaissVectorStore`, `NumpyVectorStore` |
| Graph store | `upsert_paper`, `add_edge`, `neighbors`, `subgraph`, `analytics`, `stats` | `Neo4jGraphStore`, `NetworkXGraphStore` |
| Repository | `upsert_paper`, `get_paper`, `log_search`, `record_feedback`, `get_session`, `save_session`, library ops, `insights` | `SQLiteRepository`, `MongoRepository` |

Factories (`build_embedder`, `build_vector_store`, `build_graph_store`, `build_repository`) probe the
environment once at start-up and log the chosen backend; `/api/config` reports it to the UI.

## Index lifecycle

`PaperIndex.build(papers)` is the single write path:

1. store every paper in the repository (idempotent upsert),
2. fit the text analyser (TF-IDF keyphrases) and the embedder on the corpus,
3. embed all documents and rebuild the vector index and the BM25 index,
4. upsert graph nodes and add k-nearest-neighbour similarity edges (k = 6, weight = cosine),
5. invalidate cached analytics.

Live papers are embedded per request and persisted by the Learning agent, so the index grows with use.

## Scoring

```
score(d) = 0.52·semantic + 0.14·influence + 0.12·citation + 0.12·recency + 0.10·personal
```

Weights are renormalised after any adjustment (intent bias, learned feedback) and returned with every
response, so the UI can always show the exact ranking function that produced the list. The top
`4 × top_k` candidates are then re-selected with MMR (λ = 0.75) for diversity.
