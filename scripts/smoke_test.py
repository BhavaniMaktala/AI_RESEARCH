"""End-to-end HTTP + SSE smoke test (runs a real server in-process)."""
import json
import sys
import threading
import time

sys.path.insert(0, "/scratch/work/paperrec/backend")

import requests
from werkzeug.serving import make_server

from api import create_app
from config import config

config.PORT = 5055
app = create_app(config)
server = make_server("127.0.0.1", 5055, app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(1.0)

BASE = "http://127.0.0.1:5055"
ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label} {extra}")


r = requests.get(BASE + "/", timeout=10)
check("GET / serves index.html", r.status_code == 200 and "PaperRec" in r.text, f"({len(r.text)}B)")

for path in ("/css/style.css", "/js/app.js", "/js/api.js", "/js/graph.js", "/js/charts.js", "/assets/favicon.svg"):
    r = requests.get(BASE + path, timeout=10)
    check(f"static {path}", r.status_code == 200 and len(r.content) > 200, f"({len(r.content)}B)")

r = requests.get(BASE + "/api/health", timeout=15)
check("health", r.status_code == 200 and r.json()["status"] == "ok", json.dumps(r.json()["graph"]))

r = requests.get(BASE + "/api/config", timeout=15)
cfg = r.json()
check("config", r.status_code == 200 and cfg["index"]["papers_indexed"] > 100,
      f"papers={cfg['index']['papers_indexed']} emb={cfg['index']['embedding']['kind']}")

r = requests.get(BASE + "/api/agents", timeout=10)
check("agents registry", r.status_code == 200 and r.json()["count"] == 8)

# --- SSE stream ---------------------------------------------------------
t0 = time.time()
events = []
with requests.get(BASE + "/api/search/stream",
                  params={"q": "multi agent retrieval augmented generation for literature review", "top_k": 6},
                  stream=True, timeout=90) as resp:
    check("SSE status", resp.status_code == 200 and "text/event-stream" in resp.headers.get("Content-Type", ""))
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data: "):
            continue
        events.append(json.loads(raw[6:]))
        if events[-1].get("event") in {"done", "error"}:
            break

kinds = [e["event"] for e in events]
check("SSE emits 8 agent_start", kinds.count("agent_start") == 8, str({k: kinds.count(k) for k in set(kinds)}))
check("SSE emits 8 agent_end", kinds.count("agent_end") == 8)
check("SSE emits log lines", kinds.count("log") > 5, f"({kinds.count('log')} logs)")
check("SSE emits result", "result" in kinds)
result = next(e["data"] for e in events if e["event"] == "result")
check("results returned", len(result["results"]) == 6, f"({len(result['results'])})")
check("results have summaries", all(r["summary"].get("summary") for r in result["results"]))
check("results have explanations", all(r["explanation"].get("reasons") for r in result["results"]))
print(f"      stream completed in {time.time() - t0:.2f}s, {len(events)} events, "
      f"total_ms={result['total_ms']}")

# --- REST search, detail, library, feedback -----------------------------
r = requests.post(BASE + "/api/search", json={"query": "citation graph paper recommendation", "top_k": 5}, timeout=60)
d = r.json()
check("POST /api/search", r.status_code == 200 and len(d["results"]) == 5)
pid = d["results"][0]["paper"]["paper_id"]

r = requests.get(BASE + f"/api/papers/{pid}", params={"q": "citation graph"}, timeout=30)
det = r.json()
check("paper detail", r.status_code == 200 and det["summary"] and len(det["related"]) > 0,
      f"related={len(det['related'])} graph_nodes={len(det['graph']['nodes'])}")

r = requests.get(BASE + f"/api/papers/{pid}/graph", timeout=20)
check("paper subgraph", r.status_code == 200 and len(r.json()["nodes"]) > 1)

r = requests.get(BASE + "/api/graph/overview", params={"limit": 80}, timeout=30)
g = r.json()
check("graph overview", r.status_code == 200 and len(g["nodes"]) == 80 and len(g["edges"]) > 50,
      f"nodes={len(g['nodes'])} edges={len(g['edges'])} communities={g['communities']}")

sess = requests.Session()
sess.headers["X-Session-Id"] = "smoke-test-session"
r = sess.post(BASE + "/api/library", json={"paper_id": pid}, timeout=20)
check("library add", r.status_code == 200)
r = sess.get(BASE + "/api/library", timeout=20)
check("library list", r.json()["count"] == 1)
r = sess.post(BASE + "/api/feedback", json={"paper_id": pid, "action": "like"}, timeout=20)
check("feedback like", r.status_code == 200 and r.json()["learning"]["profile_updated"])
r = sess.delete(BASE + f"/api/library/{pid}", timeout=20)
check("library remove", sess.get(BASE + "/api/library", timeout=20).json()["count"] == 0)

r = requests.get(BASE + "/api/insights", timeout=30)
ins = r.json()
check("insights", r.status_code == 200 and ins["searches"] > 0 and ins["system"]["papers_indexed"] > 100,
      f"searches={ins['searches']} avg={ins['avg_latency_ms']}ms")

r = requests.get(BASE + "/api/suggest", params={"q": "retrieval"}, timeout=20)
check("suggest", r.status_code == 200 and len(r.json()["suggestions"]) > 0)
r = requests.get(BASE + "/api/trending", timeout=20)
check("trending", r.status_code == 200 and len(r.json()["papers"]) == 6)
r = requests.get(BASE + "/api/papers/does-not-exist", timeout=20)
check("404 for unknown paper", r.status_code == 404)

server.shutdown()
print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
