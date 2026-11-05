/* =====================================================================
   Tiny chart helpers (canvas, dependency-free)
   ===================================================================== */

function drawSparkline(canvas, values, options = {}) {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, rect.width * dpr);
  canvas.height = Math.max(1, rect.height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width;
  const h = rect.height;
  ctx.clearRect(0, 0, w, h);

  if (!values || values.length < 2) {
    ctx.fillStyle = "rgba(148,163,184,0.5)";
    ctx.font = "12px Inter, system-ui, sans-serif";
    ctx.fillText("Not enough data yet", 8, h / 2);
    return;
  }

  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const pad = 6;
  const stepX = (w - pad * 2) / (values.length - 1);
  const yFor = (v) => h - pad - ((v - min) / Math.max(1, max - min)) * (h - pad * 2);

  const gradient = ctx.createLinearGradient(0, 0, 0, h);
  gradient.addColorStop(0, "rgba(99,102,241,0.35)");
  gradient.addColorStop(1, "rgba(99,102,241,0)");

  ctx.beginPath();
  values.forEach((v, i) => {
    const x = pad + i * stepX;
    const y = yFor(v);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = options.color || "#818cf8";
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  ctx.stroke();

  ctx.lineTo(pad + (values.length - 1) * stepX, h - pad);
  ctx.lineTo(pad, h - pad);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  values.forEach((v, i) => {
    const x = pad + i * stepX;
    const y = yFor(v);
    ctx.beginPath();
    ctx.arc(x, y, 2.4, 0, Math.PI * 2);
    ctx.fillStyle = "#c7d2fe";
    ctx.fill();
  });
}

function drawDonut(canvas, segments) {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, rect.width * dpr);
  canvas.height = Math.max(1, rect.height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width;
  const h = rect.height;
  ctx.clearRect(0, 0, w, h);

  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) / 2 - 8;
  const inner = radius * 0.62;

  if (!total) {
    ctx.strokeStyle = "rgba(148,163,184,0.25)";
    ctx.lineWidth = radius - inner;
    ctx.beginPath();
    ctx.arc(cx, cy, (radius + inner) / 2, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "rgba(148,163,184,0.6)";
    ctx.font = "12px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("no feedback yet", cx, cy + 4);
    return;
  }

  let start = -Math.PI / 2;
  segments.forEach((seg) => {
    const angle = (seg.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, start, start + angle);
    ctx.arc(cx, cy, inner, start + angle, start, true);
    ctx.closePath();
    ctx.fillStyle = seg.color;
    ctx.fill();
    start += angle;
  });

  ctx.fillStyle = "#e9eefc";
  ctx.font = "600 18px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(String(total), cx, cy + 2);
  ctx.fillStyle = "rgba(148,163,184,0.85)";
  ctx.font = "10px Inter, system-ui, sans-serif";
  ctx.fillText("SIGNALS", cx, cy + 16);
}
