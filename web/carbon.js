// HourProof dashboard: the carbon panel (strategies, forecast vs actual intensity, the week grid, the proof card).
// Every label is set with textContent; the colors are CSS roles in styles.css (.viz-root), validated in both modes.
const $ = (id) => document.getElementById(id);
const pct = (x, d = 1) => `${(100 * x).toFixed(d)}%`;
const bps = (b) => `${(b / 100).toFixed(2)}%`;
const fmt = (n) => Math.round(n).toLocaleString("en-GB");
const tonnes = (t) => `${fmt(t)} t`;
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
let carbon = null;

export async function loadCarbon() {
  const r = await fetch("/api/carbon");
  if (r.ok) renderCarbon(await r.json());
}

function renderCarbon(c) {
  carbon = c;
  if (!c?.available) return;
  const m = c.mae;
  $("carbon-meta").textContent = `A learned day-ahead forecast of Denmark's hourly grid CO2 intensity moves 10% of each hour's load (a declared scenario parameter) into cleaner hours of the same day. Test ${c.test_period[0]} to ${c.test_period[1]}, run once with choices frozen on validation. Forecast error ${m.model.toFixed(1)} g/kWh vs ${m.lag168.toFixed(1)} for last week's value (${Math.round(100 * c.improvement_vs_best_persistence)}% lower).`;
  renderBars(c);
  renderProofCard(c.proof);
  $("co2-caveats").replaceChildren(...c.caveats.map((x) => el("li", "", x)));
  if (c.week) {
    drawLine(c.week);
    drawWeek(c.week);
  }
}

// bars: tonnes from a zero baseline; the learned forecast is emphasised, the actual-intensity run is a reference
function renderBars(c) {
  const no = c.strategies.find((s) => s.id === "no_shift").emissions_t;
  const max = Math.max(...c.strategies.map((s) => s.emissions_t));
  $("co2-bars-sub").textContent = `${c.test_hours.toLocaleString("en-GB")} hours of the IT sector's load. Bars start at zero; the differences are in the right-hand column.`;
  const bars = $("co2-bars");
  bars.replaceChildren();
  const table = $("co2-table");
  table.replaceChildren();
  const head = el("tr");
  for (const h of ["Strategy", "Emissions, t", "vs no shift", "Residual (unmatched), t", "Hourly coverage"]) head.appendChild(el("th", "", h));
  table.appendChild(head);
  for (const s of c.strategies) {
    const red = 1 - s.emissions_t / no;
    const redTxt = s.id === "no_shift" ? "—" : `−${(100 * red).toFixed(2)}%`;
    const row = el("div", `hbar${s.id === "carbon_model" ? " focus" : ""}${s.reference ? " reference" : ""}`);
    row.tabIndex = 0;
    const label = `${s.label}: ${tonnes(s.emissions_t)}${s.id === "no_shift" ? "" : `, ${(100 * red).toFixed(2)}% below no shift`}; residual (unmatched) ${tonnes(s.residual_unmatched_t)}; hourly coverage ${pct(s.coverage, 2)}`;
    row.title = label;
    row.setAttribute("aria-label", label);
    const track = el("div", "track");
    const v = el("div", "val");
    v.style.width = `${(100 * s.emissions_t / max).toFixed(2)}%`;
    track.appendChild(v);
    const num = el("span", "num", tonnes(s.emissions_t));
    if (s.id !== "no_shift") num.appendChild(el("span", "delta", redTxt));
    row.append(el("span", "name", s.label), track, num);
    bars.appendChild(row);
    const tr = el("tr");
    for (const x of [s.label, fmt(s.emissions_t), redTxt, fmt(s.residual_unmatched_t), pct(s.coverage, 2)]) tr.appendChild(el("td", "", x));
    table.appendChild(tr);
  }
}

