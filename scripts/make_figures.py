"""Generate every figure used in the project report."""
from __future__ import annotations

import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, "/scratch/work/paperrec/backend")

OUT = "/scratch/work/paperrec/docs/figures"
os.makedirs(OUT, exist_ok=True)

INDIGO = "#4f46e5"
CYAN = "#0891b2"
SLATE = "#334155"
LIGHT = "#eef2ff"
GREY = "#64748b"
GREEN = "#059669"
AMBER = "#d97706"
PALETTE = ["#4f46e5", "#0891b2", "#059669", "#d97706", "#db2777",
           "#7c3aed", "#dc2626", "#0ea5e9", "#65a30d", "#e11d48"]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.edgecolor": "#cbd5e1",
    "axes.labelcolor": SLATE,
    "text.color": SLATE,
    "xtick.color": GREY,
    "ytick.color": GREY,
})


def rounded(ax, x, y, w, h, face, edge, lw=1.0, radius=0.02):
    patch = mpatches.FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=face, edgecolor=edge, linewidth=lw, zorder=2,
    )
    ax.add_patch(patch)
    return patch


def label(ax, x, y, text, size=8.5, weight="normal", color=SLATE, ha="center", va="center"):
    ax.text(x, y, text, fontsize=size, fontweight=weight, color=color, ha=ha, va=va, zorder=3)


