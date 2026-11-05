/* =====================================================================
   PaperRec application controller
   ===================================================================== */
(() => {
  "use strict";

  /* ------------------------------- helpers ------------------------------ */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const nf = new Intl.NumberFormat("en-IN");
  const fmt = (n) => nf.format(Number(n) || 0);
  const clamp01 = (n) => Math.max(0, Math.min(1, Number(n) || 0));
  const short = (text, max) => {
    const value = String(text || "");
    return value.length > max ? value.slice(0, max - 1) + "…" : value;
  };

  const ICON = {
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 4h11l3 3v13H5z"/></svg>',
    graph: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="8" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.2 7.2 15.6 8M7.4 8.3l3.6 7.6"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 19V9M10 19V5M16 19v-7"/></svg>',
    moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8Z"/></svg>',
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2"/></svg>',
    download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 4v10M8 11l4 4 4-4M5 19h14"/></svg>',
    compare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h7v12H4zM13 6h7v12h-7z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>',
    sparkle: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/></svg>',
  };

  function toast(message, kind = "ok") {
    const stack = $("#toasts");
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.transition = "opacity .3s ease, transform .3s ease";
      el.style.opacity = "0";
      el.style.transform = "translateY(8px)";
      setTimeout(() => el.remove(), 320);
    }, 3000);
  }

  function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  }

  /* -------------------------------- state ------------------------------- */
  const state = {
    view: "search",
    agents: [],
    payload: null,
    results: [],
    sort: "score",
    query: "",
    saved: new Set(),
    liked: new Set(),
    dismissed: new Set(),
    compare: new Map(),
    graphData: null,
    graphView: null,
    drawerGraph: null,
    currentPaper: null,
    searching: false,
    config: null,
  };

  const VIEW_COPY = {
    search: ["Discover", "Ask anything. Get ranked, summarised and explained papers."],
    library: ["Library", "Saved papers, notes and citations."],
    graph: ["Citation graph", "Explore how papers connect."],
    insights: ["Insights", "Usage, quality and system health."],
    compare: ["Compare", "Side-by-side view of selected papers."],
  };

  /* --------------------------------- boot -------------------------------- */
  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    bindNav();
    bindSearch();
    bindFilters();
    bindDrawer();
    bindSettings();
    bindPalette();
    bindCompare();
    renderCompareTray();
    bindMisc();
    syncThemeUI();

    await Promise.allSettled([loadConfig(), loadAgents(), loadLibrary(), loadHistory(), loadFeed()]);

    const hash = location.hash.replace("#", "");
    if (["search", "library", "graph", "insights", "compare"].includes(hash)) switchView(hash, false);

    const initialQuery = new URLSearchParams(location.search).get("q");
    if (initialQuery) {
      $("#queryInput").value = initialQuery;
      runSearch(initialQuery.trim());
    }
  }

  /* ------------------------------ navigation ---------------------------- */
  function bindNav() {
    $$(".nav-item[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => switchView(btn.dataset.view));
    });
    $("#menuBtn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
    $("#newSearchBtn").addEventListener("click", () => {
      switchView("search");
      $("#queryInput").focus();
      $("#queryInput").select();
    });
  }

  function switchView(view, updateHash = true) {
    state.view = view;
    $$(".nav-item[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
    const [title, subtitle] = VIEW_COPY[view] || VIEW_COPY.search;
    $("#viewTitle").textContent = title;
    $("#viewSubtitle").textContent = subtitle;
    if (updateHash) history.replaceState(null, "", "#" + view);
    $("#sidebar").classList.remove("open");

    if (view === "library") loadLibrary();
    if (view === "graph") loadGraph();
    if (view === "insights") loadInsights();
    if (view === "compare") renderCompare();
  }

  /* ------------------------------- config ------------------------------- */
  async function loadConfig() {
    try {
      const cfg = await API.get("/api/config");
      state.config = cfg;
      const index = cfg.index || {};
      const graph = cfg.graph || {};
      const rows = [
        ["Papers indexed", fmt(index.papers_indexed)],
        ["Embeddings", (index.embedding && index.embedding.name) || "—"],
        ["Vector index", (index.vector_backend && index.vector_backend.backend) || "—"],
        ["Graph", `${graph.nodes || 0} nodes · ${graph.edges || 0} edges`],
        ["Database", (cfg.database && cfg.database.backend) || "—"],
        ["Summaries", (cfg.llm && cfg.llm.provider) || "template"],
      ];
      $("#sysList").innerHTML = rows
        .map(([k, v]) => `<dt>${esc(k)}</dt><dd title="${esc(v)}">${esc(v)}</dd>`)
        .join("");
    } catch (err) {
      $("#sysList").innerHTML = `<dt>Status</dt><dd>unreachable</dd>`;
    }
  }

  async function loadAgents() {
    try {
      const data = await API.get("/api/agents");
      state.agents = data.agents || [];
      renderPipelineSkeleton();
    } catch (err) { state.agents = []; }
  }

  /* -------------------------------- search ------------------------------ */
  function bindSearch() {
    $("#searchForm").addEventListener("submit", (e) => {
      e.preventDefault();
      runSearch($("#queryInput").value.trim());
    });

    $$("#exampleRow .pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        $("#queryInput").value = pill.dataset.q;
        runSearch(pill.dataset.q);
      });
    });

    const input = $("#queryInput");
    const suggest = debounce(async (value) => {
      const panel = $("#suggestPanel");
      if (value.length < 3) { panel.hidden = true; return; }
      try {
        const data = await API.get("/api/suggest", { q: value });
        const items = data.suggestions || [];
        if (!items.length) { panel.hidden = true; return; }
        panel.innerHTML = items.map((s) => `<button type="button" class="suggest-item" data-q="${esc(s.title)}">
            <span>${esc(s.title)}</span><em>${esc(s.year || "")}</em></button>`).join("");
        panel.hidden = false;
        $$(".suggest-item", panel).forEach((btn) => {
          btn.addEventListener("click", () => {
            input.value = btn.dataset.q;
            panel.hidden = true;
            runSearch(btn.dataset.q);
          });
        });
      } catch (err) { panel.hidden = true; }
    }, 260);

    input.addEventListener("input", (e) => suggest(e.target.value));
    input.addEventListener("blur", () => setTimeout(() => { $("#suggestPanel").hidden = true; }, 180));

    $("#rankingInfo").addEventListener("click", () => {
      const legend = $("#whyLegend");
      legend.hidden = !legend.hidden;
    });
  }

  function bindFilters() {
    $("#clearFilters").addEventListener("click", () => {
      $("#yearFrom").value = ""; $("#yearTo").value = ""; $("#minCitations").value = "";
      $("#topK").value = String(Prefs.get("topK") || 12);
      toast("Filters reset");
    });
    $("#sortSelect").addEventListener("change", (e) => { state.sort = e.target.value; renderCards(); });
  }

  function readFilters() {
    return {
      year_from: $("#yearFrom").value || null,
      year_to: $("#yearTo").value || null,
      min_citations: $("#minCitations").value || null,
    };
  }

  function renderPipelineSkeleton() {
    if (!state.agents.length) return;
    $("#pipeline").innerHTML = state.agents.map((a) => `
      <li class="step" data-agent="${esc(a.key)}" title="${esc(a.description)}">
        <div class="step-top"><span class="step-dot"></span><span class="step-label">${esc(a.label)}</span></div>
        <div class="step-ms">idle</div>
      </li>`).join("");
  }

  function resetPipeline() {
    $$("#pipeline .step").forEach((li) => {
      li.classList.remove("running", "done", "error");
      $(".step-ms", li).textContent = "idle";
    });
    $("#console").innerHTML = "";
  }

  async function runSearch(query) {
    if (!query) { toast("Type a research question first", "err"); return; }
    if (state.searching) return;
    state.searching = true;
    state.query = query;
    $("#suggestPanel").hidden = true;
    history.replaceState(null, "", "?q=" + encodeURIComponent(query) + "#" + state.view);

    const button = $("#searchBtn");
    button.disabled = true;
    button.querySelector("span").textContent = "Searching…";

    $("#discover").hidden = true;
    $("#resultsHead").hidden = true;
    $("#results").innerHTML = skeletonCards(3);

    const showAgents = Prefs.get("agentPanel");
    $("#agentPanel").hidden = !showAgents;
    if (showAgents) { resetPipeline(); $("#agentMeta").textContent = "running…"; }

    const filters = readFilters();
    const topK = Number($("#topK").value) || 12;
    const startedAt = performance.now();
    let usedStream = false;

    // ?stream=0 forces the non-streaming path (used by automated screenshots
    // and by browsers/proxies that buffer Server-Sent Events)
    if (new URLSearchParams(location.search).get("stream") === "0") {
      runSearchFallback(query, filters, topK);
      return;
    }

    API.streamSearch(query, filters, topK, {
      onEvent: (event) => { usedStream = true; handleStreamEvent(event); },
      onFallback: () => runSearchFallback(query, filters, topK, startedAt),
      onError: () => { if (!usedStream) runSearchFallback(query, filters, topK, startedAt); },
    });
  }

  function handleStreamEvent(event) {
    switch (event.event) {
      case "agent_start": {
        const step = $(`#pipeline .step[data-agent="${event.agent}"]`);
        if (step) {
          step.classList.add("running");
          step.classList.remove("done", "error");
          $(".step-ms", step).textContent = "…";
        }
        break;
      }
      case "agent_end": {
        const step = $(`#pipeline .step[data-agent="${event.agent}"]`);
        if (step) {
          step.classList.remove("running");
          step.classList.add(event.status === "error" ? "error" : "done");
          $(".step-ms", step).textContent = `${Math.round(event.ms)} ms`;
          step.title = event.note || "";
        }
        break;
      }
      case "agent_error": {
        const step = $(`#pipeline .step[data-agent="${event.agent}"]`);
        if (step) { step.classList.remove("running"); step.classList.add("error"); }
        appendConsole(event.agent, event.message || "failed");
        break;
      }
      case "log":
        appendConsole(event.agent, event.message);
        break;
      case "result":
        state.payload = event.data;
        finishSearch(event.data.total_ms);
        renderResults(event.data);
        break;
      case "done":
        finishSearch(event.total_ms);
        break;
      case "error":
        toast(event.message || "Search failed", "err");
        finishSearch(null, true);
        break;
      default: break;
    }
  }

  function appendConsole(agent, message) {
    const box = $("#console");
    if (!box) return;
    const label = (state.agents.find((a) => a.key === agent) || {}).label || agent;
    const line = document.createElement("div");
    line.className = "console-line";
    line.innerHTML = `<span class="t">${new Date().toLocaleTimeString("en-GB", { hour12: false })}</span>
      <span class="a">${esc(label)}</span><span>${esc(message)}</span>`;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
  }

  async function runSearchFallback(query, filters, topK) {
    try {
      const data = await API.post("/api/search", {
        query,
        filters: {
          year_from: filters.year_from ? Number(filters.year_from) : null,
          year_to: filters.year_to ? Number(filters.year_to) : null,
          min_citations: filters.min_citations ? Number(filters.min_citations) : null,
        },
        top_k: topK,
      });
      (data.trace || []).forEach((entry) => {
        const step = $(`#pipeline .step[data-agent="${entry.agent}"]`);
        if (step) {
          step.classList.add(entry.status === "error" ? "error" : "done");
          $(".step-ms", step).textContent = `${Math.round(entry.ms)} ms`;
        }
      });
      state.payload = data;
      finishSearch(data.total_ms);
      renderResults(data);
    } catch (err) {
      toast(err.message || "Search failed", "err");
      finishSearch(null, true);
    }
  }

  function finishSearch(ms, failed = false) {
    state.searching = false;
    const button = $("#searchBtn");
    button.disabled = false;
    button.querySelector("span").textContent = "Search";
    loadHistory();
    if (!Prefs.get("agentPanel")) return;
    $("#agentMeta").textContent = failed ? "failed" : `${state.results.length} results · ${Math.round(ms || 0)} ms`;
  }

  /* ------------------------------- results ------------------------------ */
  function skeletonCards(n) {
    return Array.from({ length: n }, () => `
      <div class="skeleton">
        <div class="sk-line w70"></div><div class="sk-line w45"></div>
        <div class="sk-line w92"></div><div class="sk-line w92"></div>
      </div>`).join("");
  }

  function renderResults(payload) {
    state.results = payload.results || [];
    $("#resultsHead").hidden = false;
    $("#discover").hidden = true;

    const meta = payload.meta || {};
    const intent = (payload.understanding && payload.understanding.intent) || {};
    const seconds = ((payload.total_ms || 0) / 1000).toFixed(2);
    $("#resultsMeta").textContent =
      `${state.results.length} results · ${seconds}s` + (intent.type && intent.type !== "general" ? ` · ${intent.type} intent` : "");

    const weights = payload.weights || {};
    $("#whyLegend").innerHTML = Object.entries(weights).map(([k, v]) =>
      `<span><i style="background:${weightColor(k)}"></i>${esc(k)} ${Math.round(v * 100)}%</span>`).join("");

    renderCards();
    loadHistory();
  }

  function weightColor(name) {
    return ({ semantic: "#6366f1", influence: "#22d3ee", citation: "#fbbf24",
      recency: "#34d399", personal: "#f472b6" })[name] || "#94a3b8";
  }

  function renderCards() {
    const container = $("#results");
    const items = [...state.results];
    if (state.sort === "year") items.sort((a, b) => (b.paper.year || 0) - (a.paper.year || 0));
    if (state.sort === "citations") items.sort((a, b) => (b.paper.citation_count || 0) - (a.paper.citation_count || 0));
    container.innerHTML = items.map((res, i) => paperCard(res, i)).join("");
    container.onclick = onCardClick;
  }

  function paperCard(res, index) {
    const paper = res.paper || {};
    const summary = (res.summary && res.summary.summary) || paper.abstract || "";
    const reasons = (res.explanation && res.explanation.reasons) || [];
    const saved = state.saved.has(paper.paper_id);
    const liked = state.liked.has(paper.paper_id);
    const dismissed = state.dismissed.has(paper.paper_id);
    const selected = state.compare.has(paper.paper_id);
    const authors = (paper.authors || []).slice(0, 3).join(", ") + ((paper.authors || []).length > 3 ? " et al." : "");

    return `
    <article class="paper-card ${dismissed ? "dismissed" : ""} ${selected ? "selected" : ""}"
             data-id="${esc(paper.paper_id)}" style="--i:${index}">
      <div class="card-top">
        <div class="rank-badge ${res.rank === 1 ? "top" : ""}">${res.rank}</div>
        <div class="card-head">
          <div class="card-title" data-action="open">${esc(paper.title || "Untitled")}</div>
          <div class="card-meta">
            <span class="authors">${esc(authors || "Unknown authors")}</span>
            <span class="sep">·</span><span>${esc(paper.year || "n/a")}</span>
            <span class="sep">·</span><span>${esc(paper.venue || paper.source || "")}</span>
            ${paper.citation_count ? `<span class="sep">·</span><span>${fmt(paper.citation_count)} citations</span>` : ""}
          </div>
          <div class="card-badges">
            ${res.community_label ? `<span class="badge community">${esc(res.community_label)}</span>` : ""}
            ${res.bridge > 0.05 ? `<span class="badge bridge">interdisciplinary</span>` : ""}
            ${res.components && res.components.influence > 0.6 ? `<span class="badge influence">high influence</span>` : ""}
            ${saved ? `<span class="badge saved">in library</span>` : ""}
          </div>
        </div>
      </div>
      <p class="card-summary">${esc(short(summary, 340))}</p>
      ${reasons.length ? `<div class="card-why">${reasons.slice(0, 3).map((r) =>
        `<span class="why-chip"><b>${esc(r.label)}</b> ${esc(short(r.text, 58))}</span>`).join("")}</div>` : ""}
      <div class="card-foot">
        <div class="score-wrap">
          <span class="score-label">Match</span>
          <div class="score-bar"><div class="score-fill" style="width:${Math.round(clamp01(res.score) * 100)}%"></div></div>
          <span class="score-value">${(res.score || 0).toFixed(3)}</span>
        </div>
        <div class="card-actions">
          <button class="act-btn ${liked ? "on" : ""}" data-action="like" title="More like this">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M7 11v9H4v-9zM7 11l4-7a2 2 0 0 1 3 2l-1 5h5a2 2 0 0 1 2 2.4l-1.4 6A2 2 0 0 1 16.6 21H7"/></svg>
            Like
          </button>
          <button class="act-btn ${saved ? "on" : ""}" data-action="save" title="Save to library">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 4h12v17l-6-4-6 4z"/></svg>
            Save
          </button>
          <button class="act-btn compare ${selected ? "on" : ""}" data-action="compare" title="Add to comparison">
            ${ICON.compare} Compare
          </button>
          <button class="act-btn" data-action="open" title="Open details">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
            Details
          </button>
        </div>
      </div>
    </article>`;
  }

  async function onCardClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const card = event.target.closest(".paper-card");
    if (!card) return;
    const paperId = card.dataset.id;
    const action = button.dataset.action;

    if (action === "open") { openDetail(paperId); return; }

    if (action === "compare") {
      toggleCompare(paperId);
      card.classList.toggle("selected", state.compare.has(paperId));
      button.classList.toggle("on", state.compare.has(paperId));
      return;
    }

    if (action === "save") {
      try {
        if (state.saved.has(paperId)) {
          await API.del(`/api/library/${encodeURIComponent(paperId)}`);
          state.saved.delete(paperId);
          button.classList.remove("on");
          toast("Removed from library");
        } else {
          await API.post("/api/library", { paper_id: paperId, query: state.query });
          state.saved.add(paperId);
          button.classList.add("on");
          toast("Saved to library");
        }
        updateLibraryBadge();
      } catch (err) { toast(err.message, "err"); }
      return;
    }

    if (action === "like") {
      try {
        const data = await API.post("/api/feedback", { paper_id: paperId, action: "like", query: state.query });
        state.liked.add(paperId);
        button.classList.add("on");
        toast(data.learning && data.learning.personal_weight
          ? `Noted — your feed will adapt` : "Feedback recorded");
      } catch (err) { toast(err.message, "err"); }
      return;
    }

    if (action === "dismiss") {
      try {
        await API.post("/api/feedback", { paper_id: paperId, action: "dismiss", query: state.query });
        state.dismissed.add(paperId);
        card.classList.add("dismissed");
        toast("Hidden — your profile was adjusted");
      } catch (err) { toast(err.message, "err"); }
    }
  }

  /* ------------------------------- compare ------------------------------ */
  function bindCompare() {
    $("#trayClear").addEventListener("click", clearCompare);
    $("#clearCompare").addEventListener("click", () => { clearCompare(); switchView("search"); });
    $("#trayCompare").addEventListener("click", () => switchView("compare"));
  }

  function toggleCompare(paperId) {
    if (state.compare.has(paperId)) state.compare.delete(paperId);
    else {
      if (state.compare.size >= 4) { toast("Compare up to 4 papers", "err"); return; }
      const item = state.results.find((r) => r.paper.paper_id === paperId);
      state.compare.set(paperId, { paper: item ? item.paper : { paper_id: paperId, title: paperId }, result: item || null });
    }
    renderCompareTray();
  }

  function clearCompare() {
    state.compare.clear();
    renderCompareTray();
    renderCards();
  }

  function renderCompareTray() {
    const tray = $("#compareTray");
    const count = state.compare.size;
    tray.hidden = count === 0;
    $("#navCompare").hidden = count === 0;
    $("#compareBadge").hidden = count === 0;
    $("#compareBadge").textContent = String(count);
    $("#trayCount").textContent = String(count);
    $("#compareTrayItems").innerHTML = [...state.compare.values()].map(({ paper }) => `
      <span class="tray-chip" title="${esc(paper.title)}">
        ${esc(short(paper.title || paper.paper_id, 34))}
        <button data-remove="${esc(paper.paper_id)}" aria-label="Remove">×</button>
      </span>`).join("");
    $$("#compareTrayItems [data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.compare.delete(btn.dataset.remove);
        renderCompareTray();
        renderCards();
      });
    });
  }

  async function renderCompare() {
    const body = $("#compareBody");
    if (!state.compare.size) {
      body.innerHTML = `<div class="empty-state"><h3>Nothing selected</h3>
        <p>Use <b>Compare</b> on any result card to line papers up side by side.</p></div>`;
      return;
    }
    body.innerHTML = skeletonCards(2);
    const entries = [...state.compare.entries()];
    const details = await Promise.all(entries.map(async ([pid]) => {
      try { return await API.get(`/api/papers/${encodeURIComponent(pid)}`); }
      catch (e) { return null; }
    }));

    body.innerHTML = details.map((data, i) => {
      if (!data) return `<div class="compare-col"><h3>Unavailable</h3></div>`;
      const paper = data.paper || {};
      const metrics = data.metrics || {};
      const result = entries[i][1].result;
      return `
        <div class="compare-col">
          <h3>${esc(paper.title)}</h3>
          <div class="cc-meta">${esc((paper.authors || []).slice(0, 3).join(", "))}${paper.year ? " · " + paper.year : ""}${paper.venue ? " · " + paper.venue : ""}</div>
          ${result ? `<div class="compare-row"><div class="cr-label">Match score</div>
            <div class="cr-value big">${(result.score || 0).toFixed(3)}</div>
            <div class="compare-bar"><div style="width:${Math.round(clamp01(result.score) * 100)}%"></div></div></div>` : ""}
          <div class="compare-row"><div class="cr-label">Influence</div>
            <div class="cr-value big">${(metrics.influence || 0).toFixed(2)}</div>
            <div class="compare-bar"><div style="width:${Math.round((metrics.influence || 0) * 100)}%"></div></div></div>
          <div class="compare-row"><div class="cr-label">Citations</div><div class="cr-value">${fmt(metrics.citation_count || 0)}</div></div>
          <div class="compare-row"><div class="cr-label">Research community</div><div class="cr-value">${esc(metrics.community_label || "—")}</div></div>
          <div class="compare-row"><div class="cr-label">Summary</div><div class="cr-value">${esc(short(data.summary || paper.abstract || "", 320))}</div></div>
          <div class="compare-row"><div class="cr-label">Concepts</div>
            <div class="card-why">${(data.keywords || []).slice(0, 6).map((k) => `<span class="why-chip">${esc(k)}</span>`).join("")}</div></div>
          <div class="compare-row"><div class="cr-label">Actions</div>
            <button class="ghost-btn small" data-open="${esc(paper.paper_id)}">Open details</button></div>
        </div>`;
    }).join("");

    $$("#compareBody [data-open]").forEach((btn) => {
      btn.addEventListener("click", () => openDetail(btn.dataset.open));
    });
  }

  /* -------------------------------- drawer ------------------------------ */
  function bindDrawer() {
    $("#drawerClose").addEventListener("click", closeDrawer);
    $("#drawerOverlay").addEventListener("click", closeDrawer);
    $$(".drawer-tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => selectTab(tab.dataset.tab));
    });
  }

  function selectTab(name) {
    $$(".drawer-tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$(".tabpane").forEach((p) => { p.hidden = p.dataset.pane !== name; });
    if (name === "graph" && state.drawerGraph) state.drawerGraph.resize();
  }

  function closeDrawer() {
    $("#drawer").classList.remove("open");
    $("#drawer").setAttribute("aria-hidden", "true");
    $("#drawerOverlay").hidden = true;
  }

  async function openDetail(paperId) {
    state.currentPaper = paperId;
    $("#drawer").classList.add("open");
    $("#drawer").setAttribute("aria-hidden", "false");
    $("#drawerOverlay").hidden = false;
    $("#drawerBody").innerHTML = `<div class="skeleton"><div class="sk-line w70"></div><div class="sk-line w45"></div><div class="sk-line w92"></div></div>`;

    try {
      const [data, note] = await Promise.all([
        API.get(`/api/papers/${encodeURIComponent(paperId)}`, { q: state.query }),
        API.get(`/api/papers/${encodeURIComponent(paperId)}/note`).catch(() => ({ note: null })),
      ]);
      renderDetail(data, note.note);
      API.post("/api/feedback", { paper_id: paperId, action: "open", query: state.query }).catch(() => {});
    } catch (err) {
      $("#drawerBody").innerHTML = `<p class="detail-text">Could not load this paper: ${esc(err.message)}</p>`;
    }
  }

  function renderDetail(data, note) {
    const paper = data.paper || {};
    const metrics = data.metrics || {};
    const saved = state.saved.has(paper.paper_id);
    const authors = (paper.authors || []).join(", ");

    const overview = `
      <h2 class="detail-title">${esc(paper.title)}</h2>
      <div class="detail-meta">
        <span>${esc(authors || "Unknown authors")}</span><span class="sep">·</span>
        <span>${esc(paper.year || "n/a")}</span><span class="sep">·</span>
        <span>${esc(paper.venue || "")}</span><span class="sep">·</span>
        <span>${fmt(metrics.citation_count || 0)} citations</span>
      </div>
      <div class="card-badges" style="margin-top:12px">
        ${metrics.community_label ? `<span class="badge community">${esc(metrics.community_label)}</span>` : ""}
        <span class="badge influence">influence ${(metrics.influence || 0).toFixed(2)}</span>
        ${metrics.bridge > 0.02 ? `<span class="badge bridge">bridge ${(metrics.bridge || 0).toFixed(2)}</span>` : ""}
      </div>
      <div class="card-actions" style="margin:14px 0 0;margin-left:0">
        <button class="act-btn ${saved ? "on" : ""}" id="detailSave">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 4h12v17l-6-4-6 4z"/></svg>
          ${saved ? "Saved" : "Save"}
        </button>
        <button class="act-btn" id="copyCite">Copy citation</button>
        <a class="act-btn" href="${API.exportUrl(paper.paper_id, "bibtex")}">BibTeX</a>
        <a class="act-btn" href="${API.exportUrl(paper.paper_id, "ris")}">RIS</a>
        ${paper.url ? `<a class="act-btn" href="${esc(paper.url)}" target="_blank" rel="noopener">Source ↗</a>` : ""}
        ${paper.pdf_url ? `<a class="act-btn" href="${esc(paper.pdf_url)}" target="_blank" rel="noopener">PDF ↗</a>` : ""}
      </div>
      <div class="detail-section">
        <h4>Summary</h4>
        <p class="detail-text">${esc(data.summary || "")}</p>
      </div>
      ${(data.contributions || []).length ? `<div class="detail-section">
        <h4>Key contributions</h4>
        <ul class="detail-list">${data.contributions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
      </div>` : ""}
      <div class="detail-section">
        <h4>Concepts</h4>
        <div class="card-why">${(data.keywords || []).map((k) => `<span class="why-chip">${esc(k)}</span>`).join("")}</div>
      </div>
      <div class="detail-section">
        <h4>Metrics</h4>
        <div class="metric-grid">
          <div class="metric"><b>${(metrics.influence || 0).toFixed(2)}</b><span>PageRank</span></div>
          <div class="metric"><b>${(metrics.bridge || 0).toFixed(2)}</b><span>Bridge</span></div>
          <div class="metric"><b>${fmt(metrics.citation_count || 0)}</b><span>Citations</span></div>
          <div class="metric"><b>${metrics.degree || 0}</b><span>Graph degree</span></div>
        </div>
      </div>`;

    const why = `
      <div class="detail-section" style="margin-top:0">
        <h4>Why this paper</h4>
        <div class="reason-list">
          ${(data.explanation || []).map((r) => `
            <div class="reason">
              <div class="reason-ico">${esc(r.label.slice(0, 2).toUpperCase())}</div>
              <div class="reason-body"><div class="reason-label">${esc(r.label)}</div>
              <div class="reason-text">${esc(r.text)}</div></div>
              <div class="reason-val">${typeof r.value === "number" ? r.value.toFixed(2) : esc(r.value)}</div>
            </div>`).join("") || `<p class="detail-text">Run a search and open this paper from the results to see the full explanation.</p>`}
        </div>
      </div>
      <div class="detail-section"><h4>Abstract</h4><p class="detail-text">${esc(paper.abstract || "")}</p></div>`;

    const graphPane = `
      <div class="detail-section" style="margin-top:0">
        <h4>Neighbourhood</h4>
        <canvas class="mini-graph" id="miniGraph"></canvas>
      </div>
      <div class="detail-section">
        <h4>References found</h4>
        ${(data.citation_titles || []).length
          ? `<ul class="detail-list">${data.citation_titles.slice(0, 12).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`
          : `<p class="detail-text">No citation edges are available for this paper in the current index.</p>`}
      </div>`;

    const related = `
      <div class="detail-section" style="margin-top:0">
        <h4>Related work</h4>
        <div class="related-list">
          ${(data.related || []).map((r) => `
            <button class="related-item" data-related="${esc(r.paper_id)}">
              <span class="t">${esc(r.title)}</span><span class="s">${(r.similarity || 0).toFixed(2)}</span>
            </button>`).join("")}
        </div>
      </div>`;

    const notes = `
      <div class="detail-section" style="margin-top:0">
        <h4>Your notes</h4>
        <textarea class="note-area" id="noteArea" placeholder="What matters in this paper? Method, dataset, gap…">${esc(note ? note.body : "")}</textarea>
        <div class="note-actions">
          <button class="primary-btn small" id="saveNote">Save note</button>
          <button class="ghost-btn small" id="deleteNote">Delete</button>
          <span class="note-status" id="noteStatus">${note ? "saved " + new Date(note.ts).toLocaleDateString() : "not saved yet"}</span>
        </div>
      </div>`;

    $("#drawerBody").innerHTML = `
      <div class="tabpane" data-pane="overview">${overview}</div>
      <div class="tabpane" data-pane="why" hidden>${why}</div>
      <div class="tabpane" data-pane="graph" hidden>${graphPane}</div>
      <div class="tabpane" data-pane="related" hidden>${related}</div>
      <div class="tabpane" data-pane="notes" hidden>${notes}</div>`;

    selectTab("overview");

    const saveBtn = $("#detailSave");
    if (saveBtn) {
      saveBtn.addEventListener("click", async () => {
        try {
          if (state.saved.has(paper.paper_id)) {
            await API.del(`/api/library/${encodeURIComponent(paper.paper_id)}`);
            state.saved.delete(paper.paper_id);
            saveBtn.classList.remove("on");
            saveBtn.innerHTML = "Save";
            toast("Removed from library");
          } else {
            await API.post("/api/library", { paper_id: paper.paper_id, query: state.query });
            state.saved.add(paper.paper_id);
            saveBtn.classList.add("on");
            saveBtn.innerHTML = "Saved";
            toast("Saved to library");
          }
          updateLibraryBadge();
          renderCards();
        } catch (err) { toast(err.message, "err"); }
      });
    }

    const citeBtn = $("#copyCite");
    if (citeBtn) {
      citeBtn.addEventListener("click", async () => {
        try {
          const data2 = await API.get(`/api/papers/${encodeURIComponent(paper.paper_id)}/cite`, { style: "apa" });
          const ok = await copyText(data2.citation);
          toast(ok ? "Citation copied to clipboard" : "Could not copy", ok ? "ok" : "err");
        } catch (err) { toast(err.message, "err"); }
      });
    }

    const noteArea = $("#noteArea");
    if (noteArea) {
      $("#saveNote").addEventListener("click", async () => {
        try {
          await API.put(`/api/papers/${encodeURIComponent(paper.paper_id)}/note`, { body: noteArea.value });
          $("#noteStatus").textContent = "saved just now";
          toast("Note saved");
        } catch (err) { toast(err.message, "err"); }
      });
      $("#deleteNote").addEventListener("click", async () => {
        try {
          await API.del(`/api/papers/${encodeURIComponent(paper.paper_id)}/note`);
          noteArea.value = "";
          $("#noteStatus").textContent = "not saved yet";
          toast("Note deleted");
        } catch (err) { toast(err.message, "err"); }
      });
    }

    $$("#drawerBody [data-related]").forEach((btn) => {
      btn.addEventListener("click", () => openDetail(btn.dataset.related));
    });

    const canvas = $("#miniGraph");
    if (canvas) {
      state.drawerGraph = new ForceGraph(canvas, { onSelect: (n) => openDetail(n.id) });
      state.drawerGraph.setData(data.graph || { nodes: [], edges: [] });
      setTimeout(() => state.drawerGraph.resize(), 60);
    }
  }

  /* ------------------------------- discover ----------------------------- */
  async function loadHistory() {
    try {
      const data = await API.get("/api/history");
      const queries = (data.queries || []).filter((q) => q.query);
      $("#historyBlock").hidden = queries.length === 0;
      $("#historyChips").innerHTML = queries.slice(0, 8).map((q) => `
        <button class="history-chip" data-q="${esc(q.query)}">
          ${ICON.clock}${esc(short(q.query, 46))}${q.count > 1 ? `<em>${q.count}×</em>` : ""}
        </button>`).join("");
      $$("#historyChips .history-chip").forEach((btn) => {
        btn.addEventListener("click", () => {
          $("#queryInput").value = btn.dataset.q;
          runSearch(btn.dataset.q);
        });
      });
    } catch (err) { /* silent */ }
  }

  async function loadFeed() {
    try {
      const data = await API.get("/api/for-you", { limit: 6 });
      const papers = data.papers || [];
      $("#feedTitle").textContent = data.personalised ? "Recommended for you" : "Trending in the index";
      $("#feedNote").textContent = data.personalised
        ? "based on what you read and saved"
        : "most influential papers in the corpus";
      $("#feedGrid").innerHTML = papers.map((item) => {
        const p = item.paper || {};
        return `<button class="feed-card" data-id="${esc(p.paper_id)}">
          <span class="fc-title">${esc(short(p.title || "", 96))}</span>
          <span class="fc-meta">
            <span>${esc(p.year || "")}</span>
            ${item.community_label ? `<span>· ${esc(short(item.community_label, 28))}</span>` : ""}
            <span class="fc-score" style="margin-left:auto">${(item.score || 0).toFixed(2)}</span>
          </span>
        </button>`;
      }).join("");
      $$("#feedGrid .feed-card").forEach((card) => {
        card.addEventListener("click", () => openDetail(card.dataset.id));
      });
    } catch (err) { /* silent */ }
  }

  /* -------------------------------- library ----------------------------- */
  async function loadLibrary() {
    try {
      const data = await API.get("/api/library");
      state.saved = new Set((data.items || []).map((i) => i.paper_id));
      updateLibraryBadge();
      renderLibrary(data);
    } catch (err) {
      $("#libraryBody").innerHTML = `<p class="detail-text">Could not load library: ${esc(err.message)}</p>`;
    }
  }

  function updateLibraryBadge() {
    const badge = $("#libraryBadge");
    badge.hidden = state.saved.size === 0;
    badge.textContent = String(state.saved.size);
  }

  function renderLibrary(data) {
    const body = $("#libraryBody");
    const groups = data.groups || {};
    const names = Object.keys(groups);
    if (!names.length) {
      body.innerHTML = `<div class="empty-state">
        <div class="empty-art"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M6 4h12v17l-6-4-6 4z"/></svg></div>
        <h3>Your library is empty</h3>
        <p>Save papers from Discover and they appear here, ready to export as BibTeX or RIS.</p>
      </div>`;
      return;
    }
    body.innerHTML = names.map((name) => `
      <div class="list-group">
        <h3>${esc(name)} · ${groups[name].length}</h3>
        ${groups[name].map((item) => `
          <div class="lib-item" data-id="${esc(item.paper_id)}">
            <div style="flex:1;min-width:0">
              <div class="t" data-action="open">${esc(item.title)}</div>
              <div class="m">${esc((item.authors || []).slice(0, 3).join(", "))}${item.year ? " · " + item.year : ""}${item.venue ? " · " + item.venue : ""}</div>
            </div>
            <a class="act-btn" href="${API.exportUrl(item.paper_id, "bibtex")}" title="BibTeX">${ICON.download}</a>
            <button class="act-btn" data-action="remove" title="Remove">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
            </button>
          </div>`).join("")}
      </div>`).join("");

    body.onclick = async (event) => {
      const button = event.target.closest("[data-action]");
      const row = event.target.closest(".lib-item");
      if (!row) return;
      const id = row.dataset.id;
      if (button && button.dataset.action === "remove") {
        try {
          await API.del(`/api/library/${encodeURIComponent(id)}`);
          state.saved.delete(id);
          updateLibraryBadge();
          loadLibrary();
          toast("Removed");
        } catch (err) { toast(err.message, "err"); }
      } else if (!button) {
        openDetail(id);
      }
    };
  }

  /* --------------------------------- graph ------------------------------ */
  function bindGraphControls() {
    $("#graphReset").addEventListener("click", () => state.graphView && state.graphView.resetView());
    $("#graphLimit").addEventListener("change", loadGraph);
    $("#graphCommunity").addEventListener("change", loadGraph);
    $("#refreshLibrary").addEventListener("click", loadLibrary);
    $("#refreshInsights").addEventListener("click", loadInsights);
    $("#exportLibraryBib").addEventListener("click", () => { window.location.href = API.libraryExportUrl("bibtex"); });
    $("#exportLibraryRis").addEventListener("click", () => { window.location.href = API.libraryExportUrl("ris"); });
  }

  async function loadGraph() {
    const canvas = $("#graphCanvas");
    if (!state.graphView) state.graphView = new ForceGraph(canvas, { onSelect: (node) => openDetail(node.id) });
    try {
      const data = await API.get("/api/graph/overview", {
        limit: $("#graphLimit").value,
        community: $("#graphCommunity").value || undefined,
      });
      state.graphData = data;
      state.graphView.resize();
      state.graphView.setData(data);

      const labels = data.labels || {};
      const counts = {};
      (data.nodes || []).forEach((n) => { counts[n.community] = (counts[n.community] || 0) + 1; });
      const select = $("#graphCommunity");
      if (select.options.length <= 1) {
        Object.entries(labels).forEach(([id, label]) => {
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = `${label} (${counts[id] || 0})`;
          select.appendChild(opt);
        });
      }
      $("#graphLegend").innerHTML = Object.entries(labels).slice(0, 10).map(([id, label]) =>
        `<div class="lg"><span class="sw" style="background:${COMMUNITY_COLORS[Number(id) % COMMUNITY_COLORS.length]}"></span>${esc(label)}</div>`).join("");
      $("#graphStats").innerHTML = `
        <span class="chip">${data.nodes.length} papers</span>
        <span class="chip">${data.edges.length} links</span>
        <span class="chip">${data.communities} communities</span>`;
    } catch (err) { toast(err.message, "err"); }
  }

  /* ------------------------------- insights ----------------------------- */
  async function loadInsights() {
    const body = $("#insightsBody");
    try {
      const data = await API.get("/api/insights");
      const system = data.system || {};
      const feedback = data.feedback || {};
      const latencySeries = (data.recent_searches || []).map((r) => r.latency_ms || 0).reverse();

      body.innerHTML = `
        <div class="kpi-grid">
          ${kpi(fmt(system.papers_indexed || data.papers), "Papers indexed", `${fmt(data.searches)} searches`)}
          ${kpi(`${Math.round(data.avg_latency_ms || 0)} ms`, "Avg response", `${(data.recent_searches || []).length} recent runs`)}
          ${kpi(fmt((system.graph || {}).edges || 0), "Graph links", `${(system.graph || {}).nodes || 0} nodes`)}
          ${kpi(fmt(system.communities || 0), "Research communities", "detected automatically")}
          ${kpi(fmt(data.library_items || 0), "Saved papers", `${fmt(data.sessions || 0)} sessions`)}
        </div>
        <div class="grid-2">
          <div class="panel"><h3>Top queries</h3>
            ${bars((data.top_queries || []).map((q) => ({ label: q.query, value: q.count })))}</div>
          <div class="panel"><h3>Corpus by category</h3>
            ${bars((data.top_categories || []).map((c) => ({ label: c.category, value: c.count })))}</div>
          <div class="panel"><h3>Response time</h3>
            <canvas id="latencySpark" style="width:100%;height:120px"></canvas></div>
          <div class="panel"><h3>Feedback</h3>
            <div style="display:flex;gap:16px;align-items:center">
              <canvas id="feedbackDonut" style="width:140px;height:140px;flex:none"></canvas>
              <div style="flex:1">${Object.entries(feedback).map(([k, v]) =>
                `<div class="bar-row"><span class="lbl">${esc(k)}</span><span class="val">${v}</span></div>`).join("")
                || `<p class="detail-text">No feedback yet.</p>`}</div>
            </div></div>
          <div class="panel"><h3>Most influential papers</h3>
            ${(data.top_influence || []).map((p) => `
              <div class="bar-row">
                <span class="lbl" title="${esc(p.title)}">${esc(short(p.title, 56))}</span>
                <span class="val">${(p.influence || 0).toFixed(2)}</span>
                <div class="bar-track"><div class="bar-fill" style="width:${Math.round((p.influence || 0) * 100)}%"></div></div>
              </div>`).join("")}</div>
          <div class="panel"><h3>System</h3>
            <div class="sys-grid">
              ${sysTile("Embeddings", (system.embedding || {}).name || "—")}
              ${sysTile("Vector index", (system.vector_backend || {}).backend || "—")}
              ${sysTile("Graph", (system.graph || {}).backend || "—")}
              ${sysTile("Database", (system.database || {}).backend || "—")}
              ${sysTile("Summaries", (system.llm || {}).provider || "template")}
              ${sysTile("Dimensions", (system.embedding || {}).dim || "—")}
            </div></div>
        </div>`;

      drawSparkline($("#latencySpark"), latencySeries);
      drawDonut($("#feedbackDonut"), Object.entries(feedback).map(([k, v], i) => ({
        value: v, color: ["#34d399", "#fbbf24", "#f87171", "#6366f1", "#22d3ee"][i % 5],
      })));
    } catch (err) {
      body.innerHTML = `<p class="detail-text">Could not load insights: ${esc(err.message)}</p>`;
    }
  }

  const kpi = (value, label, sub) =>
    `<div class="kpi"><b>${value}</b><span>${esc(label)}</span><small>${esc(sub || "")}</small></div>`;
  const sysTile = (label, value) =>
    `<div class="sys-tile"><span>${esc(label)}</span><b title="${esc(value)}">${esc(value)}</b></div>`;

  function bars(items) {
    if (!items.length) return `<p class="detail-text">No data yet — run a few searches.</p>`;
    const max = Math.max(...items.map((i) => i.value), 1);
    return items.map((i) => `
      <div class="bar-row">
        <span class="lbl" title="${esc(i.label)}">${esc(short(i.label, 50))}</span>
        <span class="val">${i.value}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.round((i.value / max) * 100)}%"></div></div>
      </div>`).join("");
  }

  /* -------------------------------- palette ----------------------------- */
  let paletteItems = [];
  let paletteIndex = 0;

  function bindPalette() {
    $("#paletteBtn").addEventListener("click", () => openPalette());
    $("#paletteOverlay").addEventListener("click", closePalette);
    const input = $("#paletteInput");
    input.addEventListener("input", () => renderPalette(input.value));
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); paletteIndex = Math.min(paletteIndex + 1, paletteItems.length - 1); paintPalette(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); paletteIndex = Math.max(paletteIndex - 1, 0); paintPalette(); }
      else if (e.key === "Enter") { e.preventDefault(); const item = paletteItems[paletteIndex]; if (item) { closePalette(); item.run(); } }
    });
  }

  function openPalette() {
    $("#palette").hidden = false;
    $("#paletteOverlay").hidden = false;
    const input = $("#paletteInput");
    input.value = "";
    input.focus();
    renderPalette("");
  }

  function closePalette() {
    $("#palette").hidden = true;
    $("#paletteOverlay").hidden = true;
  }

  function paletteActions() {
    const actions = [
      { icon: ICON.search, label: "New search", sub: "/", run: () => { switchView("search"); $("#queryInput").focus(); } },
      { icon: ICON.book, label: "Go to Library", sub: "g l", run: () => switchView("library") },
      { icon: ICON.graph, label: "Go to Citation graph", sub: "g g", run: () => switchView("graph") },
      { icon: ICON.chart, label: "Go to Insights", sub: "g i", run: () => switchView("insights") },
      { icon: ICON.compare, label: "Go to Compare", sub: "", run: () => switchView("compare") },
      { icon: ICON.moon, label: `Switch to ${Theme.current() === "dark" ? "light" : "dark"} theme`, sub: "t", run: () => { Theme.toggle(); syncThemeUI(); } },
      { icon: ICON.gear, label: "Open settings", sub: "", run: () => openSettings() },
      { icon: ICON.download, label: "Export library as BibTeX", sub: "", run: () => { window.location.href = API.libraryExportUrl("bibtex"); } },
      { icon: ICON.trash, label: "Clear search history", sub: "", run: clearHistory },
    ];
    return actions;
  }

  function renderPalette(query) {
    const q = (query || "").trim().toLowerCase();
    const actions = paletteActions()
      .filter((a) => !q || a.label.toLowerCase().includes(q))
      .map((a) => ({ ...a }));

    const items = [];
    if (q) items.push({
      icon: ICON.search, label: `Search for “${query.trim()}”`, sub: "enter",
      run: () => { $("#queryInput").value = query.trim(); switchView("search"); runSearch(query.trim()); },
    });

    const history = $$("#historyChips .history-chip").map((b) => b.dataset.q);
    history
      .filter((h) => !q || h.toLowerCase().includes(q))
      .slice(0, 4)
      .forEach((h) => items.push({
        icon: ICON.clock, label: h, sub: "recent",
        run: () => { $("#queryInput").value = h; switchView("search"); runSearch(h); },
      }));

    items.push(...actions);

    if (q.length >= 3) {
      items.push({
        icon: ICON.sparkle, label: `Find papers similar to “${query.trim()}”`, sub: "suggest",
        run: async () => {
          try {
            const data = await API.get("/api/suggest", { q: query.trim() });
            const first = (data.suggestions || [])[0];
            if (first) openDetail(first.paper_id);
            else toast("No suggestions", "err");
          } catch (e) { toast(e.message, "err"); }
        },
      });
    }

    paletteItems = items;
    paletteIndex = 0;
    paintPalette();
  }

  function paintPalette() {
    const box = $("#paletteResults");
    if (!paletteItems.length) {
      box.innerHTML = `<div class="palette-empty">No matching actions</div>`;
      return;
    }
    box.innerHTML = paletteItems.map((item, i) => `
      <button class="palette-item ${i === paletteIndex ? "active" : ""}" data-index="${i}">
        <span class="pi-ico">${item.icon}</span>
        <span>${esc(item.label)}</span>
        ${item.sub ? `<span class="pi-sub">${esc(item.sub)}</span>` : ""}
      </button>`).join("");
    $$(".palette-item", box).forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = paletteItems[Number(btn.dataset.index)];
        closePalette();
        if (item) item.run();
      });
    });
    const active = $(".palette-item.active", box);
    if (active) active.scrollIntoView({ block: "nearest" });
  }

  /* -------------------------------- settings ---------------------------- */
  function bindSettings() {
    $("#settingsBtn").addEventListener("click", openSettings);
    $("#openSettings").addEventListener("click", openSettings);
    $("#settingsClose").addEventListener("click", closeSettings);
    $("#settingsOverlay").addEventListener("click", closeSettings);

    $("#themeBtn").addEventListener("click", () => { Theme.toggle(); syncThemeUI(); });

    $$("#themeSegmented button").forEach((btn) => {
      btn.addEventListener("click", () => { Theme.set(btn.dataset.themeValue); syncThemeUI(); });
    });

    $("#densitySelect").addEventListener("change", (e) => {
      Prefs.set("density", e.target.value);
      document.documentElement.setAttribute("data-density", e.target.value);
    });

    $("#defaultTopK").addEventListener("change", (e) => {
      Prefs.set("topK", Number(e.target.value));
      $("#topK").value = e.target.value;
    });

    $("#agentToggle").addEventListener("change", (e) => {
      Prefs.set("agentPanel", e.target.checked);
      $("#agentPanel").hidden = !e.target.checked;
      toast(e.target.checked ? "Agent activity enabled" : "Agent activity hidden");
    });

    $("#clearHistorySetting").addEventListener("click", clearHistory);
    $("#resetLocal").addEventListener("click", () => {
      Prefs.reset();
      Theme.apply("system");
      syncThemeUI();
      toast("Preferences reset");
    });
  }

  function openSettings() {
    syncThemeUI();
    $("#settings").classList.add("open");
    $("#settings").setAttribute("aria-hidden", "false");
    $("#settingsOverlay").hidden = false;
    loadConfig();
  }

  function closeSettings() {
    $("#settings").classList.remove("open");
    $("#settings").setAttribute("aria-hidden", "true");
    $("#settingsOverlay").hidden = true;
  }

  function syncThemeUI() {
    const pref = Prefs.get("theme");
    $$("#themeSegmented button").forEach((b) => b.classList.toggle("active", b.dataset.themeValue === pref));
    $("#densitySelect").value = Prefs.get("density");
    $("#defaultTopK").value = String(Prefs.get("topK"));
    $("#agentToggle").checked = !!Prefs.get("agentPanel");
    $("#topK").value = String(Prefs.get("topK"));
    $("#agentPanel").hidden = !Prefs.get("agentPanel") || !state.searching;
  }

  async function clearHistory() {
    try {
      await API.del("/api/history");
      $("#historyBlock").hidden = true;
      $("#historyChips").innerHTML = "";
      toast("Search history cleared");
    } catch (err) { toast(err.message, "err"); }
  }

  /* --------------------------------- misc ------------------------------- */
  function bindMisc() {
    bindGraphControls();
    $("#agentClose").addEventListener("click", () => { $("#agentPanel").hidden = true; });

    document.addEventListener("keydown", (e) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
      if (e.key === "Escape") {
        closePalette(); closeDrawer(); closeSettings();
        return;
      }
      if (e.key === "/" && !mod && document.activeElement.tagName !== "INPUT"
          && document.activeElement.tagName !== "TEXTAREA") {
        e.preventDefault();
        switchView("search");
        $("#queryInput").focus();
      }
      if (e.key === "t" && !mod && document.activeElement.tagName !== "INPUT"
          && document.activeElement.tagName !== "TEXTAREA") {
        Theme.toggle(); syncThemeUI();
      }
    });

    window.addEventListener("prefs:change", () => syncThemeUI());
    window.addEventListener("hashchange", () => {
      const hash = location.hash.replace("#", "");
      if (["search", "library", "graph", "insights", "compare"].includes(hash)) switchView(hash, false);
    });
    window.addEventListener("resize", () => {
      if (state.graphView && state.view === "graph") state.graphView.resize();
    });
  }
})();