function renderProofCard(p) {
  const card = $("proof-card");
  card.replaceChildren(el("div", "pc-label", "On-chain proof"));
  if (!p) {
    card.appendChild(el("p", "muted", "No emissions proof yet."));
    return;
  }
  const t = (kg) => (kg / 1000).toLocaleString("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  card.append(
    el("div", "pc-main", `Residual ≤ ${t(p.residual_kg)} t CO2`),
    el("div", "pc-line", `Coverage ≥ ${bps(p.coverage_bps)}`),
    el("span", "pc-private", "Hourly load: private"),
  );
  const meta = [];
  if (p.fixture_week) meta.push(`Real proof over the week of ${p.fixture_week} (Solidity test fixture).`);
  else meta.push(`${p.zk_mode === "mock" ? "MOCK verifier (test mode, not a real proof)" : "UltraHonk proof"} on ${p.network === "base-sepolia" ? "Base Sepolia" : "a local replay chain"}${p.gas ? `, ${fmt(p.gas)} gas` : ""}.`);
  if (p.target_kg !== undefined && p.target_kg !== null) {
    meta.push(`Note target ≤ ${t(p.target_kg)} t: ${p.kpi_met ? "met, base coupon" : "missed, coupon stepped up"}.`);
  }
  meta.push("The hourly intensities are public; the contract rebuilds them from the intensity oracle.");
  card.appendChild(el("div", "pc-meta", meta.join(" ")));
}

function niceTicks(hi, n = 4) {
  const step0 = hi / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= step0);
  const ticks = [];
  for (let v = 0; v <= hi + step - 1e-9; v += step) ticks.push(v);
  return ticks;
}

const SVG = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs, text) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
};

function drawLine(w) {
  const svg = $("co2-line");
  const tip = $("co2-tip");
  const wrap = $("co2-linewrap");
  const W = Math.max(wrap.clientWidth, 320);
  const H = svg.clientHeight || 220;
  const L = 40, R = 8, T = 26, B = 22;
  const n = w.intensity.length;
  const ticks = niceTicks(Math.max(...w.intensity, ...w.forecast) * 1.02);
  const ymax = ticks[ticks.length - 1];
  const x = (i) => L + (i / (n - 1)) * (W - L - R);
  const y = (v) => T + (1 - v / ymax) * (H - T - B);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.replaceChildren(svgEl("title", {}, "Hourly CO2 intensity: actual and the agent's day-ahead forecast"));
  for (const v of ticks) {
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "var(--grid)", "stroke-width": 1 }),
      svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "var(--muted)" }, String(v)));
  }
  svg.appendChild(svgEl("text", { x: 0, y: 10, "font-size": 11, fill: "var(--muted)" }, "g/kWh"));
  for (let d = 0; d < 7; d++) {
    const t = new Date(w.hours[d * 24] + "Z");
    if (d) svg.appendChild(svgEl("line", { x1: x(d * 24), x2: x(d * 24), y1: T, y2: H - B, stroke: "var(--grid)", "stroke-width": 1 }));
    svg.appendChild(svgEl("text", { x: x(d * 24 + 12), y: H - 6, "text-anchor": "middle", "font-size": 11, fill: "var(--muted)" },
      t.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", timeZone: "UTC" })));
  }
  const path = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const line = { fill: "none", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" };
  svg.append(svgEl("path", { d: path(w.forecast), stroke: "var(--series-2)", ...line }),
    svgEl("path", { d: path(w.intensity), stroke: "var(--series-1)", ...line }));
  const xl = svgEl("line", { y1: T, y2: H - B, stroke: "var(--muted)", "stroke-width": 1 });
  const da = svgEl("circle", { r: 4, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2 });
  const df = svgEl("circle", { r: 4, fill: "var(--series-2)", stroke: "var(--surface)", "stroke-width": 2 });
  const cross = svgEl("g", { visibility: "hidden" });
  cross.append(xl, df, da);
  const hit = svgEl("rect", { x: L, y: 0, width: W - L - R, height: H, fill: "transparent", tabindex: 0,
    "aria-label": "Hourly values; use the arrow keys" });
  svg.append(cross, hit);

  const hide = () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; };
  const row = (cls, v, name) => {
    const r = el("div", "t-row");
    r.append(el("span", `lk ${cls}`), el("b", "", `${Math.round(v)} g/kWh`), el("span", "muted", name));
    return r;
  };
  const show = (i) => {
    i = Math.max(0, Math.min(n - 1, i));
    cross.setAttribute("visibility", "visible");
    xl.setAttribute("x1", x(i));
    xl.setAttribute("x2", x(i));
    da.setAttribute("cx", x(i));
    da.setAttribute("cy", y(w.intensity[i]));
    df.setAttribute("cx", x(i));
    df.setAttribute("cy", y(w.forecast[i]));
    tip.replaceChildren(el("div", "t-h", `${w.hours[i].slice(0, 16)} UTC`),
      row("lk-actual", w.intensity[i], "actual"), row("lk-fc", w.forecast[i], "forecast"));
    const sh = w.shift_mwh?.[i];
    if (sh !== undefined && Math.abs(sh) > 0.05) {
      tip.appendChild(el("div", "muted", `Plan: ${sh > 0 ? "+" : "−"}${Math.abs(sh).toFixed(1)} MWh ${sh > 0 ? "moved in" : "deferred"}`));
    }
    tip.hidden = false;
    const px = (x(i) / W) * wrap.clientWidth;
    const left = px + 14 + tip.offsetWidth > wrap.clientWidth ? px - 14 - tip.offsetWidth : px + 14;
    tip.style.left = `${Math.max(0, left)}px`;
  };
  let fi = 0;
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    fi = Math.round((((e.clientX - r.left) / r.width) * W - L) / (W - L - R) * (n - 1));
    show(fi);
  });
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("focus", () => show(fi));
  hit.addEventListener("blur", hide);
  hit.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    fi = Math.max(0, Math.min(n - 1, fi + (e.key === "ArrowRight" ? 1 : -1)));
    show(fi);
    e.preventDefault();
  });
}

