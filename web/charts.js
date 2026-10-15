// Small SVG chart helpers (no outside libraries).

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function niceStep(range, count) {
  const raw = range / Math.max(count, 1);
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const unit = raw / power;
  const nice = unit < 1.5 ? 1 : unit < 3 ? 2 : unit < 7 ? 5 : 10;
  return nice * power;
}

function niceTicks(min, max, count) {
  if (min === max) { min -= 1; max += 1; }
  const step = niceStep(max - min, count);
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return ticks;
}

function axisMoney(v) {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 10000) return `${sign}$${Math.round(abs / 1000)}k`;
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${sign}$${Math.round(abs)}`;
}

function tipMoney(v) {
  return `${v < 0 ? "-" : ""}$${Math.round(Math.abs(v)).toLocaleString("en-US")}`;
}

// series: [{name, y, color, width, dash, fill}]  markers: [{x, label, color, dash, labelPos}]
function lineChart(el, opts) {
  const width = Math.max(el.clientWidth || 640, 260);
  const height = opts.height || 340;
  const m = { l: 56, r: 12, t: 22, b: 40 };
  const xs = opts.x;
  const x0 = xs[0], x1 = xs[xs.length - 1];

  let ys = [0];
  opts.series.forEach((s) => s.y.forEach((v) => ys.push(v)));
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const pad = (y1 - y0) * 0.08;
  y0 -= pad; y1 += pad;
  const yTicks = niceTicks(y0, y1, height < 300 ? 4 : 6);
  const xTicks = niceTicks(x0, x1, width < 420 ? 3 : 6).filter((v) => v >= x0 && v <= x1);

  const X = (v) => m.l + ((v - x0) / (x1 - x0)) * (width - m.l - m.r);
  const Y = (v) => m.t + ((y1 - v) / (y1 - y0)) * (height - m.t - m.b);
  const pts = (arr) => arr.map((v, i) => `${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");

  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(opts.label || "Profit and loss chart")}">`;
  svg += `<g class="grid">`;
  yTicks.forEach((t) => { svg += `<line x1="${m.l}" x2="${width - m.r}" y1="${Y(t)}" y2="${Y(t)}"/>`; });
  xTicks.forEach((t) => { svg += `<line y1="${m.t}" y2="${height - m.b}" x1="${X(t)}" x2="${X(t)}"/>`; });
  svg += `</g><g class="axis">`;
  yTicks.forEach((t) => { svg += `<text x="${m.l - 8}" y="${Y(t) + 4}" text-anchor="end">${axisMoney(t)}</text>`; });
  xTicks.forEach((t) => { svg += `<text x="${X(t)}" y="${height - m.b + 16}" text-anchor="middle">$${Math.round(t)}</text>`; });
  svg += `<text x="${(m.l + width - m.r) / 2}" y="${height - 6}" text-anchor="middle">${escapeHtml(opts.xLabel || "")}</text>`;
  svg += `</g>`;

  // profit / loss shading
  opts.series.filter((s) => s.fill).forEach((s) => {
    const up = s.y.map((v) => Math.max(v, 0));
    const down = s.y.map((v) => Math.min(v, 0));
    const base = `${X(x1)},${Y(0)} ${X(x0)},${Y(0)}`;
    svg += `<polygon points="${pts(up)} ${base}" fill="rgba(22,163,74,0.13)"/>`;
    svg += `<polygon points="${pts(down)} ${base}" fill="rgba(220,38,38,0.12)"/>`;
  });

  svg += `<line class="zero" x1="${m.l}" x2="${width - m.r}" y1="${Y(0)}" y2="${Y(0)}"/>`;

  (opts.markers || []).forEach((mk) => {
    if (mk.x < x0 || mk.x > x1) return;
    const dash = mk.dash || "3 3";
    const anchor = X(mk.x) > width - 90 ? "end" : "start";
    const dx = anchor === "end" ? -4 : 4;
    const ty = mk.labelPos === "bottom" ? height - m.b - 6 : m.t - 6;
    svg += `<line x1="${X(mk.x)}" x2="${X(mk.x)}" y1="${m.t}" y2="${height - m.b}" stroke="${mk.color}" stroke-dasharray="${dash}" stroke-width="1.5"/>`;
    svg += `<text x="${X(mk.x) + dx}" y="${ty}" text-anchor="${anchor}" font-size="11" fill="${mk.color}">${escapeHtml(mk.label)}</text>`;
  });

  opts.series.forEach((s) => {
    const dash = s.dash ? ` stroke-dasharray="${s.dash}"` : "";
    svg += `<polyline points="${pts(s.y)}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}"${dash} stroke-linejoin="round"/>`;
  });

  svg += `<line class="hover-line" x1="0" x2="0" y1="${m.t}" y2="${height - m.b}" stroke="#9ca3af" visibility="hidden"/>`;
  svg += `<rect class="hover-area" x="${m.l}" y="${m.t}" width="${width - m.l - m.r}" height="${height - m.t - m.b}" fill="transparent"/>`;
  svg += `</svg>`;

  el.innerHTML = svg + `<div class="tooltip" hidden></div>`;

  // hover tooltip
  const svgEl = el.querySelector("svg");
  const area = el.querySelector(".hover-area");
  const line = el.querySelector(".hover-line");
  const tip = el.querySelector(".tooltip");
  area.addEventListener("mousemove", (event) => {
    const box = svgEl.getBoundingClientRect();
    const scale = width / box.width;
    const px = (event.clientX - box.left) * scale;
    const value = x0 + ((px - m.l) / (width - m.l - m.r)) * (x1 - x0);
    let i = 0;
    for (let j = 1; j < xs.length; j++) if (Math.abs(xs[j] - value) < Math.abs(xs[i] - value)) i = j;
    line.setAttribute("x1", X(xs[i]));
    line.setAttribute("x2", X(xs[i]));
    line.setAttribute("visibility", "visible");
    tip.innerHTML = `<strong>$${xs[i].toFixed(2)}</strong><br>` +
      opts.series.map((s) => `${escapeHtml(s.name)}: ${tipMoney(s.y[i])}`).join("<br>");
    tip.style.left = `${X(xs[i]) / scale}px`;
    tip.style.top = `${(m.t + 10) / scale}px`;
    tip.hidden = false;
  });
  area.addEventListener("mouseleave", () => {
    line.setAttribute("visibility", "hidden");
    tip.hidden = true;
  });
}

function legendHtml(series) {
  return series.map((s) => {
    const style = s.dash ? (s.dash.startsWith("2") || s.dash.startsWith("1") ? "dot" : "dash") : "";
    return `<span class="${style}" style="--c:${s.color}">${escapeHtml(s.name)}</span>`;
  }).join("");
}

// Red → white → green background for a P&L value.
function heatColor(value, maxAbs) {
  const t = Math.max(-1, Math.min(1, value / (maxAbs || 1)));
  const mix = (a, b, f) => Math.round(a + (b - a) * f);
  const [r, g, b] = t >= 0 ? [mix(255, 22, t), mix(255, 163, t), mix(255, 74, t)]
                            : [mix(255, 220, -t), mix(255, 38, -t), mix(255, 38, -t)];
  const text = Math.abs(t) > 0.55 ? "#fff" : "#1f2430";
  return `background:rgb(${r},${g},${b});color:${text}`;
}
