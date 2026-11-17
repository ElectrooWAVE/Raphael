import { animate, stagger } from "https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm";

// Single application state object (no other globals).
const state = {
  seriesByProduct: new Map(),
  selectedProduct: "",
  selectedStore: "",
  horizon: 28,
  rangeKey: "ALL",
  history: null,
  forecast: null,
  loadingInitial: true,
  loadingForecast: false,
  error: "",
  animToken: 0,
  rafId: 0,
};

const COLORS = {
  primary: "#1F4E79",
  forecast: "#C2571A",
  intervalFill: "rgba(194, 87, 26, 0.14)",
  grid: "#E4DDD3",
  plotBg: "#F6F3EE",
  sliderBg: "#E6E1D8",
  border: "#D9D2C7",
  tick: "#475467",
  text: "#1F2933",
};

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const dec1Fmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function el(id) {
  return document.getElementById(id);
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// --- Formatters ---

function formatDate(isoDate) {
  return dateFmt.format(new Date(`${isoDate}T00:00:00Z`));
}

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function currentSeriesId() {
  return `${state.selectedProduct} | ${state.selectedStore}`;
}

// --- API module ---

async function apiFetch(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("Cannot reach the server. Is it running?");
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload && payload.detail ? String(payload.detail) : `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return payload;
}

const api = {
  getSeries: () => apiFetch("/api/series"),
  getHistory: (seriesId) => apiFetch(`/api/history?series_id=${encodeURIComponent(seriesId)}`),
  postForecast: (seriesId, horizon) =>
    apiFetch("/api/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series_id: seriesId, horizon }),
    }),
};

// --- State helpers ---

function buildProductStoreMap(seriesIds) {
  const map = new Map();
  for (const sid of seriesIds) {
    const parts = sid.split(" | ");
    if (parts.length !== 2) continue;
    const [product, store] = parts;
    if (!map.has(product)) map.set(product, []);
    map.get(product).push(store);
  }
  return map;
}

function computePrevPeriodChange(history, forecast) {
  if (!history || !forecast || !history.sales || !history.sales.length) return null;
  const n = forecast.dates.length;
  const recent = history.sales.slice(-n).filter((v) => v !== null && Number.isFinite(v));
  if (!recent.length) return null;
  const prevAvg = recent.reduce((acc, v) => acc + v, 0) / recent.length;
  if (prevAvg === 0) return null;
  return ((forecast.daily_average - prevAvg) / prevAvg) * 100;
}

function computeRangeWindow(rangeKey) {
  if (!state.history || !state.history.dates.length) return null;
  const hDates = state.history.dates;
  const endDate = state.forecast ? state.forecast.dates[state.forecast.dates.length - 1] : hDates[hDates.length - 1];
  const anchor = hDates[hDates.length - 1];

  const daysMap = { "1M": 30, "3M": 90, "6M": 180, "1Y": 365 };
  if (rangeKey === "ALL") {
    return [hDates[0], endDate];
  }
  const backDays = daysMap[rangeKey] || 180;
  return [addDays(anchor, -backDays), endDate];
}

// --- Animations module ---

function cancelAnimations() {
  state.animToken += 1;
  if (state.rafId) {
    cancelAnimationFrame(state.rafId);
    state.rafId = 0;
  }
}

function moveHorizonHighlight(instant = false) {
  const group = el("horizon-group");
  const highlight = el("horizon-highlight");
  const active = group.querySelector('button[aria-checked="true"]');
  if (!active || !highlight) return;

  const x = active.offsetLeft - 3;
  const width = active.offsetWidth;
  if (instant || reducedMotion()) {
    highlight.style.width = `${width}px`;
    highlight.style.transform = `translateX(${x}px)`;
  } else {
    animate(highlight, { x, width }, { duration: 0.22, easing: "ease-out" });
  }
}

function animateKpiCountUp(forecast, pctChange, token) {
  const totalEl = el("kpi-total-value");
  const avgEl = el("kpi-avg-value");
  const changeEl = el("kpi-change-value");

  if (reducedMotion()) {
    totalEl.textContent = intFmt.format(Math.round(forecast.total));
    avgEl.textContent = dec1Fmt.format(forecast.daily_average);
    if (pctChange === null) {
      changeEl.textContent = "n/a";
    } else {
      changeEl.textContent = `${pctChange >= 0 ? "+" : ""}${dec1Fmt.format(pctChange)}%`;
    }
    return;
  }

  animate(0, forecast.total, {
    duration: 0.8,
    easing: "ease-out",
    onUpdate: (v) => {
      if (state.animToken !== token) return;
      totalEl.textContent = intFmt.format(Math.round(v));
    },
  });

  animate(0, forecast.daily_average, {
    duration: 0.8,
    easing: "ease-out",
    onUpdate: (v) => {
      if (state.animToken !== token) return;
      avgEl.textContent = dec1Fmt.format(v);
    },
  });

  if (pctChange === null) {
    changeEl.textContent = "n/a";
  } else {
    animate(0, pctChange, {
      duration: 0.8,
      easing: "ease-out",
      onUpdate: (v) => {
        if (state.animToken !== token) return;
        changeEl.textContent = `${v >= 0 ? "+" : ""}${dec1Fmt.format(v)}%`;
      },
    });
  }
}

function animatePanelsEntrance() {
  if (reducedMotion()) return;
  const targets = document.querySelectorAll(".kpi-block, .chart-panel");
  animate(
    targets,
    { opacity: [0.4, 1], y: [8, 0] },
    { duration: 0.35, delay: stagger(0.06), easing: "ease-out" }
  );
}

function animateForecastReveal(chartEl, forecast, token) {
  if (reducedMotion()) return;
  const totalPts = forecast.dates.length;
  const durationMs = 1200;
  const start = performance.now();

  function frame(now) {
    if (state.animToken !== token) return;
    const t = Math.min(1, (now - start) / durationMs);
    const count = Math.max(1, Math.ceil(t * totalPts));

    Plotly.restyle(
      chartEl,
      {
        x: [forecast.dates.slice(0, count)],
        y: [forecast.median.slice(0, count)],
      },
      [3]
    );
    Plotly.restyle(chartEl, { opacity: [t] }, [2]);

    if (t < 1) {
      state.rafId = requestAnimationFrame(frame);
    } else {
      state.rafId = 0;
    }
  }

  state.rafId = requestAnimationFrame(frame);
}

// --- Charts module ---

function buildChartLayout(hasForecast, forecast) {
  const win = computeRangeWindow(state.rangeKey);
  const layout = {
    template: "plotly_white",
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: COLORS.plotBg,
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: COLORS.text },
    margin: { l: 58, r: 16, t: 54, b: 30 },
    height: 440,
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "#FFFFFF",
      bordercolor: COLORS.border,
      font: { family: "Inter, system-ui, sans-serif", size: 13, color: COLORS.text },
    },
    legend: {
      orientation: "h",
      x: 0,
      y: 1.13,
      font: { size: 12, color: COLORS.text },
    },
    xaxis: {
      type: "date",
      showgrid: false,
      showspikes: false,
      hoverformat: "%a, %d %b %Y",
      tickfont: { size: 12, color: COLORS.tick },
      tickformatstops: [
        { dtickrange: [null, 1000 * 60 * 60 * 24 * 95], value: "%d %b %Y" },
        { dtickrange: [1000 * 60 * 60 * 24 * 95, 1000 * 60 * 60 * 24 * 450], value: "%b %Y" },
        { dtickrange: [1000 * 60 * 60 * 24 * 450, null], value: "%Y" },
      ],
      rangeslider: {
        visible: true,
        thickness: 0.05,
        bgcolor: COLORS.sliderBg,
        bordercolor: COLORS.border,
        borderwidth: 1,
      },
    },
    yaxis: {
      title: { text: "Units sold", font: { size: 13, color: COLORS.text } },
      tickfont: { size: 12, color: COLORS.tick },
      tickformat: ",d",
      rangemode: "tozero",
      gridcolor: COLORS.grid,
      zeroline: false,
    },
  };

  if (win) {
    layout.xaxis.range = win;
  }

  if (hasForecast && forecast) {
    layout.shapes = [
      {
        type: "line",
        x0: forecast.dates[0],
        x1: forecast.dates[0],
        y0: 0,
        y1: 1,
        yref: "paper",
        line: { color: COLORS.tick, width: 1.2, dash: "dash" },
      },
    ];
    layout.annotations = [
      {
        x: forecast.dates[0],
        y: 1,
        yref: "paper",
        text: "Forecast start",
        showarrow: false,
        xanchor: "left",
        yanchor: "bottom",
        xshift: 4,
        font: { size: 11, color: COLORS.tick },
      },
    ];
  }

  return layout;
}

function renderChart(animateReveal = false) {
  const chartEl = el("chart");
  if (!state.history || typeof Plotly === "undefined") return;

  const hDates = state.history.dates;
  const hSales = state.history.sales;
  const hasForecast = Boolean(state.forecast);

  const traces = [
    {
      x: hDates,
      y: hSales,
      type: "scatter",
      mode: "lines",
      name: "Historical sales",
      line: { color: COLORS.primary, width: 1.6 },
      hovertemplate: "Historical sales: %{y:,.1f} units<extra></extra>",
    },
  ];

  if (hasForecast) {
    const f = state.forecast;
    const initCount = animateReveal && !reducedMotion() ? 1 : f.dates.length;
    traces.push(
      {
        x: f.dates,
        y: f.q90,
        type: "scatter",
        mode: "lines",
        line: { width: 0 },
        showlegend: false,
        hoverinfo: "skip",
      },
      {
        x: f.dates,
        y: f.q10,
        type: "scatter",
        mode: "lines",
        line: { width: 0 },
        fill: "tonexty",
        fillcolor: COLORS.intervalFill,
        opacity: animateReveal && !reducedMotion() ? 0 : 1,
        name: "80% prediction interval",
        hoverinfo: "skip",
      },
      {
        x: f.dates.slice(0, initCount),
        y: f.median.slice(0, initCount),
        type: "scatter",
        mode: "lines",
        name: "Predicted demand (median)",
        line: { color: COLORS.forecast, width: 2.4 },
        hovertemplate: "Predicted demand (median): %{y:,.1f} units<extra></extra>",
      }
    );
  }

  const layout = buildChartLayout(hasForecast, state.forecast);
  Plotly.react(chartEl, traces, layout, { responsive: true, displaylogo: false });

  if (animateReveal && hasForecast) {
    animateForecastReveal(chartEl, state.forecast, state.animToken);
  }
}

// --- UI module ---

function renderControls() {
  const productSelect = el("product-select");
  const storeSelect = el("store-select");
  const generateBtn = el("generate-btn");
  const spinner = el("btn-spinner");
  const btnLabel = el("btn-label");
  const busy = state.loadingInitial || state.loadingForecast;

  productSelect.disabled = busy;
  storeSelect.disabled = busy;
  generateBtn.disabled = busy || !state.selectedProduct || !state.selectedStore;
  spinner.hidden = !state.loadingForecast;
  btnLabel.textContent = state.loadingForecast ? "Forecasting..." : "Generate Forecast";

  for (const btn of el("horizon-group").querySelectorAll("button[data-horizon]")) {
    const checked = Number(btn.dataset.horizon) === state.horizon;
    btn.setAttribute("aria-checked", String(checked));
    btn.tabIndex = checked ? 0 : -1;
    btn.disabled = busy;
  }

  for (const btn of el("range-group").querySelectorAll("button[data-range]")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.range === state.rangeKey));
    btn.disabled = busy || !state.history;
  }

  el("chart-skeleton").hidden = !state.loadingForecast;
  document.querySelector("main").setAttribute("aria-busy", String(busy));
}

function renderStatus() {
  const summaryEl = el("data-summary");
  const loadingEl = el("loading-text");
  const hintEl = el("empty-hint");
  const errorEl = el("error-banner");

  if (state.loadingInitial) {
    summaryEl.textContent = "Loading products...";
  } else if (state.history && state.history.summary) {
    const s = state.history.summary;
    summaryEl.textContent =
      `${formatDate(s.start)} to ${formatDate(s.end)} | ${intFmt.format(s.days)} days | ` +
      `${intFmt.format(s.zero_days)} zero-sales days kept | ${intFmt.format(s.missing_days)} missing days`;
  } else {
    summaryEl.textContent = "";
  }

  loadingEl.hidden = !state.loadingForecast;
  hintEl.hidden = Boolean(state.loadingInitial || state.loadingForecast || state.forecast || state.error);

  if (state.error) {
    errorEl.textContent = state.error;
    errorEl.hidden = false;
  } else {
    errorEl.textContent = "";
    errorEl.hidden = true;
  }
}

function renderKpis(animateValues = false) {
  const n = state.forecast ? state.forecast.dates.length : state.horizon;
  el("kpi-total-label").textContent = `Total predicted demand (${n} days)`;
  el("kpi-change-label").textContent = `vs previous ${n} days`;

  if (!state.forecast) {
    el("kpi-total-value").textContent = "-";
    el("kpi-avg-value").textContent = "-";
    el("kpi-change-value").textContent = "-";
    el("kpi-total-unit").hidden = true;
    el("kpi-avg-unit").hidden = true;
    return;
  }

  el("kpi-total-unit").hidden = false;
  el("kpi-avg-unit").hidden = false;
  const pct = computePrevPeriodChange(state.history, state.forecast);

  if (animateValues) {
    animateKpiCountUp(state.forecast, pct, state.animToken);
  } else {
    el("kpi-total-value").textContent = intFmt.format(Math.round(state.forecast.total));
    el("kpi-avg-value").textContent = dec1Fmt.format(state.forecast.daily_average);
    el("kpi-change-value").textContent = pct === null ? "n/a" : `${pct >= 0 ? "+" : ""}${dec1Fmt.format(pct)}%`;
  }
}

function renderStrip() {
  if (!state.history || !state.history.dates.length) {
    el("strip-last-actual").textContent = "-";
    el("strip-period").textContent = "-";
    el("strip-peak").textContent = "-";
    return;
  }

  const hDates = state.history.dates;
  el("strip-last-actual").textContent = formatDate(hDates[hDates.length - 1]);

  if (!state.forecast) {
    el("strip-period").textContent = "-";
    el("strip-peak").textContent = "-";
    return;
  }

  const f = state.forecast;
  el("strip-period").textContent = `${formatDate(f.dates[0])} - ${formatDate(f.dates[f.dates.length - 1])}`;
  let peakIdx = 0;
  for (let i = 1; i < f.median.length; i += 1) {
    if (f.median[i] > f.median[peakIdx]) peakIdx = i;
  }
  el("strip-peak").textContent = `${formatDate(f.dates[peakIdx])} (${dec1Fmt.format(f.median[peakIdx])} units)`;
}

function renderTable() {
  const tbody = el("forecast-tbody");
  const dlBtn = el("download-csv-btn");
  tbody.textContent = "";

  if (!state.forecast) {
    dlBtn.disabled = true;
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.className = "muted-cell";
    td.textContent = "Generate a forecast to view daily values.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  dlBtn.disabled = false;
  const f = state.forecast;
  for (let i = 0; i < f.dates.length; i += 1) {
    const tr = document.createElement("tr");
    const cells = [
      { text: formatDate(f.dates[i]), cls: "" },
      { text: dec1Fmt.format(f.median[i]), cls: "num" },
      { text: dec1Fmt.format(f.expected[i]), cls: "num" },
      { text: dec1Fmt.format(f.q10[i]), cls: "num" },
      { text: dec1Fmt.format(f.q90[i]), cls: "num" },
    ];
    for (const c of cells) {
      const td = document.createElement("td");
      if (c.cls) td.className = c.cls;
      td.textContent = c.text;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function renderAbout() {
  const pill = el("device-pill");
  if (state.forecast) {
    const dev = String(state.forecast.device || "-").toUpperCase();
    el("about-model").textContent = `Amazon Chronos-2 (${state.forecast.model})`;
    el("about-device").textContent = dev;
    pill.textContent = dev;
    pill.hidden = false;
  } else {
    el("about-model").textContent = "Amazon Chronos-2 (amazon/chronos-2)";
    el("about-device").textContent = "-";
    pill.hidden = true;
  }
}

function renderAll(options = {}) {
  renderControls();
  renderStatus();
  renderKpis(Boolean(options.animateForecast));
  renderStrip();
  renderChart(Boolean(options.animateForecast));
  renderTable();
  renderAbout();
  if (options.animateForecast) {
    animatePanelsEntrance();
  }
}

function populateProducts() {
  const select = el("product-select");
  select.textContent = "";
  const products = Array.from(state.seriesByProduct.keys()).sort();
  for (const product of products) {
    const opt = document.createElement("option");
    opt.value = product;
    opt.textContent = product;
    select.appendChild(opt);
  }
  state.selectedProduct = products[0] || "";
  select.value = state.selectedProduct;
}

function populateStores() {
  const select = el("store-select");
  select.textContent = "";
  const stores = (state.seriesByProduct.get(state.selectedProduct) || []).slice().sort();
  for (const store of stores) {
    const opt = document.createElement("option");
    opt.value = store;
    opt.textContent = store;
    select.appendChild(opt);
  }
  if (!stores.includes(state.selectedStore)) {
    state.selectedStore = stores[0] || "";
  }
  select.value = state.selectedStore;
}

// --- Events & Actions ---

async function loadSelectedHistory() {
  if (!state.selectedProduct || !state.selectedStore) return;
  cancelAnimations();
  state.forecast = null;
  state.rangeKey = "ALL";
  state.error = "";
  renderAll();

  try {
    state.history = await api.getHistory(currentSeriesId());
  } catch (err) {
    state.history = null;
    state.error = err.message;
  }
  renderAll();
}

async function handleGenerateForecast() {
  if (!state.selectedProduct || !state.selectedStore) return;
  cancelAnimations();
  const token = state.animToken;
  state.loadingForecast = true;
  state.error = "";
  renderControls();
  renderStatus();

  try {
    const res = await api.postForecast(currentSeriesId(), state.horizon);
    if (state.animToken !== token) return;
    state.forecast = res;
    state.rangeKey = "6M";
  } catch (err) {
    state.forecast = null;
    state.error = err.message;
  } finally {
    state.loadingForecast = false;
    renderAll({ animateForecast: Boolean(state.forecast && state.animToken === token) });
  }
}

function downloadForecastCsv() {
  if (!state.forecast) return;
  const f = state.forecast;
  const lines = ["date,median,expected,q10,q90"];
  for (let i = 0; i < f.dates.length; i += 1) {
    lines.push(`${f.dates[i]},${f.median[i].toFixed(2)},${f.expected[i].toFixed(2)},${f.q10[i].toFixed(2)},${f.q90[i].toFixed(2)}`);
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `forecast_${state.selectedProduct}_${state.selectedStore}_${f.dates.length}d.csv`.replace(/\s+/g, "_");
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function selectHorizon(newHorizon) {
  if (state.horizon === newHorizon) return;
  state.horizon = newHorizon;
  renderControls();
  renderKpis(false);
  moveHorizonHighlight(false);
}

function setupEvents() {
  el("product-select").addEventListener("change", (e) => {
    state.selectedProduct = e.target.value;
    populateStores();
    loadSelectedHistory();
  });

  el("store-select").addEventListener("change", (e) => {
    state.selectedStore = e.target.value;
    loadSelectedHistory();
  });

  const horizonGroup = el("horizon-group");
  horizonGroup.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-horizon]");
    if (!btn || btn.disabled) return;
    selectHorizon(Number(btn.dataset.horizon));
  });

  horizonGroup.addEventListener("keydown", (e) => {
    const buttons = Array.from(horizonGroup.querySelectorAll("button[data-horizon]"));
    const idx = buttons.indexOf(document.activeElement);
    if (idx === -1) return;
    let nextIdx = -1;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") nextIdx = (idx + 1) % buttons.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") nextIdx = (idx - 1 + buttons.length) % buttons.length;
    if (nextIdx !== -1) {
      e.preventDefault();
      buttons[nextIdx].focus();
      selectHorizon(Number(buttons[nextIdx].dataset.horizon));
    }
  });

  el("range-group").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-range]");
    if (!btn || btn.disabled) return;
    state.rangeKey = btn.dataset.range;
    renderControls();
    renderChart(false);
  });

  el("generate-btn").addEventListener("click", handleGenerateForecast);

  el("download-csv-btn").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    downloadForecastCsv();
  });

  window.addEventListener("resize", () => moveHorizonHighlight(true));
}

async function init() {
  setupEvents();
  moveHorizonHighlight(true);
  renderAll();

  try {
    const seriesIds = await api.getSeries();
    state.seriesByProduct = buildProductStoreMap(seriesIds);
    populateProducts();
    populateStores();
    state.loadingInitial = false;
    await loadSelectedHistory();
  } catch (err) {
    state.loadingInitial = false;
    state.error = err.message;
    renderAll();
  }
}

document.addEventListener("DOMContentLoaded", init);
