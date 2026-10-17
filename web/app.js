// HourProof dashboard. Plain ES modules, no build step.
import { loadCarbon } from "./carbon.js";

const $ = (id) => document.getElementById(id);
const pct = (x, d = 1) => `${(100 * x).toFixed(d)}%`;
const bps = (b) => `${(b / 100).toFixed(2)}%`;
const fmt = (n) => Math.round(n).toLocaleString("en-GB");
let week = null;
let mode = "naive";
let polling = null;

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

function renderWeek() {
  const el = $("week");
  el.innerHTML = "";
  if (!week?.available) {
    el.innerHTML = `<p class="muted" style="grid-column:1/-1">No data yet. Run <code>python -m hourproof data fetch</code> and <code>python -m hourproof agent backtest</code>, then reload.</p>`;
    return;
  }
  el.appendChild(Object.assign(document.createElement("div"), { className: "hr" }));
  for (let h = 0; h < 24; h++) {
    el.appendChild(Object.assign(document.createElement("div"), { className: "hr", textContent: h % 3 === 0 ? String(h).padStart(2, "0") : "" }));
  }
  const load = mode === "agent" ? week.private_agent_load_mwh : week.private_naive_load_mwh;
  const cert = week.base_mwh.map((b, i) => b + (mode === "agent" ? week.topup_mwh[i] : 0));
  for (let d = 0; d < 7; d++) {
    const t = new Date(week.hours[d * 24] + "Z");
    el.appendChild(Object.assign(document.createElement("div"), {
      className: "day", textContent: t.toLocaleDateString("en-GB", window.innerWidth < 760 ? { weekday: "short", day: "numeric", timeZone: "UTC" } : { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }),
    }));
    for (let h = 0; h < 24; h++) {
      const i = d * 24 + h;
      const share = Math.min(cert[i] / load[i], 1);
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.tabIndex = 0;
      const label = `${week.hours[i].slice(0, 16)} UTC: ${fmt(Math.min(cert[i], load[i]))} of ${fmt(load[i])} MWh covered (${pct(share, 0)})`;
      cell.title = label;
      cell.setAttribute("aria-label", label);
      const fill = document.createElement("div");
      fill.className = "fill";
      fill.style.height = `${(100 * share).toFixed(1)}%`;
      cell.appendChild(fill);
      el.appendChild(cell);
    }
  }
  const c = mode === "agent" ? week.coverage_agent : week.coverage_naive;
  $("week-caption").textContent = `Week of ${week.window_start_utc.slice(0, 10)} (UTC). Hourly coverage this week: ${pct(c)}. Source: ${week.source}.`;
  drawBars($("pub-chart"), cert, null, "Certificates (MWh)");
  drawBars($("priv-chart"), load, cert, "Load (MWh)");
}

