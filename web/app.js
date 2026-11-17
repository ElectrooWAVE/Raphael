"use strict";

// Single application state object (no other globals).
const state = {
  seriesByProduct: new Map(),
  selectedProduct: "",
  selectedStore: "",
  horizon: 28,
  history: null,
  forecast: null,
  loadingInitial: true,
  loadingForecast: false,
  error: "",
};

const COLORS = {
  primary: "#1F4E79",
  forecast: "#C2571A",
  intervalFill: "rgba(194, 87, 26, 0.15)",
  grid: "#E7E2DA",
  muted: "#667085",
  text: "#1F2933",
};

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const dec1Fmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function el(id) {
  return document.getElementById(id);
}

function formatDate(isoDate) {
  return dateFmt.format(new Date(`${isoDate}T00:00:00Z`));
}

function currentSeriesId() {
  return `${state.selectedProduct} | ${state.selectedStore}`;
}

// --- API helpers ---

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

function fetchSeriesList() {
  return apiFetch("/api/series");
}

function fetchHistory(seriesId) {
  return apiFetch(`/api/history?series_id=${encodeURIComponent(seriesId)}`);
}

function fetchForecast(seriesId, horizon) {
  return apiFetch("/api/forecast", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ series_id: seriesId, horizon }),
  });
}

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
  if (!history || !forecast || !history.sales || !history.sales.length) return "n/a";
  const n = forecast.dates.length;
  const recent = history.sales.slice(-n).filter((v) => v !== null && Number.isFinite(v));
  if (!recent.length) return "n/a";
  const prevAvg = recent.reduce((acc, v) => acc + v, 0) / recent.length;
  if (prevAvg === 0) return "n/a";
  const pct = ((forecast.daily_average - prevAvg) / prevAvg) * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${dec1Fmt.format(pct)}%`;
}

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// --- Render functions ---

function renderControls() {
  const productSelect = el("product-select");
  const storeSelect = el("store-select");
  const generateBtn = el("generate-btn");
  const busy = state.loadingInitial || state.loadingForecast;

  productSelect.disabled = busy;
  storeSelect.disabled = busy;
  generateBtn.disabled = busy || !state.selectedProduct || !state.selectedStore;

  const horizonBtns = el("horizon-group").querySelectorAll("button[data-horizon]");
  for (const btn of horizonBtns) {
    const h = Number(btn.dataset.horizon);
    const checked = h === state.horizon;
    btn.setAttribute("aria-checked", String(checked));
    btn.tabIndex = checked ? 0 : -1;
    btn.disabled = busy;
  }

  const pageEl = document.querySelector("main");
  pageEl.setAttribute("aria-busy", String(busy));
}

function renderStatus() {
  const summaryEl = el("data-summary");
  const loadingEl = el("loading-status");
  const loadingTextEl = el("loading-text");
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

  if (state.loadingForecast) {
    loadingTextEl.textContent = "Running Chronos-2 inference...";
    loadingEl.hidden = false;
  } else {
    loadingEl.hidden = true;
  }

  hintEl.hidden = Boolean(state.loadingInitial || state.loadingForecast || state.forecast || state.error);

  if (state.error) {
    errorEl.textContent = state.error;
    errorEl.hidden = false;
  } else {
    errorEl.textContent = "";
    errorEl.hidden = true;
  }
}

function renderKpis() {
  const totalLabel = el("kpi-total-label");
  const totalValue = el("kpi-total-value");
  const avgValue = el("kpi-avg-value");
  const changeLabel = el("kpi-change-label");
  const changeValue = el("kpi-change-value");

  const n = state.forecast ? state.forecast.dates.length : state.horizon;
  totalLabel.textContent = `Total predicted demand (${n} days)`;
  changeLabel.textContent = `vs previous ${n} days`;

  if (!state.forecast) {
    totalValue.textContent = "-";
    avgValue.textContent = "-";
    changeValue.textContent = "-";
    return;
  }

  totalValue.textContent = `${intFmt.format(Math.round(state.forecast.total))} units`;
  avgValue.textContent = `${dec1Fmt.format(state.forecast.daily_average)} units`;
  changeValue.textContent = computePrevPeriodChange(state.history, state.forecast);
}

function renderChart() {
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
      line: { color: COLORS.primary, width: hasForecast ? 1.5 : 1.2 },
    },
  ];

  const layout = {
    template: "plotly_white",
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, system-ui, sans-serif", size: 13, color: COLORS.text },
    margin: { l: 54, r: 16, t: 44, b: 36 },
    height: 420,
    hovermode: "x unified",
    legend: { orientation: "h", x: 0, y: 1.08 },
    xaxis: {
      showgrid: false,
      type: "date",
      rangeselector: {
        buttons: [
          { count: 1, label: "1M", step: "month", stepmode: "backward" },
          { count: 3, label: "3M", step: "month", stepmode: "backward" },
          { count: 6, label: "6M", step: "month", stepmode: "backward" },
          { count: 1, label: "1Y", step: "year", stepmode: "backward" },
          { step: "all", label: "All" },
        ],
      },
      rangeslider: { visible: true },
    },
    yaxis: {
      title: "Units sold",
      gridcolor: COLORS.grid,
      zeroline: false,
    },
  };

  if (hasForecast) {
    const f = state.forecast;
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
        name: "80% prediction interval",
        hoverinfo: "skip",
      },
      {
        x: f.dates,
        y: f.mean,
        type: "scatter",
        mode: "lines",
        name: "Predicted demand",
        line: { color: COLORS.forecast, width: 2 },
      }
    );

    const lastHistDate = hDates[hDates.length - 1];
    const viewStart = addDays(lastHistDate, -179);
    const viewEnd = f.dates[f.dates.length - 1];
    layout.xaxis.range = [viewStart, viewEnd];
    layout.shapes = [
      {
        type: "line",
        x0: f.dates[0],
        x1: f.dates[0],
        y0: 0,
        y1: 1,
        yref: "paper",
        line: { color: COLORS.muted, width: 1, dash: "dash" },
      },
    ];
  }

  Plotly.react(chartEl, traces, layout, { responsive: true, displaylogo: false });
}

function renderTable() {
  const tbody = el("forecast-tbody");
  tbody.textContent = "";

  if (!state.forecast) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "muted-cell";
    td.textContent = "Generate a forecast to view daily values.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  const f = state.forecast;
  for (let i = 0; i < f.dates.length; i += 1) {
    const tr = document.createElement("tr");
    const cells = [
      { text: formatDate(f.dates[i]), cls: "" },
      { text: dec1Fmt.format(f.mean[i]), cls: "num" },
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
  const modelEl = el("about-model");
  const deviceEl = el("about-device");
  if (state.forecast) {
    modelEl.textContent = `Amazon Chronos-2 (${state.forecast.model})`;
    deviceEl.textContent = String(state.forecast.device || "-").toUpperCase();
  } else {
    modelEl.textContent = "Amazon Chronos-2 (amazon/chronos-2)";
    deviceEl.textContent = "-";
  }
}

function renderAll() {
  renderControls();
  renderStatus();
  renderKpis();
  renderChart();
  renderTable();
  renderAbout();
}

function populateProducts() {
  const productSelect = el("product-select");
  productSelect.textContent = "";
  const products = Array.from(state.seriesByProduct.keys()).sort();
  for (const product of products) {
    const opt = document.createElement("option");
    opt.value = product;
    opt.textContent = product;
    productSelect.appendChild(opt);
  }
  state.selectedProduct = products[0] || "";
  productSelect.value = state.selectedProduct;
}

function populateStores() {
  const storeSelect = el("store-select");
  storeSelect.textContent = "";
  const stores = (state.seriesByProduct.get(state.selectedProduct) || []).slice().sort();
  for (const store of stores) {
    const opt = document.createElement("option");
    opt.value = store;
    opt.textContent = store;
    storeSelect.appendChild(opt);
  }
  if (!stores.includes(state.selectedStore)) {
    state.selectedStore = stores[0] || "";
  }
  storeSelect.value = state.selectedStore;
}

// --- Event handlers ---

async function loadSelectedHistory() {
  if (!state.selectedProduct || !state.selectedStore) return;
  state.forecast = null;
  state.error = "";
  renderAll();

  try {
    state.history = await fetchHistory(currentSeriesId());
  } catch (err) {
    state.history = null;
    state.error = err.message;
  }
  renderAll();
}

async function handleGenerateForecast() {
  if (!state.selectedProduct || !state.selectedStore) return;
  state.loadingForecast = true;
  state.error = "";
  renderControls();
  renderStatus();

  try {
    state.forecast = await fetchForecast(currentSeriesId(), state.horizon);
  } catch (err) {
    state.forecast = null;
    state.error = err.message;
  } finally {
    state.loadingForecast = false;
    renderAll();
  }
}

function selectHorizon(newHorizon) {
  if (state.horizon === newHorizon) return;
  state.horizon = newHorizon;
  renderControls();
  renderKpis();
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
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      nextIdx = (idx + 1) % buttons.length;
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      nextIdx = (idx - 1 + buttons.length) % buttons.length;
    }
    if (nextIdx !== -1) {
      e.preventDefault();
      buttons[nextIdx].focus();
      selectHorizon(Number(buttons[nextIdx].dataset.horizon));
    }
  });

  el("generate-btn").addEventListener("click", handleGenerateForecast);
}

async function init() {
  setupEvents();
  renderAll();

  try {
    const seriesIds = await fetchSeriesList();
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
