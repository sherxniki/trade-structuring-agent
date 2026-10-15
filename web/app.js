// Trade Structuring Agent — page logic.

const COLORS = ["#2563eb", "#d97706", "#7c3aed"];
const $ = (id) => document.getElementById(id);

const state = { meta: null, plan: null, structure: 0, dayIndex: 0, tab: "compare" };

// ---------- formatting ----------

function money(x) {
  if (x === null || x === undefined) return "Unlimited";
  return `${x < 0 ? "-" : ""}$${Math.round(Math.abs(x)).toLocaleString("en-US")}`;
}
function signedMoney(x, suffix = "") {
  return `${x < 0 ? "-" : "+"}$${Math.round(Math.abs(x)).toLocaleString("en-US")}${suffix}`;
}
function cost(p) {
  if (Math.abs(p) < 5) return "≈ $0";
  return p > 0 ? `${money(p)} paid` : `${money(-p)} received`;
}
function loss(maxLoss) {
  if (maxLoss === null) return "Unlimited";
  return maxLoss < 0 ? money(-maxLoss) : "$0";
}
function price(x) {
  return `$${Number(x).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function pct(x, digits = 0) {
  return `${(x * 100).toFixed(digits)}%`;
}
function richText(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

// ---------- setup ----------

async function init() {
  try {
    const res = await fetch("/api/meta", { cache: "no-store" });
    state.meta = await res.json();
  } catch {
    state.meta = { ai: false, live: false, tickers: ["AAPL"], examples: [] };
  }
  const { meta } = state;

  $("examples").innerHTML = meta.examples
    .map((ex, i) => `<button type="button" data-i="${i}" title="${escapeHtml(ex)}">${escapeHtml(ex)}</button>`)
    .join("");
  $("examples").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    $("view").value = meta.examples[Number(button.dataset.i)];
    run();
  });

  $("ticker").innerHTML = meta.tickers.map((t) => `<option>${escapeHtml(t)}</option>`).join("");

  $("ai").checked = meta.ai;
  $("ai").disabled = !meta.ai;
  $("ai-hint").textContent = meta.ai
    ? "Uses the class app store's model (from your class allowance)."
    : "AI model not connected: using the built-in keyword reader.";
  $("live-row").hidden = !meta.live;

  $("rate").addEventListener("input", () => { $("rate-out").textContent = Number($("rate").value).toFixed(2); });
  $("skew").addEventListener("input", () => { $("skew-out").textContent = Number($("skew").value).toFixed(1); });
  $("build").addEventListener("click", run);
  $("view").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) run();
  });

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));

  let timer;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(() => state.plan && renderCharts(), 150);
  });
}

// ---------- run the agent ----------

const STEP_NAMES = [
  "Reading your view",
  "Fetching market data",
  "Designing and pricing candidate structures",
  "Comparing and writing the recommendation",
];

function showSteps(activeIndex, details = []) {
  const steps = $("steps");
  steps.hidden = false;
  steps.innerHTML = STEP_NAMES.map((name, i) => {
    const cls = i < activeIndex ? "done" : i === activeIndex ? "active" : "";
    const detail = details[i] ? `<span class="detail">${escapeHtml(details[i])}</span>` : "";
    return `<li class="${cls}">${name}${detail}</li>`;
  }).join("");
}

async function run() {
  const text = $("view").value.trim();
  if (!text) {
    showError("Type a market view first.");
    return;
  }
  showError("");
  $("build").disabled = true;

  let step = 0;
  showSteps(0);
  const ticker = setInterval(() => { if (step < 3) showSteps(++step); }, 900);

  try {
    const res = await fetch("/api/build", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        text,
        defaultTicker: $("ticker").value,
        rate: Number($("rate").value),
        skew: Number($("skew").value),
        useAI: $("ai").checked,
        live: $("live").checked,
      }),
    });
    const data = await res.json().catch(() => ({ error: "The server did not answer. Try again." }));
    if (!res.ok || data.error) throw new Error(data.error || "Something went wrong.");

    clearInterval(ticker);
    const v = data.view;
    showSteps(4, [
      `Read by ${v.parsed_by === "llm" ? "AI" : "keyword rules"}: ${v.ticker}, ${v.direction}` +
        (["bullish", "bearish"].includes(v.direction) ? ` (${v.strength})` : "") + `, ${v.horizonText}`,
      `${data.market.ticker} at ${price(data.market.spot)}, vol ${pct(data.market.atmVol)}. ${data.market.note}`,
      data.strategies.map((s) => s.name).join(" · "),
      data.explainedBy === "ai" ? "Explanation written by AI" : "Explanation from the built-in template",
    ]);
    state.plan = data;
    state.structure = 0;
    state.dayIndex = 0;
    render();
  } catch (error) {
    clearInterval(ticker);
    $("steps").hidden = true;
    showError(error.message);
  } finally {
    $("build").disabled = false;
  }
}

function showError(message) {
  $("error").hidden = !message;
  $("error").textContent = message;
}

// ---------- render ----------

function render() {
  const p = state.plan;
  const v = p.view;
  const md = p.market;
  $("results").hidden = false;

  // what the agent understood
  const budget = { any: "No limit", low: "Keep it cheap", zero: "Zero cost" }[v.cost_preference] +
    (v.max_premium ? ` (≤ ${money(v.max_premium)})` : "");
  const pills = [
    `Ticker: ${v.ticker}`,
    `View: ${v.direction}` + (["bullish", "bearish"].includes(v.direction) ? ` (${v.strength})` : ""),
    ...(v.move_pct ? [`Move: ${v.move_pct}%`] : []),
    `Horizon: ${v.horizonText}`,
    `Budget: ${budget}`,
    `Risk: ${v.limited_risk ? "Capped losses" : "OK with large risk"}`,
  ];
  $("pills").innerHTML = pills.map((t) => `<span class="pill">${escapeHtml(t)}</span>`).join("");

  const tiles = [
    { k: `${md.ticker} price`, v: price(md.spot) },
    { k: "Implied vol (ATM)", v: pct(md.atmVol, 1) },
    { k: "Expected move (1 sd)", v: `±${price(p.expectedMove)}` },
  ];
  if (["bullish", "bearish"].includes(v.direction)) {
    const change = p.targetPrice / md.spot - 1;
    tiles.push({ k: "Target price", v: price(p.targetPrice), d: `${change >= 0 ? "↑" : "↓"} ${pct(Math.abs(change), 1)}`, cls: change >= 0 ? "up" : "down" });
  } else if (v.direction === "hedge") {
    const change = p.downsidePrice / md.spot - 1;
    tiles.push({ k: "Downside scenario", v: price(p.downsidePrice), d: `↓ ${pct(Math.abs(change), 1)}`, cls: "down" });
  } else {
    tiles.push({ k: "Market data", v: md.source === "live" ? "Live" : "Sample" });
  }
  $("stats").innerHTML = tiles.map(statHtml).join("");
  $("market-note").hidden = md.source === "live";
  $("market-note").textContent = md.note;

  // recommendation
  const best = p.strategies[0];
  $("explanation").innerHTML = richText(p.explanation);
  $("best-legs").innerHTML = `<strong>Legs:</strong> ${best.legs.map((l) => escapeHtml(l.label)).join(" · ")} — expiry in ${escapeHtml(v.horizonText)}`;

  $("how-reader").textContent = v.parsed_by === "llm" ? "An LLM (through the class app store)" : "A keyword parser";

  renderCompareTable();
  renderAdvanced();
  renderCharts();
}

function statHtml(t) {
  return `<div class="stat"><div class="k">${escapeHtml(t.k)}</div><div class="v">${escapeHtml(t.v)}</div>` +
    (t.d ? `<div class="d ${t.cls || ""}">${escapeHtml(t.d)}</div>` : "") + `</div>`;
}

function renderCompareTable() {
  const p = state.plan;
  const hedge = p.view.direction === "hedge";
  const head = ["Structure", "Legs", "Upfront", "Max gain", "Max loss", "Breakeven", "If you're right", "Chance of profit", "Fit score"];
  const rows = p.strategies.map((s) => {
    const m = s.metrics;
    return `<tr class="${s.best ? "best" : ""}">` + [
      (s.best ? "★ " : "") + s.name,
      s.legs.map((l) => l.label).join(" · "),
      cost(m.netPremium),
      money(m.maxGain),
      loss(m.maxLoss),
      m.breakevens.map(price).join(", ") || "—",
      hedge ? "—" : money(m.pnlIfRight),
      pct(m.probProfit),
      s.score.toFixed(2),
    ].map((c) => `<td>${escapeHtml(c)}</td>`).join("") + `</tr>`;
  });
  $("compare-table").innerHTML = `<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody>`;
}

function markers() {
  const p = state.plan;
  const list = [{ x: p.market.spot, label: `Now ${price(p.market.spot)}`, color: "#6b7280", dash: "2 3" }];
  if (["bullish", "bearish"].includes(p.view.direction)) {
    list.push({ x: p.targetPrice, label: `Target ${price(p.targetPrice)}`, color: "#0ea5e9", dash: "6 4", labelPos: "bottom" });
  } else if (p.view.direction === "hedge") {
    list.push({ x: p.downsidePrice, label: `Downside ${price(p.downsidePrice)}`, color: "#dc2626", dash: "6 4", labelPos: "bottom" });
  }
  return list;
}

function renderCharts() {
  const p = state.plan;
  const xLabel = `${p.market.ticker} price at expiry`;

  // compare: all three at expiry
  const series = p.strategies.map((s, i) => ({
    name: (s.best ? "★ " : "") + s.name, y: s.expiry, color: COLORS[i], width: s.best ? 3.5 : 2, dash: s.best ? null : "7 5",
  }));
  if (p.stockOnly) series.push({ name: "Shares only (no hedge)", y: p.stockOnly, color: "#9ca3af", width: 2, dash: "2 4" });
  if (state.tab === "compare") {
    lineChart($("compare-chart"), { x: p.x, series, markers: markers(), xLabel, height: 380 });
  }
  $("compare-legend").innerHTML = legendHtml(series);

  // payoff: one chart per structure
  if (state.tab === "payoff") {
    const grid = $("payoff-grid");
    grid.innerHTML = p.strategies.map((s, i) => `<div class="item"><h3>${s.best ? "★ " : ""}${escapeHtml(s.name)}</h3>` +
      `<div class="chart" id="payoff-${i}"></div><div class="legend" id="payoff-legend-${i}"></div><p>${escapeHtml(s.summary)}</p></div>`).join("");
    p.strategies.forEach((s, i) => {
      const own = [
        { name: "At expiry", y: s.expiry, color: COLORS[i], width: 3, fill: true },
        { name: "If it moves today", y: s.today, color: COLORS[i], width: 1.5, dash: "2 3" },
      ];
      lineChart($(`payoff-${i}`), { x: p.x, series: own, markers: markers(), xLabel, height: 300 });
      $(`payoff-legend-${i}`).innerHTML = legendHtml(own);
    });
  }
}

function renderAdvanced() {
  const p = state.plan;
  const s = p.strategies[state.structure];
  const g = s.greeks;

  $("structure-pick").innerHTML = p.strategies.map((x, i) =>
    `<button type="button" class="${i === state.structure ? "on" : ""}" data-i="${i}">${x.best ? "★ " : ""}${escapeHtml(x.name)}</button>`).join("");
  $("structure-pick").onclick = (event) => {
    const b = event.target.closest("button");
    if (!b) return;
    state.structure = Number(b.dataset.i);
    renderAdvanced();
  };

  $("greeks").innerHTML = [
    { k: "Delta", v: `${g.delta_shares >= 0 ? "+" : ""}${Math.round(g.delta_shares)} shares`, d: `${signedMoney(g.delta_dollars)} exposure` },
    { k: "Gamma (shares per 1% move)", v: `${g.gamma_shares >= 0 ? "+" : ""}${g.gamma_shares.toFixed(2)}` },
    { k: "Vega (per vol point)", v: signedMoney(g.vega) },
    { k: "Theta (per day)", v: signedMoney(g.theta) },
  ].map(statHtml).join("");

  $("days-pick").innerHTML = p.days.map((d, i) =>
    `<button type="button" class="${i === state.dayIndex ? "on" : ""}" data-i="${i}">${d === 0 ? "Today" : `+${d}d`}</button>`).join("");
  $("days-pick").onclick = (event) => {
    const b = event.target.closest("button");
    if (!b) return;
    state.dayIndex = Number(b.dataset.i);
    renderAdvanced();
  };

  const grid = s.grids[String(p.days[state.dayIndex])];
  const maxAbs = Math.max(1, ...grid.flat().map(Math.abs));
  const head = `<thead><tr><th class="row">Vol ↓ / Price →</th>${p.spotMoves.map((x) => `<th>${x > 0 ? "+" : ""}${pct(x)}</th>`).join("")}</tr></thead>`;
  const body = grid.map((row, r) => `<tr><th class="row">${p.volMoves[r] > 0 ? "+" : ""}${p.volMoves[r]} vol</th>` +
    row.map((v) => `<td style="${heatColor(v, maxAbs)}">${v > 0 ? "+" : ""}${Math.round(v).toLocaleString("en-US")}</td>`).join("") + `</tr>`).join("");
  $("heat").innerHTML = head + `<tbody>${body}</tbody>`;

  $("legs-table").innerHTML = `<thead><tr><th>Leg</th><th>Strike</th><th>Implied vol</th><th>Price / share</th></tr></thead><tbody>` +
    s.legs.map((l) => `<tr><td>${escapeHtml(l.label)}</td><td>${l.strike === null ? "—" : price(l.strike)}</td>` +
      `<td>${l.vol === null ? "—" : pct(l.vol, 1)}</td><td>${price(l.price)}</td></tr>`).join("") + `</tbody>`;
}

function showTab(name) {
  state.tab = name;
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === name);
    t.setAttribute("aria-selected", t.dataset.tab === name ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
  if (state.plan) renderCharts();
}

init();
