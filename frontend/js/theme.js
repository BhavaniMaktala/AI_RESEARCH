/* =====================================================================
   Theme + preference store (shared by every module)
   ===================================================================== */
const Prefs = (() => {
  const KEY = "paperrec.prefs";
  const DEFAULTS = { theme: "system", density: "comfortable", topK: 12, agentPanel: false };

  function all() {
    try { return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY)) || {}) }; }
    catch (e) { return { ...DEFAULTS }; }
  }
  function get(key) { return all()[key]; }
  function set(key, value) {
    const next = { ...all(), [key]: value };
    try { localStorage.setItem(KEY, JSON.stringify(next)); } catch (e) {}
    window.dispatchEvent(new CustomEvent("prefs:change", { detail: { key, value, prefs: next } }));
    return next;
  }
  function reset() {
    try { localStorage.removeItem(KEY); } catch (e) {}
    window.dispatchEvent(new CustomEvent("prefs:change", { detail: { key: "*", prefs: { ...DEFAULTS } } }));
  }
  return { all, get, set, reset, DEFAULTS };
})();

const Theme = (() => {
  const media = window.matchMedia("(prefers-color-scheme: dark)");

  function resolve(pref) {
    if (pref === "light" || pref === "dark") return pref;
    return media.matches ? "dark" : "light";
  }
  function apply(pref) {
    const mode = resolve(pref || Prefs.get("theme"));
    document.documentElement.setAttribute("data-theme", mode);
    document.documentElement.setAttribute("data-density", Prefs.get("density"));
    return mode;
  }
  function set(pref) {
    Prefs.set("theme", pref);
    return apply(pref);
  }
  function toggle() {
    const next = resolve(Prefs.get("theme")) === "dark" ? "light" : "dark";
    return set(next);
  }
  function current() { return resolve(Prefs.get("theme")); }

  media.addEventListener("change", () => {
    if (Prefs.get("theme") === "system") apply("system");
  });

  return { apply, set, toggle, current, resolve };
})();

Theme.apply(Prefs.get("theme"));