function drawBars(svg, values, overlay, label) {
  const W = 700, H = 160, n = values.length, max = Math.max(...values, ...(overlay || [0])) * 1.08 || 1;
  const bw = W / n;
  const css = getComputedStyle(document.documentElement);
  const clean = css.getPropertyValue("--clean").trim(), ink = css.getPropertyValue("--ink").trim(), rule = css.getPropertyValue("--rule").trim();
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  let s = `<line x1="0" y1="${H - 0.5}" x2="${W}" y2="${H - 0.5}" stroke="${rule}"/>`;
  for (let d = 1; d < 7; d++) s += `<line x1="${d * 24 * bw}" y1="0" x2="${d * 24 * bw}" y2="${H}" stroke="${rule}" stroke-width="1"/>`;
  if (!overlay) {
    values.forEach((v, i) => { const h = (v / max) * H; s += `<rect x="${i * bw + 0.5}" y="${H - h}" width="${Math.max(bw - 1, 1)}" height="${h}" fill="${clean}"/>`; });
  } else {
    overlay.forEach((v, i) => { const h = (v / max) * H; s += `<rect x="${i * bw}" y="${H - h}" width="${bw}" height="${h}" fill="${clean}" opacity="0.28"/>`; });
    const pts = values.map((v, i) => `${(i + 0.5) * bw},${H - (v / max) * H}`).join(" ");
    s += `<polyline points="${pts}" fill="none" stroke="${ink}" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
  }
  svg.innerHTML = `<title>${label}</title>` + s;
}

function renderOverview(o) {
  const ds = o.dataset, bt = o.backtest, demo = o.demo;
  if (ds) {
    $("h-annual").textContent = "100% clean over the year.";
    $("h-hourly").textContent = `${pct(ds.hourly_match_of_100pct_annual_wind)} hour by hour.`;
    $("lede").textContent = `${ds.buyer_label ? `Denmark's ${ds.buyer_label} sector, as one buyer,` : "A buyer"} buys exactly its yearly consumption in Danish wind${ds.year ? ` (${ds.year})` : ""}. Hour by hour, only ${pct(ds.hourly_match_of_100pct_annual_wind)} of its consumption is met by wind produced in that same hour. HourProof makes each hour's certificate count once, proves the hourly match without revealing consumption, and lets an AI agent close the gap.`;
  }
  const status = $("status");
  if (o.running) { status.textContent = "Run in progress"; status.className = "status warn"; }
  else if (demo?.status === "done") { status.textContent = `Last run ${demo.run_id} on ${demo.network}: passed`; status.className = "status ok"; }
  else if (demo?.status === "failed") { status.textContent = `Last run ${demo.run_id} failed`; status.className = "status warn"; }
  else status.textContent = ds ? `Dataset: ${ds.hours} hours of ${ds.year}` : "No dataset yet";

  if (bt) {
    const c = bt.coverage;
    $("agent-meta").textContent = `Walk-forward on real hours, ${bt.test_period[0]} to ${bt.test_period[1]}. Decisions use only what was known at 17:30 UTC the day before. Flexible share ${pct(bt.params.flex_share, 0)} of each hour's load (scenario parameter); extra certificates ${pct(bt.extra_share_of_test_load)} of load, and the comparison portfolio gets exactly the same extra MWh.`;
    const rows = [
      ["Fixed portfolio", c.naive_fixed_portfolio],
      ["Bigger portfolio, same MWh", c.bigger_portfolio_same_mwh],
      ["Agent: moving flexible load", c.agent_shift_only],
      ["Agent: moving load and buying hours", c.agent_shift_and_topup],
      ["Perfect foresight (reference)", c.perfect_foresight_bound, true],
    ];
    $("bars").innerHTML = rows.map(([n, v, bound]) => `<div class="bar${bound ? " bound" : ""}"><span>${n}</span><div class="track"><div class="val" style="width:${(100 * v).toFixed(1)}%"></div></div><span class="num">${pct(v)}</span></div>`).join("");
    const sk = bt.forecast_skill;
    $("skill").innerHTML = `
      <div><dt>Gain over the same MWh</dt><dd>${bt.gain_vs_same_mwh_pp >= 0 ? "+" : ""}${bt.gain_vs_same_mwh_pp.toFixed(1)} points</dd></div>
      <div><dt>Wind error, published forecast</dt><dd>${fmt(sk.wind_mae_raw_forecast_mwh)} MWh/h</dd></div>
      <div><dt>Wind error, agent's model</dt><dd>${fmt(sk.wind_mae_model_mwh)} MWh/h</dd></div>
      <div><dt>Load error, agent vs last week</dt><dd>${sk.load_mae_model_mwh.toFixed(1)} vs ${sk.load_mae_lag168_mwh.toFixed(1)} MWh/h</dd></div>`;
  } else {
    $("agent-meta").textContent = "No backtest yet: python -m hourproof agent backtest";
  }
  renderRun(demo);
  applyStaticSnapshot(o.static_snapshot);
}

// Hosted without a backend (e.g. Vercel): the data is a snapshot of one verified public run, nothing can be started.
function applyStaticSnapshot(s) {
  if (!s) return;
  for (const b of [$("run-local"), $("run-base")]) {
    b.disabled = true;
    b.title = "Static snapshot: run it yourself with make demo (local chain) or make demo-base (Base Sepolia)";
  }
  const note = `Static snapshot of the verified ${s.network} run ${s.run_id} (${s.verification}). Every transaction links to its block explorer. To run the scenario yourself: make demo (local chain) or make demo-base (Base Sepolia). `;
  $("run-meta").textContent = note + $("run-meta").textContent;
}

