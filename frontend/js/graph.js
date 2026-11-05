/* =====================================================================
   Force-directed graph renderer (canvas, no dependencies)
   Handles pan, zoom, drag, hover tooltips and click selection.
   ===================================================================== */
const COMMUNITY_COLORS = [
  "#6366f1", "#22d3ee", "#34d399", "#fbbf24", "#f472b6",
  "#a78bfa", "#fb7185", "#4ade80", "#38bdf8", "#facc15",
  "#f97316", "#2dd4bf",
];

class ForceGraph {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.nodes = [];
    this.links = [];
    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this.hover = null;
    this.dragged = null;
    this.dragging = false;
    this.onSelect = opts.onSelect || (() => {});
    this.alpha = 1;
    this._raf = null;
    this._bindEvents();
    this.resize();
  }

  setData(payload) {
    const w = this.canvas.clientWidth || 800;
    const h = this.canvas.clientHeight || 500;
    this.nodes = (payload.nodes || []).map((n, i) => {
      const angle = (i / Math.max(1, payload.nodes.length)) * Math.PI * 2;
      const radius = 60 + Math.random() * Math.min(w, h) * 0.32;
      return {
        ...n,
        x: w / 2 + Math.cos(angle) * radius,
        y: h / 2 + Math.sin(angle) * radius,
        vx: 0, vy: 0,
        r: 4 + Math.min(9, (n.influence || 0) * 9),
      };
    });
    const byId = new Map(this.nodes.map((n) => [n.id, n]));
    this.links = (payload.edges || [])
      .map((e) => ({ source: byId.get(e.source), target: byId.get(e.target), kind: e.kind, weight: e.weight }))
      .filter((l) => l.source && l.target);
    this.alpha = 1;
    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this.start();
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, rect.width * dpr);
    this.canvas.height = Math.max(1, rect.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.width = rect.width;
    this.height = rect.height;
    this.draw();
  }

  start() {
    if (this._raf) return;
    const loop = () => {
      this.tick();
      this.draw();
      if (this.alpha > 0.005 || this.dragged) {
        this._raf = requestAnimationFrame(loop);
      } else {
        this._raf = null;
      }
    };
    this._raf = requestAnimationFrame(loop);
  }

  tick() {
    const nodes = this.nodes;
    if (!nodes.length) return;
    const cx = this.width / 2;
    const cy = this.height / 2;
    const repulsion = 2600;
    const damping = 0.82;

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist2 = dx * dx + dy * dy;
        if (dist2 < 1) { dist2 = 1; dx = Math.random() - 0.5; dy = Math.random() - 0.5; }
        const force = repulsion / dist2;
        const dist = Math.sqrt(dist2);
        const fx = (dx / dist) * force * this.alpha;
        const fy = (dy / dist) * force * this.alpha;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }
    }

    for (const link of this.links) {
      const { source: a, target: b } = link;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const rest = 78;
      const strength = (dist - rest) * 0.012 * (0.5 + (link.weight || 0.3)) * this.alpha;
      const fx = (dx / dist) * strength;
      const fy = (dy / dist) * strength;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }

    for (const n of nodes) {
      n.vx += (cx - n.x) * 0.0022 * this.alpha;
      n.vy += (cy - n.y) * 0.0022 * this.alpha;
      n.vx *= damping; n.vy *= damping;
      n.x += n.vx; n.y += n.vy;
    }
    this.alpha *= 0.985;
  }

  draw() {
    const ctx = this.ctx;
    const { width, height } = this;
    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.translate(this.offsetX, this.offsetY);
    ctx.scale(this.scale, this.scale);

    // edges
    for (const link of this.links) {
      const { source: a, target: b } = link;
      const highlight = this.hover && (a === this.hover || b === this.hover);
      ctx.strokeStyle = link.kind === "cites"
        ? "rgba(251,191,36,0.45)"
        : highlight ? "rgba(129,140,248,0.75)" : "rgba(148,163,184,0.18)";
      ctx.lineWidth = (link.kind === "cites" ? 1.4 : 0.9) / this.scale;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    // nodes
    for (const n of this.nodes) {
      const color = COMMUNITY_COLORS[Math.abs(n.community ?? 0) % COMMUNITY_COLORS.length];
      const isHover = n === this.hover;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r + (isHover ? 2.5 : 0), 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = isHover ? 1 : 0.9;
      ctx.fill();
      ctx.globalAlpha = 1;
      if (isHover) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.6 / this.scale;
        ctx.stroke();
      }
    }

    // labels for important / hovered nodes
    ctx.font = `${11 / this.scale}px Inter, system-ui, sans-serif`;
    ctx.textAlign = "center";
    for (const n of this.nodes) {
      const show = n === this.hover || (n.influence || 0) > 0.45 || this.scale > 1.8;
      if (!show) continue;
      const label = (n.title || "").slice(0, 42) + ((n.title || "").length > 42 ? "…" : "");
      const y = n.y - n.r - 6 / this.scale;
      const metrics = ctx.measureText(label);
      ctx.fillStyle = "rgba(6,10,18,0.78)";
      ctx.fillRect(n.x - metrics.width / 2 - 4, y - 11 / this.scale, metrics.width + 8, 14 / this.scale);
      ctx.fillStyle = "#dbe4ff";
      ctx.fillText(label, n.x, y);
    }
    ctx.restore();
  }

  toGraphCoords(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (clientX - rect.left - this.offsetX) / this.scale,
      y: (clientY - rect.top - this.offsetY) / this.scale,
    };
  }

  pick(clientX, clientY) {
    const { x, y } = this.toGraphCoords(clientX, clientY);
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const n = this.nodes[i];
      const dx = n.x - x;
      const dy = n.y - y;
      if (dx * dx + dy * dy <= Math.pow(n.r + 4, 2)) return n;
    }
    return null;
  }

  _bindEvents() {
    const canvas = this.canvas;
    let last = null;

    canvas.addEventListener("mousedown", (e) => {
      const node = this.pick(e.clientX, e.clientY);
      if (node) {
        this.dragged = node;
        node.fixed = true;
      } else {
        this.dragging = true;
        last = { x: e.clientX, y: e.clientY };
        canvas.classList.add("dragging");
      }
      this.alpha = Math.max(this.alpha, 0.35);
      this.start();
    });

    canvas.addEventListener("mousemove", (e) => {
      if (this.dragged) {
        const { x, y } = this.toGraphCoords(e.clientX, e.clientY);
        this.dragged.x = x;
        this.dragged.y = y;
        this.dragged.vx = 0;
        this.dragged.vy = 0;
        this.alpha = Math.max(this.alpha, 0.2);
        this.start();
        return;
      }
      if (this.dragging && last) {
        this.offsetX += e.clientX - last.x;
        this.offsetY += e.clientY - last.y;
        last = { x: e.clientX, y: e.clientY };
        this.draw();
        return;
      }
      const node = this.pick(e.clientX, e.clientY);
      if (node !== this.hover) {
        this.hover = node;
        this.draw();
      }
      canvas.style.cursor = node ? "pointer" : "grab";
    });

    const endDrag = () => {
      if (this.dragged) { this.dragged.fixed = false; this.dragged = null; }
      this.dragging = false;
      last = null;
      canvas.classList.remove("dragging");
      this.alpha = Math.max(this.alpha, 0.15);
      this.start();
    };
    canvas.addEventListener("mouseup", endDrag);
    canvas.addEventListener("mouseleave", endDrag);

    canvas.addEventListener("click", (e) => {
      const node = this.pick(e.clientX, e.clientY);
      if (node && this.onSelect) this.onSelect(node);
    });

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.12 : 0.89;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const newScale = Math.min(4, Math.max(0.35, this.scale * factor));
      this.offsetX = mx - ((mx - this.offsetX) * newScale) / this.scale;
      this.offsetY = my - ((my - this.offsetY) * newScale) / this.scale;
      this.scale = newScale;
      this.draw();
    }, { passive: false });

    window.addEventListener("resize", () => this.resize());
  }

  resetView() {
    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this.alpha = 0.6;
    this.start();
  }
}
