/* =====================================================================
   API client: REST + Server-Sent Events
   ===================================================================== */
const API = (() => {
  const SESSION_KEY = "paperrec.session";
  let sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = (crypto.randomUUID ? crypto.randomUUID() : "s-" + Math.random().toString(36).slice(2));
    localStorage.setItem(SESSION_KEY, sessionId);
  }

  function qs(params) {
    const search = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") search.set(k, v);
    });
    const s = search.toString();
    return s ? "?" + s : "";
  }

  async function request(path, options = {}) {
    const res = await fetch(path, {
      method: options.method || "GET",
      headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    let data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
    return data;
  }

  function streamSearch(query, filters, topK, handlers = {}) {
    const params = { q: query, top_k: topK, session_id: sessionId };
    if (filters.year_from) params.year_from = filters.year_from;
    if (filters.year_to) params.year_to = filters.year_to;

    const source = new EventSource("/api/search/stream" + qs(params));
    let received = false;

    source.onmessage = (event) => {
      received = true;
      let payload;
      try { payload = JSON.parse(event.data); } catch (e) { return; }
      if (handlers.onEvent) handlers.onEvent(payload);
      if (payload.event === "done" || payload.event === "error") source.close();
    };
    source.onerror = () => {
      source.close();
      if (!received && handlers.onFallback) handlers.onFallback();
      else if (handlers.onError) handlers.onError();
    };
    return { close: () => source.close(), hadData: () => received };
  }

  return {
    sessionId,
    get: (path, params) => request(path + qs(params)),
    post: (path, body) => request(path, { method: "POST", body }),
    put: (path, body) => request(path, { method: "PUT", body }),
    del: (path) => request(path, { method: "DELETE" }),
    streamSearch,
    exportUrl: (paperId, fmt) => `/api/papers/${encodeURIComponent(paperId)}/export?format=${fmt}&session_id=${sessionId}`,
    libraryExportUrl: (fmt) => `/api/library/export?format=${fmt}&session_id=${sessionId}`,
  };
})();
