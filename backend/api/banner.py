"""Startup banner: shows the user exactly which backend is active."""
from __future__ import annotations


def summary(application) -> str:
    try:
        c = application.extensions["container"]
        index = c.index.stats()
        graph = c.graph.stats()
        lines = [
            f"  Papers        {index['papers_indexed']}",
            f"  Embeddings    {index['embedding']['name']}",
            f"  Vector index  {index['vector_backend']['backend']}",
            f"  Graph         {graph['backend']} ({graph['nodes']} nodes / {graph['edges']} edges)",
            f"  Database      {c.repo.kind}",
            f"  Summaries     {c.llm.info()['provider']}",
        ]
        tips = []
        if index["embedding"]["kind"] != "sentence-transformers":
            tips.append("pip install sentence-transformers   -> stronger semantic matching")
        if not c.llm.enabled:
            tips.append("LLM_PROVIDER + LLM_API_KEY in .env  -> LLM-written summaries")
        if tips:
            lines.append("")
            lines.extend(f"  Optional: {tip}" for tip in tips)
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 - a status line must never block startup
        return ""


def print_banner(application, config, server: str = "flask") -> None:
    print("\n" + "=" * 70)
    print("  PaperRec - AI Research Paper Recommendation System")
    print(f"  http://{config.HOST}:{config.PORT}      (server: {server})")
    print("-" * 70)
    print(summary(application))
    print("=" * 70)
    print("  Press CTRL+C to stop\n")