# ---------------------------------------------------------------- figure 1
def architecture():
    fig, ax = plt.subplots(figsize=(7.0, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    bands = [
        (8.55, 1.15, "Presentation layer", "#f8fafc"),
        (6.95, 1.25, "API layer - Flask REST + Server-Sent Events", "#f8fafc"),
        (5.15, 1.45, "Multi-agent orchestration layer", "#eef2ff"),
        (3.05, 1.75, "Intelligence services", "#f8fafc"),
        (1.05, 1.65, "Data and external sources", "#f8fafc"),
    ]
    for y, h, title, face in bands:
        rounded(ax, 0.25, y, 9.5, h, face, "#cbd5e1", lw=0.8)
        label(ax, 0.45, y + h - 0.16, title, size=8, weight="bold", color=GREY, ha="left")

    # presentation
    items = ["Discover / search", "Live agent trace", "Paper drawer", "Library", "Graph explorer", "Insights"]
    w = 9.5 / len(items) - 0.12
    for i, item in enumerate(items):
        x = 0.35 + i * (w + 0.12)
        rounded(ax, x, 8.65, w, 0.45, "#ffffff", INDIGO, lw=0.9)
        label(ax, x + w / 2, 8.87, item, size=7.2)

    # api
    api = ["/search", "/search/stream", "/papers/*", "/graph/*", "/library", "/insights"]
    w = 9.5 / len(api) - 0.12
    for i, item in enumerate(api):
        x = 0.35 + i * (w + 0.12)
        rounded(ax, x, 7.1, w, 0.5, "#ffffff", CYAN, lw=0.9)
        label(ax, x + w / 2, 7.35, item, size=6.8)

    # agents
    agents = ["Query\nUnderstanding", "Paper\nRetrieval", "Semantic\nAnalysis", "Citation\nGraph",
              "Recommend-\nation", "Summariz-\nation", "Explain-\nability", "Learning"]
    w = 9.5 / len(agents) - 0.1
    for i, item in enumerate(agents):
        x = 0.32 + i * (w + 0.1)
        face = "#e0e7ff" if i % 2 == 0 else "#dbeafe"
        rounded(ax, x, 5.35, w, 0.62, face, INDIGO, lw=1.0)
        label(ax, x + w / 2, 5.66, item, size=6.3, weight="bold")

    # services
    services = ["Embeddings\n(SBERT | TF-IDF)", "Vector index\n(FAISS | NumPy)",
                "BM25\nlexical index", "Graph\nanalytics", "Summarizer &\nexplainability",
                "LLM (optional)"]
    w = 9.5 / len(services) - 0.12
    for i, item in enumerate(services):
        x = 0.35 + i * (w + 0.12)
        rounded(ax, x, 3.2, w, 0.62, "#ffffff", "#94a3b8", lw=0.9)
        label(ax, x + w / 2, 3.51, item, size=6.7)

    # data
    data = ["SQLite /\nMongoDB", "FAISS /\nNumPy index", "Neo4j /\nNetworkX", "Semantic\nScholar API",
            "arXiv\nAPI", "Seed corpus\n(132 papers)"]
    w = 9.5 / len(data) - 0.12
    for i, item in enumerate(data):
        x = 0.35 + i * (w + 0.12)
        rounded(ax, x, 1.2, w, 0.6, "#f1f5f9", "#94a3b8", lw=0.9)
        label(ax, x + w / 2, 1.5, item, size=6.7)

    for y0, y1 in [(8.55, 8.2), (6.95, 6.6), (5.15, 4.8), (3.05, 2.7)]:
        ax.annotate("", xy=(5.0, y1), xytext=(5.0, y0),
                    arrowprops=dict(arrowstyle="-|>", color="#94a3b8", lw=1.1))
    ax.annotate("", xy=(5.0, 8.2), xytext=(5.0, 8.55),
                arrowprops=dict(arrowstyle="<|-|>", color="#94a3b8", lw=1.0))

    fig.tight_layout(pad=0.2)
    fig.savefig(f"{OUT}/fig_architecture.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- figure 2
def pipeline():
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.3)
    ax.axis("off")

    steps = [
        ("1. Query\nUnderstanding", "intent, acronyms,\nyear filters"),
        ("2. Paper\nRetrieval", "BM25 + dense +\nlive APIs"),
        ("3. Semantic\nAnalysis", "embeddings,\ncosine, concepts"),
        ("4. Citation\nGraph", "PageRank,\ncommunities"),
        ("5. Ranking", "5 signals\n+ MMR"),
        ("6. Summarization", "extractive,\nquery-focused"),
        ("7. Explainability", "reason list\nper paper"),
        ("8. Learning", "profile drift,\nweight tuning"),
    ]
    w, h, gap = 2.16, 1.0, 0.29
    x0 = 0.35
    positions = {}
    for i, (title, sub) in enumerate(steps):
        row, col = divmod(i, 4)
        x = x0 + col * (w + gap)
        y = 2.75 if row == 0 else 1.05
        positions[i] = (x, y)
        rounded(ax, x, y, w, h, "#eef2ff", INDIGO, lw=1.1, radius=0.04)
        label(ax, x + w / 2, y + h - 0.28, title, size=7.6, weight="bold", color="#312e81")
        label(ax, x + w / 2, y + 0.28, sub, size=6.3, color=GREY)
        if col < 3:
            ax.annotate("", xy=(x + w + gap - 0.02, y + h / 2), xytext=(x + w + 0.02, y + h / 2),
                        arrowprops=dict(arrowstyle="-|>", color=INDIGO, lw=1.1))

    # wrap arrow: end of row 1 -> start of row 2
    bx, by = positions[3]
    tx, ty = positions[4]
    mid_y = 2.32
    ax.plot([bx + w / 2, bx + w / 2], [by, mid_y], color=INDIGO, lw=1.1)
    ax.plot([bx + w / 2, tx + w / 2], [mid_y, mid_y], color=INDIGO, lw=1.1)
    ax.annotate("", xy=(tx + w / 2, ty + h + 0.01), xytext=(tx + w / 2, mid_y),
                arrowprops=dict(arrowstyle="-|>", color=INDIGO, lw=1.1))

    # feedback loop: learning (8) back to ranking (5)
    lx, ly = positions[7]
    rx, ry = positions[4]
    loop_y = 0.62
    ax.plot([lx + w / 2, lx + w / 2], [ly, loop_y], color=AMBER, lw=1.1, linestyle="--")
    ax.plot([lx + w / 2, rx + w / 2], [loop_y, loop_y], color=AMBER, lw=1.1, linestyle="--")
    ax.annotate("", xy=(rx + w / 2, ry - 0.01), xytext=(rx + w / 2, loop_y),
                arrowprops=dict(arrowstyle="-|>", color=AMBER, lw=1.1, linestyle="--"))
    ax.text((lx + rx) / 2 + w / 2, loop_y - 0.19,
            "feedback loop: interest profile + weight adaptation",
            fontsize=6.5, color=AMBER, ha="center")

    ax.text(5.0, 4.12, "Shared state flows through every node; each agent streams a start/end event to the browser over SSE.",
            fontsize=6.7, color=GREY, ha="center")
    fig.tight_layout(pad=0.2)
    fig.savefig(f"{OUT}/fig_pipeline.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- figure 3
def datamodel():
    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9)
    ax.axis("off")

    tables = {
        "search_log": (0.35, 5.6, ["id  PK", "session_id  FK", "query", "result_count", "latency_ms", "ts"]),
        "sessions": (3.55, 5.6, ["session_id  PK", "profile  BLOB", "weights  JSON", "created_at", "updated_at"]),
        "papers": (6.75, 5.6, ["paper_id  PK", "title, abstract", "authors  JSON", "year, venue",
                               "categories  JSON", "citation_count", "source, url, pdf_url"]),
        "feedback": (3.55, 1.5, ["id  PK", "session_id  FK", "paper_id  FK", "action, query", "ts"]),
        "library": (6.75, 1.5, ["id  PK", "session_id  FK", "paper_id  FK", "list_name", "ts"]),
    }
    for name, (x, y, fields) in tables.items():
        h = 0.42 + 0.32 * len(fields)
        rounded(ax, x, y, 2.9, h, "#ffffff", INDIGO, lw=1.0, radius=0.02)
        ax.add_patch(mpatches.Rectangle((x, y + h - 0.34), 2.9, 0.34, facecolor="#e0e7ff",
                                        edgecolor=INDIGO, lw=1.0, zorder=3))
        label(ax, x + 1.45, y + h - 0.17, name, size=8.2, weight="bold", color="#312e81")
        for i, f in enumerate(fields):
            label(ax, x + 0.14, y + h - 0.58 - i * 0.32, f, size=6.9, ha="left", color=SLATE)

    def arrow(x0, y0, x1, y1, text="", rad=0.0, tx=None, ty=None):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.0,
                                    connectionstyle=f"arc3,rad={rad}"))
        if text:
            ax.text(tx if tx is not None else (x0 + x1) / 2,
                    ty if ty is not None else (y0 + y1) / 2,
                    text, fontsize=6.4, color=GREY, ha="center", va="center")

    arrow(3.4, 7.0, 3.53, 7.0, "1 : N", tx=3.46, ty=7.95)
    arrow(5.0, 5.55, 5.0, 3.6, "1 : N", tx=5.28, ty=4.55)
    arrow(6.95, 5.55, 6.35, 3.62, "N : 1", rad=0.12, tx=7.15, ty=4.35)
    arrow(8.2, 5.55, 8.2, 3.6, "N : 1", tx=8.48, ty=4.55)

    ax.text(5.0, 0.72, "The vector index (FAISS / NumPy) and the graph store (Neo4j / NetworkX) are derived\n"
                       "views rebuilt from papers at start-up - they are never the source of truth.",
            fontsize=6.8, color=GREY, ha="center")
    fig.tight_layout(pad=0.2)
    fig.savefig(f"{OUT}/fig_datamodel.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- figure 4
def latency_by_agent(bench):
    data = bench["agent_latency_ms"]
    order = ["query_understanding", "retrieval", "semantic", "citation", "ranking",
             "summarization", "explainability", "learning"]
    names = ["Query\nunderstanding", "Retrieval", "Semantic", "Citation graph", "Ranking",
             "Summarization", "Explainability", "Learning"]
    means = [data[k]["mean"] for k in order]
    maxes = [data[k]["max"] for k in order]

    fig, ax = plt.subplots(figsize=(7.0, 3.1))
    y = np.arange(len(names))
    ax.barh(y, means, color=INDIGO, height=0.55, label="mean")
    ax.barh(y, maxes, color=INDIGO, alpha=0.18, height=0.55, label="worst case")
    for i, (m, mx) in enumerate(zip(means, maxes)):
        ax.text(mx + 1.2, i, f"{m:.1f} ms", va="center", fontsize=7.5, color=SLATE)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Latency per agent (ms)")
    ax.set_xlim(0, max(maxes) * 1.28)
    ax.grid(axis="x", color="#e2e8f0", lw=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False, fontsize=7.5, loc="lower right")
    fig.tight_layout(pad=0.3)
    fig.savefig(f"{OUT}/fig_latency_agents.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- figure 5
def latency_per_query(bench):
    rows = bench["per_query"]
    labels = [r["query"][:34] + ("…" if len(r["query"]) > 34 else "") for r in rows]
    values = [r["latency_ms"] for r in rows]

    fig, ax = plt.subplots(figsize=(7.0, 3.3))
    y = np.arange(len(labels))
    colors = [CYAN if v < 150 else AMBER for v in values]
    ax.barh(y, values, color=colors, height=0.6)
    for i, v in enumerate(values):
        ax.text(v + 4, i, f"{v:.0f}", va="center", fontsize=7, color=SLATE)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.2)
    ax.invert_yaxis()
    ax.set_xlabel("End-to-end pipeline latency (ms)")
    ax.grid(axis="x", color="#e2e8f0", lw=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.text(0.99, 0.03, "amber = first request (cold graph analytics)",
            transform=ax.transAxes, fontsize=6.6, color=GREY, ha="right")
    fig.tight_layout(pad=0.3)
    fig.savefig(f"{OUT}/fig_latency_queries.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- figure 6
def graph_view():
    from api import create_app
    from config import config

    app = create_app(config)
    index = app.extensions["container"].index
    g = index.graph.graph
    analytics = index.analytics()

    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    pos = nx.spring_layout(g, seed=11, k=0.42, iterations=140, weight="weight")
    communities = analytics["community"]
    groups: dict[int, list] = {}
    for node in g.nodes():
        groups.setdefault(communities.get(node, 0), []).append(node)

    for cid, nodes in groups.items():
        nx.draw_networkx_nodes(g, pos, nodelist=nodes, node_size=26,
                               node_color=PALETTE[cid % len(PALETTE)], ax=ax, linewidths=0)
    nx.draw_networkx_edges(g, pos, alpha=0.16, width=0.55, edge_color="#64748b", ax=ax)

    handles = []
    for cid in sorted(groups):
        label_text = analytics["community_labels"].get(cid, f"cluster {cid + 1}")
        handles.append(mpatches.Patch(color=PALETTE[cid % len(PALETTE)],
                                      label=label_text[:44] + ("…" if len(label_text) > 44 else "")))
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.20), ncol=2,
              fontsize=6.2, frameon=False, handlelength=1.0, columnspacing=1.2)

    ax.set_axis_off()
    ax.set_title(f"Similarity graph of the bundled corpus - {g.number_of_nodes()} papers, "
                 f"{g.number_of_edges()} edges, {analytics['communities']} communities",
                 fontsize=8.4, color=SLATE, pad=6)
    fig.tight_layout(pad=0.2)
    fig.savefig(f"{OUT}/fig_graph.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    with open("/scratch/work/paperrec/docs/benchmark.json", encoding="utf-8") as fh:
        bench = json.load(fh)
    architecture()
    pipeline()
    datamodel()
    latency_by_agent(bench)
    latency_per_query(bench)
    graph_view()
    print("figures written to", OUT)
    for name in sorted(os.listdir(OUT)):
        print(" ", name, os.path.getsize(os.path.join(OUT, name)) // 1024, "KB")