function renderRun(demo) {
  if (!demo) return;
  const network = demo.network === "base-sepolia" ? "Base Sepolia" : "a local replay chain";
  $("run-meta").textContent = `Run ${demo.run_id} on ${network}${demo.zk_mode === "mock" ? " with a MOCK verifier (test mode, not a real proof)" : ""}: ${demo.status}${demo.summary?.transactions ? `, ${demo.summary.transactions} transactions, ${fmt(demo.summary.gas_total)} gas` : ""}.`;
  $("steps").innerHTML = demo.steps.map((s) => `
    <li><span class="title">${s.title}</span><span class="state ${s.status}">${s.status === "done" ? "Done" : s.status === "failed" ? "Failed" : "Running"}${s.seconds ? `, ${s.seconds}s` : ""}</span>
      <span class="detail">${escapeHTML(s.detail || "")}</span>
      ${s.txs?.length ? `<span class="txs">${s.txs.slice(0, 12).map((t) => t.url ? `<a href="${t.url}" target="_blank" rel="noopener">${escapeHTML(t.label)}</a>` : `<span title="${t.hash}">${escapeHTML(t.label)} (${fmt(t.gas)} gas)</span>`).join("")}${s.txs.length > 12 ? `<span class="muted">+${s.txs.length - 12} more</span>` : ""}</span>` : ""}
    </li>`).join("");
  if (demo.attacks?.length) {
    $("attacks").innerHTML = demo.attacks.map((a) => `
      <li><span>${escapeHTML(a.title)}</span><span class="verdict ${a.status === "blocked" ? "blocked" : "not"}">${a.status === "blocked" ? `Refused: ${a.observed}` : `${a.status} (${a.observed || "…"})`}</span>
      ${a.note ? `<span class="why">${escapeHTML(a.note)}</span>` : ""}</li>`).join("");
  }
  const prove = demo.steps.find((s) => s.id === "prove");
  if (prove?.metrics?.proven_bps) {
    $("proven").textContent = `Proven on-chain: coverage ≥ ${bps(prove.metrics.proven_bps)}`;
    $("truth").textContent = `True coverage, private: ${bps(prove.metrics.true_coverage_private_bps)}`;
  }
  const note = demo.steps.find((s) => s.id === "note")?.metrics;
  if (note && note.coupon_bps !== undefined && note.kpi === "RESIDUAL_EMISSIONS") {
    const t = (kg) => `${(kg / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} t`;
    $("note-text").textContent = note.kpi_met
      ? `The emissions proof showed residual emissions of at most ${t(note.proven_residual_kg)}, within the ${t(note.target_residual_kg)} target fixed by rule before the week, so the note paid its base coupon.`
      : `No proof showed residual emissions within the ${t(note.target_residual_kg)} target (fixed by rule before the week) by the deadline, so the coupon stepped up automatically.`;
    $("note").innerHTML = `<div><dt>KPI</dt><dd>Residual emissions</dd></div><div><dt>Target</dt><dd>≤ ${t(note.target_residual_kg)}</dd></div>
      <div><dt>Proven</dt><dd>≤ ${t(note.proven_residual_kg)}</dd></div><div><dt>KPI met</dt><dd>${note.kpi_met ? "Yes" : "No"}</dd></div>
      <div><dt>Coupon</dt><dd>${bps(note.coupon_bps)}</dd></div><div><dt>Paid on 1,000 notes</dt><dd>${fmt(note.coupon_paid_tusd)} tUSD</dd></div>`;
  } else if (note && note.coupon_bps !== undefined) {
    $("note-text").textContent = note.kpi_met
      ? `The proof met the ${bps(note.target_bps)} target, so the note paid its base coupon.`
      : `No proof reached the ${bps(note.target_bps)} target by the deadline, so the coupon stepped up automatically.`;
    $("note").innerHTML = `<div><dt>KPI target</dt><dd>${bps(note.target_bps)}</dd></div><div><dt>KPI met</dt><dd>${note.kpi_met ? "Yes" : "No"}</dd></div>
      <div><dt>Coupon</dt><dd>${bps(note.coupon_bps)}</dd></div><div><dt>Paid on 1,000 notes</dt><dd>${fmt(note.coupon_paid_tusd)} tUSD</dd></div>`;
  }
}

function escapeHTML(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]); }

async function refresh() {
  const [o, w] = await Promise.all([getJSON("/api/overview"), getJSON("/api/week")]);
  week = w;
  renderOverview(o);
  renderWeek();
  loadCarbon().catch(() => {});
  return o;
}

async function startRun(network) {
  for (const b of [$("run-local"), $("run-base")]) b.disabled = true;
  try {
    const r = await fetch("/api/demo/run", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ network, zk_mode: "real", mode: "carbon" }) });
    if (!r.ok) { const e = await r.json(); $("run-meta").textContent = e.error || `Could not start the run (HTTP ${r.status}).`; return; }
    $("log").parentElement.open = true;
    poll();
  } finally { setTimeout(() => { for (const b of [$("run-local"), $("run-base")]) b.disabled = false; }, 1500); }
}

function poll() {
  clearInterval(polling);
  polling = setInterval(async () => {
    const l = await getJSON("/api/demo/log");
    $("log").textContent = l.log;
    $("log").scrollTop = $("log").scrollHeight;
    const o = await refresh();
    if (!l.running && !o.running) clearInterval(polling);
  }, 2000);
}

document.querySelectorAll(".toggle button").forEach((b) => b.addEventListener("click", () => {
  mode = b.dataset.mode;
  document.querySelectorAll(".toggle button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
  renderWeek();
}));
$("run-local").addEventListener("click", () => startRun("local"));
$("run-base").addEventListener("click", () => startRun("base-sepolia"));
refresh().then((o) => { if (o.running && !o.static_snapshot) poll(); }).catch((e) => { $("status").textContent = `API error: ${e.message}`; });