function drawWeek(w) {
  const grid = $("co2-week");
  grid.replaceChildren(el("div", "hr"));
  for (let h = 0; h < 24; h++) grid.appendChild(el("div", "hr", h % 3 === 0 ? String(h).padStart(2, "0") : ""));
  const lo = Math.min(...w.intensity);
  const hi = Math.max(...w.intensity);
  $("co2-scale-txt").textContent = `${Math.round(lo)} → ${Math.round(hi)} g/kWh`;
  const narrow = window.innerWidth < 760;
  for (let d = 0; d < 7; d++) {
    const t = new Date(w.hours[d * 24] + "Z");
    grid.appendChild(el("div", "day", t.toLocaleDateString("en-GB", narrow
      ? { weekday: "short", day: "numeric", timeZone: "UTC" } : { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })));
    for (let h = 0; h < 24; h++) {
      const i = d * 24 + h;
      const v = w.intensity[i];
      const f = hi > lo ? (v - lo) / (hi - lo) : 0;
      const cell = el("div", "cell");
      cell.tabIndex = 0;
      cell.style.background = `color-mix(in oklab, var(--seq-hi) ${(100 * f).toFixed(1)}%, var(--seq-lo))`;
      const sh = w.shift_mwh?.[i] ?? 0;
      const plan = Math.abs(sh) > 0.05 ? `; plan ${sh > 0 ? "+" : "−"}${Math.abs(sh).toFixed(1)} MWh` : "";
      const label = `${w.hours[i].slice(0, 16)} UTC: ${Math.round(v)} g/kWh actual, ${Math.round(w.forecast[i])} forecast${plan}`;
      cell.title = label;
      cell.setAttribute("aria-label", label);
      if (sh > 0.05) cell.appendChild(el("span", "in"));
      grid.appendChild(cell);
    }
  }
  const mae = w.mae ? ` Forecast error this week ${w.mae.model.toFixed(1)} g/kWh (last week's value: ${w.mae.lag168.toFixed(1)}).` : "";
  $("co2-caption").textContent = `Week of ${w.hours[0].slice(0, 10)} (UTC). Shading runs along the scale above, from the cleanest hour of the week to the dirtiest.${mae} Source: ${w.source}.`;
}

window.addEventListener("resize", () => { if (carbon?.week) drawLine(carbon.week); });
