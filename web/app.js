import { animate, stagger } from "https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm";

// Single application state object
const state = {
  activeTab: "forecasting",
  seriesByProduct: new Map(),
  selectedProduct: "",
  selectedStore: "",
  selectedModel: "chronos",
  horizon: 28,
  rangeKey: "ALL",
  history: null,
  forecast: null,
  evalMetrics: null,
  loadingInitial: true,
  loadingForecast: false,
  loadingEval: false,
  error: "",
  animToken: 0,
  rafId: 0,
  selectedFile: null,
  historyQuery: {
    seriesId: "",
    modelType: "",
    sort: "newest",
    limit: 15,
    offset: 0,
    total: 0,
  },
  inspectedRun: null,
  modalTriggerEl: null,
  pendingDeleteRunId: null,
};

const COLORS = {
  primary: "#1F4E79",
  actual: "#1F2933",
  chronos: "#1F4E79",
  custom: "#C2571A",
  baseline: "#596673",
  intervalFill: "rgba(194, 87, 26, 0.14)",
  chronosFill: "rgba(31, 78, 121, 0.12)",
  grid: "#E4DDD3",
  plotBg: "#F6F3EE",
  sliderBg: "#E6E1D8",
  border: "#D9D2C7",
  tick: "#475467",
  text: "#1F2933",
};

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const dec1Fmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dec2Fmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function el(id) {
  return document.getElementById(id);
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function formatDate(isoDate) {
  if (!isoDate) return "-";
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

// --- API Helpers ---

async function apiFetch(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("Cannot reach the server. Is it running on port 8000?");
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
  postForecast: (seriesId, horizon, modelType) =>
    apiFetch("/api/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series_id: seriesId, horizon, model_type: modelType }),
    }),
  postCompare: (seriesId, horizon, cutoffIndex) =>
    apiFetch("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series_id: seriesId, horizon, cutoff_index: cutoffIndex }),
    }),
  getOverview: () => apiFetch("/api/overview"),
  getDatasets: () => apiFetch("/api/datasets"),
  getHistoryRuns: (params = {}) => {
    const q = new URLSearchParams();
    q.set("paginated", "true");
    q.set("limit", String(params.limit ?? 15));
    q.set("offset", String(params.offset ?? 0));
    q.set("sort", params.sort || "newest");
    if (params.seriesId) q.set("series_id", params.seriesId);
    if (params.modelType) q.set("model_type", params.modelType);
    return apiFetch(`/api/history/runs?${q.toString()}`);
  },
  getRunDetails: (runId) => apiFetch(`/api/history/runs/${encodeURIComponent(runId)}`),
  deleteRun: (runId) => apiFetch(`/api/history/runs/${encodeURIComponent(runId)}`, { method: "DELETE" }),
  rerunForecast: (runId) => apiFetch(`/api/history/runs/${encodeURIComponent(runId)}/rerun`, { method: "POST" }),
  getModels: (datasetId) => apiFetch(datasetId ? `/api/models?dataset_id=${encodeURIComponent(datasetId)}` : "/api/models"),
  postTrainModel: (payload) =>
    apiFetch("/api/models/train", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getTrainStatus: (runId) => apiFetch(`/api/models/train/${runId}`),
};

function showAlert(message, type = "error") {
  const banner = el("global-alert");
  banner.textContent = message;
  banner.className = `alert-banner ${type}`;
  banner.hidden = false;
  setTimeout(() => {
    banner.hidden = true;
  }, 5000);
}

// --- State Helpers ---

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

// --- Animations ---

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
    changeEl.textContent = pctChange === null ? "n/a" : `${pctChange >= 0 ? "+" : ""}${dec1Fmt.format(pctChange)}%`;
    return;
  }

  const durationMs = 600;
  const start = performance.now();
  const targetTotal = forecast.total;
  const targetAvg = forecast.daily_average;

  function step(now) {
    if (state.animToken !== token) return;
    const progress = Math.min(1, (now - start) / durationMs);
    const ease = 1 - Math.pow(1 - progress, 3);

    totalEl.textContent = intFmt.format(Math.round(targetTotal * ease));
    avgEl.textContent = dec1Fmt.format(targetAvg * ease);

    if (progress < 1) {
      requestAnimationFrame(step);
    } else {
      totalEl.textContent = intFmt.format(Math.round(targetTotal));
      avgEl.textContent = dec1Fmt.format(targetAvg);
      changeEl.textContent = pctChange === null ? "n/a" : `${pctChange >= 0 ? "+" : ""}${dec1Fmt.format(pctChange)}%`;
    }
  }

  requestAnimationFrame(step);
}

function animatePanelsEntrance() {
  if (reducedMotion()) return;
  const targets = [el("kpi-total-value").closest(".panel"), el("kpi-avg-value").closest(".panel"), el("kpi-change-value").closest(".panel")];
  animate(targets, { opacity: [0.75, 1], y: [6, 0] }, { duration: 0.35, delay: stagger(0.06), easing: "ease-out" });
}

// --- Navigation ---

function initNavigation() {
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  document.querySelectorAll("[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.jump));
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".nav-tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === tabId);
  });
  document.querySelectorAll(".view-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `view-${tabId}`);
  });

  if (tabId === "forecasting") {
    setTimeout(() => {
      moveHorizonHighlight(true);
      renderChart(false);
    }, 50);
  } else if (tabId === "overview") {
    loadOverview();
  } else if (tabId === "training") {
    loadTrainingView();
  } else if (tabId === "comparison") {
    syncComparisonSelectors();
  } else if (tabId === "datasets") {
    loadDatasetsView();
  } else if (tabId === "history") {
    loadHistoryView();
  }
}

// --- Rendering: Forecasting View (Exact previous aesthetic) ---

function renderControls() {
  const busy = state.loadingInitial || state.loadingForecast;
  el("product-select").disabled = busy;
  el("store-select").disabled = busy;
  el("model-select").disabled = busy;
  el("generate-btn").disabled = busy || !state.selectedProduct || !state.selectedStore;

  el("btn-spinner").hidden = !state.loadingForecast;
  el("btn-label").textContent = state.loadingForecast ? "Running Inference..." : "Generate Forecast";

  const buttons = el("horizon-group").querySelectorAll("button[data-horizon]");
  buttons.forEach((btn) => {
    const val = Number(btn.dataset.horizon);
    const active = val === state.horizon;
    btn.setAttribute("aria-checked", String(active));
    btn.tabIndex = active ? 0 : -1;
    btn.disabled = busy;
  });

  const rangeButtons = el("range-group").querySelectorAll("button[data-range]");
  rangeButtons.forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.range === state.rangeKey));
  });
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
  }

  loadingEl.hidden = !state.loadingForecast;
  hintEl.hidden = Boolean(state.loadingInitial || state.loadingForecast || state.forecast || state.error);

  if (state.error) {
    errorEl.textContent = state.error;
    errorEl.hidden = false;
  } else {
    errorEl.hidden = true;
  }
}

function renderKpis(animateCount = false) {
  el("kpi-total-label").textContent = `Total predicted demand (${state.horizon} days)`;
  const totalUnit = el("kpi-total-unit");
  const avgUnit = el("kpi-avg-unit");

  if (!state.forecast) {
    el("kpi-total-value").textContent = "-";
    el("kpi-avg-value").textContent = "-";
    el("kpi-change-value").textContent = "-";
    totalUnit.hidden = true;
    avgUnit.hidden = true;
    return;
  }

  totalUnit.hidden = false;
  avgUnit.hidden = false;
  const pct = computePrevPeriodChange(state.history, state.forecast);

  if (animateCount) {
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

function buildChartLayout(hasForecast) {
  const win = computeRangeWindow(state.rangeKey);
  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: COLORS.plotBg,
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: COLORS.text },
    margin: { l: 58, r: 16, t: 36, b: 30 },
    height: 440,
    showlegend: true,
    legend: { orientation: "h", x: 0, y: 1.12, font: { size: 11 } },
    hovermode: "x unified",
    xaxis: {
      type: "date",
      showgrid: true,
      gridcolor: COLORS.grid,
      gridwidth: 1,
      zeroline: false,
      tickcolor: COLORS.border,
      tickfont: { color: COLORS.tick, size: 11 },
      rangeslider: { visible: false },
    },
    yaxis: {
      title: { text: "Units", font: { size: 12, color: COLORS.tick } },
      showgrid: true,
      gridcolor: COLORS.grid,
      gridwidth: 1,
      zeroline: true,
      zerolinecolor: COLORS.border,
      rangemode: "tozero",
      tickfont: { color: COLORS.tick, size: 11 },
    },
  };

  if (win) {
    layout.xaxis.range = [win[0], win[1]];
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
      name: "Actual daily sales",
      line: { color: COLORS.primary, width: 1.8 },
      hovertemplate: "Actual sales: %{y:,.0f} units<extra></extra>",
    },
  ];

  if (hasForecast) {
    const f = state.forecast;
    const modelColor = state.selectedModel === "custom" ? COLORS.custom : COLORS.chronos;
    const modelName = state.selectedModel === "custom" ? "Custom Model" : state.selectedModel === "baseline" ? "Baseline" : "Chronos-2";

    traces.push(
      {
        x: f.dates,
        y: f.q90,
        type: "scatter",
        mode: "lines",
        name: "80% interval (high)",
        line: { color: "transparent", width: 0 },
        showlegend: false,
        hoverinfo: "skip",
      },
      {
        x: f.dates,
        y: f.q10,
        type: "scatter",
        mode: "lines",
        fill: "tonexty",
        fillcolor: COLORS.intervalFill,
        name: "80% prediction interval",
        line: { color: "transparent", width: 0 },
        hovertemplate: "Interval: %{y:,.1f} - %{customdata:,.1f}<extra></extra>",
        customdata: f.q90,
      },
      {
        x: f.dates,
        y: f.median,
        type: "scatter",
        mode: "lines",
        name: `${modelName} (median)`,
        line: { color: COLORS.custom, width: 2.4 },
        hovertemplate: `${modelName}: %{y:,.1f} units<extra></extra>`,
      }
    );
  }

  const layout = buildChartLayout(hasForecast);
  Plotly.react(chartEl, traces, layout, { responsive: true, displaylogo: false });
}

function renderTable() {
  const tbody = el("forecast-tbody");
  const dlBtn = el("download-csv-btn");
  tbody.textContent = "";

  if (!state.forecast) {
    dlBtn.disabled = true;
    tbody.innerHTML = `<tr><td colspan="5" class="muted-cell">Generate a forecast to view daily values.</td></tr>`;
    return;
  }

  dlBtn.disabled = false;
  const f = state.forecast;
  for (let i = 0; i < f.dates.length; i += 1) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatDate(f.dates[i])}</td>
      <td class="num">${dec1Fmt.format(f.median[i])}</td>
      <td class="num">${dec1Fmt.format(f.expected[i])}</td>
      <td class="num">${dec1Fmt.format(f.q10[i])}</td>
      <td class="num">${dec1Fmt.format(f.q90[i])}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderAbout() {
  const pill = el("device-pill");
  const aboutModel = el("about-model");
  const aboutMethod = el("about-method");

  if (state.selectedModel === "custom") {
    aboutModel.textContent = "Custom Model (Recursive Multi-Quantile)";
    aboutMethod.textContent = "Frequency-aware lag & rolling features with Q10, Q50, Q90 quantile regression";
  } else if (state.selectedModel === "baseline") {
    aboutModel.textContent = "Seasonal Baseline (Lag 7 Seasonal-Naive)";
    aboutMethod.textContent = "Empirical seasonal benchmark";
  } else {
    aboutModel.textContent = "Amazon Chronos-2 (amazon/chronos-2)";
    aboutMethod.textContent = "Pretrained 120M foundation model, zero-shot";
  }

  if (state.forecast) {
    const dev = String(state.forecast.device || "CPU").toUpperCase();
    el("about-device").textContent = dev;
    pill.textContent = dev;
  } else {
    el("about-device").textContent = "-";
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

// --- Inline Model Evaluation Controller ---

async function handleRunEvaluation() {
  if (!state.selectedProduct || !state.selectedStore) return;
  const btn = el("run-eval-btn");
  btn.disabled = true;
  btn.textContent = "Evaluating...";

  try {
    const hist = await api.getHistory(currentSeriesId());
    const len = hist.dates.length;
    const cutoff = Math.max(30, len - state.horizon);

    const comp = await api.postCompare(currentSeriesId(), state.horizon, cutoff);
    const modelKey = state.selectedModel === "custom" ? "custom" : state.selectedModel === "baseline" ? "baseline" : "chronos";
    const m = comp.metrics[modelKey] || comp.metrics.chronos || {};

    el("eval-mae").textContent = m.mae !== undefined ? dec2Fmt.format(m.mae) : "-";
    el("eval-rmse").textContent = m.rmse !== undefined ? dec2Fmt.format(m.rmse) : "-";
    el("eval-wape").textContent = m.wape !== undefined ? (m.wape * 100).toFixed(1) + "%" : "-";
    el("eval-mase").textContent = m.mase !== undefined ? dec2Fmt.format(m.mase) : "-";
    el("eval-bias").textContent = m.bias !== undefined ? (m.bias * 100).toFixed(1) + "%" : "-";
    el("eval-coverage").textContent = m.coverage_80 !== undefined ? (m.coverage_80 * 100).toFixed(1) + "%" : "-";
    el("eval-width").textContent = m.mean_interval_width !== undefined ? dec1Fmt.format(m.mean_interval_width) : "-";

    el("eval-note").textContent = `Evaluated against ${state.horizon}-day holdout window (${comp.actual_test_dates[0]} to ${comp.actual_test_dates[comp.actual_test_dates.length - 1]}).`;
    showAlert("Evaluation completed successfully against ground truth window.", "success");
  } catch (err) {
    showAlert("Evaluation failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Evaluate on Historical Context";
  }
}

// --- Selectors & History Loading ---

function populateProducts() {
  const select = el("product-select");
  select.textContent = "";
  const products = Array.from(state.seriesByProduct.keys()).sort();
  for (const product of products) {
    select.appendChild(new Option(product, product));
  }
  state.selectedProduct = products[0] || "";
  select.value = state.selectedProduct;
}

function populateStores() {
  const select = el("store-select");
  select.textContent = "";
  const stores = (state.seriesByProduct.get(state.selectedProduct) || []).slice().sort();
  for (const store of stores) {
    select.appendChild(new Option(store, store));
  }
  if (!stores.includes(state.selectedStore)) {
    state.selectedStore = stores[0] || "";
  }
  select.value = state.selectedStore;
}

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
    const res = await api.postForecast(currentSeriesId(), state.horizon, state.selectedModel);
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

// --- Overview (Monosphere UI) Controller ---

async function loadOverview() {
  try {
    const data = await api.getOverview();
    el("ov-series").textContent = intFmt.format(data.total_series || 75);
    el("ov-records").textContent = intFmt.format(data.total_records || 143475);
    el("ov-device").textContent = String(data.device || "CPU").toUpperCase();

    const tbody = el("ov-recent-tbody");
    tbody.innerHTML = "";
    if (!data.recent_runs || data.recent_runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted-cell">No experiments recorded yet.</td></tr>`;
      return;
    }
    data.recent_runs.forEach((r) => {
      const tr = document.createElement("tr");
      const modelDisp = r.model_type === "custom" || r.model_type === "lightgbm" ? "Custom Model" : r.model_type.toUpperCase();
      tr.innerHTML = `
        <td><code>${r.id}</code></td>
        <td><strong>${modelDisp}</strong></td>
        <td>${r.series_id}</td>
        <td class="num">${r.horizon}d</td>
        <td class="num">${r.execution_time_sec !== undefined ? r.execution_time_sec + "s" : "-"}</td>
        <td>${new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch {
    // fallback
  }
}

// --- Model Comparison Controller ---

function syncComparisonSelectors() {
  const pSelect = el("cmp-product-select");
  const sSelect = el("cmp-store-select");
  pSelect.innerHTML = "";
  sSelect.innerHTML = "";

  const products = Array.from(state.seriesByProduct.keys()).sort();
  products.forEach((p) => pSelect.appendChild(new Option(p, p)));
  pSelect.value = state.selectedProduct || products[0] || "";

  const updateStores = () => {
    sSelect.innerHTML = "";
    const stores = (state.seriesByProduct.get(pSelect.value) || []).slice().sort();
    stores.forEach((s) => sSelect.appendChild(new Option(s, s)));
    sSelect.value = state.selectedStore || stores[0] || "";
  };

  updateStores();
  pSelect.onchange = updateStores;
}

async function handleRunComparison() {
  const p = el("cmp-product-select").value;
  const s = el("cmp-store-select").value;
  const sid = `${p} | ${s}`;
  const horizon = state.horizon;
  const mode = el("cmp-mode-select").value;

  const btn = el("cmp-run-btn");
  const spinner = el("cmp-spinner");
  btn.disabled = true;
  spinner.hidden = false;
  el("cmp-status-text").textContent = "Running side-by-side comparison across all 3 model engines...";

  try {
    let cutoff = undefined;
    if (mode === "historical") {
      const hist = await api.getHistory(sid);
      cutoff = Math.max(30, hist.dates.length - horizon);
    }

    const comp = await api.postCompare(sid, horizon, cutoff);
    renderComparisonChart(comp);
    renderComparisonTable(comp);
    el("cmp-status-text").textContent = `Comparison complete for ${sid} across ${horizon} days.`;
  } catch (err) {
    showAlert("Comparison error: " + err.message);
    el("cmp-status-text").textContent = "Comparison encountered an error.";
  } finally {
    btn.disabled = false;
    spinner.hidden = true;
  }
}

function renderComparisonChart(data) {
  const chartEl = el("cmp-chart");
  if (typeof Plotly === "undefined") return;

  const traces = [];

  if (data.has_ground_truth && data.actual_test_dates.length > 0) {
    traces.push({
      x: data.actual_test_dates,
      y: data.actual_test_values,
      type: "scatter",
      mode: "lines+markers",
      name: "Actual Demand",
      line: { color: COLORS.actual, width: 2.2 },
      marker: { size: 5 },
    });
  }

  const modelMap = {
    chronos: { name: "Chronos-2 (Zero-Shot)", color: COLORS.chronos, dash: "solid" },
    custom: { name: "Custom Model", color: COLORS.custom, dash: "solid" },
    lightgbm: { name: "Custom Model", color: COLORS.custom, dash: "solid" },
    baseline: { name: "Seasonal Baseline", color: COLORS.baseline, dash: "dash" },
  };

  for (const [key, fc] of Object.entries(data.forecasts)) {
    if (!fc || fc.error || !fc.median) continue;
    const info = modelMap[key] || { name: key, color: COLORS.custom, dash: "solid" };

    traces.push({
      x: fc.dates,
      y: fc.median,
      type: "scatter",
      mode: "lines",
      name: info.name,
      line: { color: info.color, width: 2.2, dash: info.dash },
    });

    if (fc.q10 && fc.q90 && key !== "baseline") {
      traces.push(
        {
          x: fc.dates,
          y: fc.q90,
          type: "scatter",
          mode: "lines",
          line: { color: "transparent" },
          showlegend: false,
          hoverinfo: "skip",
        },
        {
          x: fc.dates,
          y: fc.q10,
          type: "scatter",
          mode: "lines",
          fill: "tonexty",
          fillcolor: key === "chronos" ? COLORS.chronosFill : COLORS.intervalFill,
          line: { color: "transparent" },
          name: `${info.name} 80% Interval`,
        }
      );
    }
  }

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: COLORS.plotBg,
    margin: { l: 58, r: 16, t: 36, b: 30 },
    height: 440,
    font: { family: "Inter, sans-serif", size: 12 },
    xaxis: { gridcolor: COLORS.grid },
    yaxis: { gridcolor: COLORS.grid, title: "Units" },
    legend: { orientation: "h", y: 1.12, x: 0 },
  };

  Plotly.react(chartEl, traces, layout, { responsive: true, displaylogo: false });
}

function renderComparisonTable(data) {
  const tbody = el("cmp-metrics-tbody");
  tbody.innerHTML = "";

  const best = data.best_models || {};
  const displayNames = {
    chronos: "Amazon Chronos-2",
    custom: "Custom Model",
    lightgbm: "Custom Model",
    baseline: "Seasonal Baseline",
  };

  for (const [mkey, m] of Object.entries(data.metrics)) {
    if (!m) continue;
    const name = displayNames[mkey] || mkey;
    const tr = document.createElement("tr");

    const badgeMae = best.mae === mkey ? `<span class="badge-best">Best MAE</span>` : "";
    const badgeWape = best.wape === mkey ? `<span class="badge-best">Best WAPE</span>` : "";

    tr.innerHTML = `
      <td><strong>${name}</strong> ${badgeMae} ${badgeWape}</td>
      <td class="num">${m.mae !== undefined ? dec2Fmt.format(m.mae) : "-"}</td>
      <td class="num">${m.rmse !== undefined ? dec2Fmt.format(m.rmse) : "-"}</td>
      <td class="num">${m.wape !== undefined ? (m.wape * 100).toFixed(1) + "%" : "-"}</td>
      <td class="num">${m.mase !== undefined ? dec2Fmt.format(m.mase) : "-"}</td>
      <td class="num">${m.bias !== undefined ? (m.bias * 100).toFixed(1) + "%" : "-"}</td>
      <td class="num">${m.pinball_loss !== undefined ? dec2Fmt.format(m.pinball_loss) : "-"}</td>
      <td class="num">${m.coverage_80 !== undefined ? (m.coverage_80 * 100).toFixed(1) + "%" : "-"}</td>
      <td class="num">${m.mean_interval_width !== undefined ? dec1Fmt.format(m.mean_interval_width) : "-"}</td>
      <td class="num">${m.execution_time_sec !== undefined ? m.execution_time_sec + "s" : "-"}</td>
    `;
    tbody.appendChild(tr);
  }
}

// --- Data Management Controller ---

async function loadDatasetsView() {
  try {
    const list = await api.getDatasets();
    const tbody = el("ds-list-tbody");
    tbody.innerHTML = "";
    list.forEach((d) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${d.name}</strong><br><small class="text-muted"><code>${d.id}</code></small></td>
        <td>v${d.version_num}</td>
        <td class="num">${intFmt.format(d.num_records)}</td>
        <td class="num">${d.num_series}</td>
        <td>${d.date_start} to ${d.date_end}</td>
        <td><span class="pill">${d.quality_report ? d.quality_report.quality_status : "HEALTHY"}</span></td>
      `;
      tr.onclick = () => showDatasetQuality(d);
      tbody.appendChild(tr);
    });
  } catch (err) {
    showAlert(err.message);
  }
}

function showDatasetQuality(ds) {
  const card = el("ds-quality-card");
  const content = el("ds-quality-content");
  if (!ds.quality_report) {
    card.hidden = true;
    return;
  }
  const q = ds.quality_report;
  card.hidden = false;
  content.innerHTML = `
    <div><dt>Zero-Sales Days</dt><dd>${intFmt.format(q.zero_sales_count)}</dd></div>
    <div><dt>Negative Observations</dt><dd>${q.negative_sales_count}</dd></div>
    <div><dt>Duplicates Aggregated</dt><dd>${q.duplicate_count}</dd></div>
    <div><dt>Timeline Gaps</dt><dd>${q.gap_count}</dd></div>
  `;
}

function initDatasetWizard() {
  const dropZone = el("file-drop-zone");
  const fileInput = el("file-input");

  dropZone.onclick = () => fileInput.click();
  dropZone.ondragover = (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  };
  dropZone.ondragleave = () => dropZone.classList.remove("dragover");
  dropZone.ondrop = (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) handleFileSelected(e.dataTransfer.files[0]);
  };
  fileInput.onchange = (e) => {
    if (e.target.files.length > 0) handleFileSelected(e.target.files[0]);
  };
  el("import-form").onsubmit = handleImportSubmit;
}

async function handleFileSelected(file) {
  state.selectedFile = file;
  el("file-info-bar").hidden = false;
  el("file-name-lbl").textContent = file.name;
  el("file-size-lbl").textContent = `${(file.size / 1024).toFixed(1)} KB`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const meta = await apiFetch("/api/datasets/inspect", { method: "POST", body: formData });
    const timeSelect = el("map-time-select");
    const targetSelect = el("map-target-select");
    timeSelect.innerHTML = "";
    targetSelect.innerHTML = "";

    meta.columns.forEach((c) => {
      timeSelect.appendChild(new Option(c, c, false, c === meta.suggested_time_col));
      targetSelect.appendChild(new Option(c, c, false, c === meta.suggested_target_col));
    });

    el("map-series-input").value = (meta.suggested_series_cols || []).join(", ");
    el("map-covariates-input").value = (meta.suggested_covariates || []).join(", ");
    el("ds-name-input").value = file.name.replace(/\.[^/.]+$/, "").replace(/_/g, " ");
    el("import-form").hidden = false;
  } catch (err) {
    showAlert("File inspection failed: " + err.message);
  }
}

async function handleImportSubmit(e) {
  e.preventDefault();
  if (!state.selectedFile) return;

  const btn = el("wiz-submit-btn");
  const spinner = el("wiz-spinner");
  btn.disabled = true;
  spinner.hidden = false;

  const formData = new FormData();
  formData.append("file", state.selectedFile);
  formData.append("dataset_name", el("ds-name-input").value);
  formData.append("time_col", el("map-time-select").value);
  formData.append("target_col", el("map-target-select").value);
  formData.append("series_cols", el("map-series-input").value);
  formData.append("covariates", el("map-covariates-input").value);
  formData.append("frequency", el("map-freq-select").value);

  try {
    const res = await apiFetch("/api/datasets/import", { method: "POST", body: formData });
    showAlert(`Dataset '${res.dataset_name}' (v${res.version_num}) imported successfully!`, "success");
    el("import-form").reset();
    el("import-form").hidden = true;
    el("file-info-bar").hidden = true;
    state.selectedFile = null;
    await loadDatasetsView();
  } catch (err) {
    showAlert("Import failed: " + err.message);
  } finally {
    btn.disabled = false;
    spinner.hidden = true;
  }
}

// --- Forecast History & Run Inspector Controller ---

function populateHistorySeriesFilter() {
  const select = el("hist-filter-series");
  if (!select) return;
  const allSeries = [];
  for (const [product, stores] of state.seriesByProduct.entries()) {
    for (const store of stores) {
      allSeries.push(`${product} | ${store}`);
    }
  }
  allSeries.sort();
  const prev = state.historyQuery.seriesId;
  select.textContent = "";
  select.appendChild(new Option("All series", ""));
  for (const sid of allSeries) {
    select.appendChild(new Option(sid, sid));
  }
  select.value = allSeries.includes(prev) ? prev : "";
}

function formatDateTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function showHistoryError(msg) {
  const banner = el("hist-error-banner");
  if (!banner) return;
  if (msg) {
    banner.textContent = msg;
    banner.hidden = false;
  } else {
    banner.textContent = "";
    banner.hidden = true;
  }
}

function hideHistoryDeleteConfirm() {
  state.pendingDeleteRunId = null;
  const box = el("hist-delete-confirm");
  if (box) box.hidden = true;
}

function requestHistoryRowDelete(runId) {
  state.pendingDeleteRunId = runId;
  el("hist-delete-msg").textContent = `Delete forecast run ${runId}? This removes its stored values permanently.`;
  el("hist-delete-confirm").hidden = false;
}

async function loadHistoryView() {
  populateHistorySeriesFilter();
  showHistoryError("");
  const tbody = el("hist-runs-tbody");
  tbody.textContent = "";
  const loadTr = document.createElement("tr");
  const loadTd = document.createElement("td");
  loadTd.colSpan = 9;
  loadTd.className = "muted-cell";
  loadTd.textContent = "Loading historical runs...";
  loadTr.appendChild(loadTd);
  tbody.appendChild(loadTr);

  try {
    const q = state.historyQuery;
    const data = await api.getHistoryRuns(q);
    const runs = Array.isArray(data) ? data : data.items || [];
    const total = Array.isArray(data) ? runs.length : Number(data.total || 0);
    q.total = total;

    if (runs.length === 0 && q.offset > 0) {
      q.offset = Math.max(0, q.offset - q.limit);
      return loadHistoryView();
    }

    el("hist-total-badge").textContent = `${intFmt.format(total)} run${total === 1 ? "" : "s"}`;
    const startIdx = total === 0 ? 0 : q.offset + 1;
    const endIdx = Math.min(total, q.offset + runs.length);
    el("hist-page-info").textContent = `Showing ${startIdx}-${endIdx} of ${intFmt.format(total)}`;
    el("hist-prev-btn").disabled = q.offset <= 0;
    el("hist-next-btn").disabled = q.offset + q.limit >= total;

    tbody.textContent = "";
    if (runs.length === 0) {
      const emptyTr = document.createElement("tr");
      const emptyTd = document.createElement("td");
      emptyTd.colSpan = 9;
      emptyTd.className = "muted-cell";
      emptyTd.textContent = "No forecast runs match the current filters.";
      emptyTr.appendChild(emptyTd);
      tbody.appendChild(emptyTr);
      return;
    }

    for (const r of runs) {
      const tr = document.createElement("tr");
      const engineText = r.engine_label || (r.model_type === "lightgbm" || r.model_type === "custom" ? "Custom (LightGBM)" : String(r.model_type || "").toUpperCase());

      const tdId = document.createElement("td");
      const code = document.createElement("code");
      code.textContent = r.id;
      tdId.appendChild(code);
      tr.appendChild(tdId);

      const tdEng = document.createElement("td");
      const strong = document.createElement("strong");
      strong.textContent = engineText;
      tdEng.appendChild(strong);
      tr.appendChild(tdEng);

      const tdMod = document.createElement("td");
      tdMod.textContent = r.model_id || "-";
      tr.appendChild(tdMod);

      const tdSeries = document.createElement("td");
      tdSeries.textContent = r.series_id || "-";
      tr.appendChild(tdSeries);

      const tdHorizon = document.createElement("td");
      tdHorizon.className = "num";
      tdHorizon.textContent = `${r.horizon}d`;
      tr.appendChild(tdHorizon);

      const tdDev = document.createElement("td");
      tdDev.textContent = String(r.device || "-").toUpperCase();
      tr.appendChild(tdDev);

      const tdExec = document.createElement("td");
      tdExec.className = "num";
      tdExec.textContent = r.execution_time_sec !== null && r.execution_time_sec !== undefined ? `${r.execution_time_sec}s` : "-";
      tr.appendChild(tdExec);

      const tdCreated = document.createElement("td");
      tdCreated.textContent = formatDateTime(r.created_at);
      tr.appendChild(tdCreated);

      const tdAction = document.createElement("td");
      const actionBox = document.createElement("div");
      actionBox.className = "history-actions";

      const inspectBtn = document.createElement("button");
      inspectBtn.type = "button";
      inspectBtn.className = "btn-secondary";
      inspectBtn.textContent = "Inspect";
      inspectBtn.addEventListener("click", () => inspectRun(r.id, inspectBtn));

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn-danger-outline";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => requestHistoryRowDelete(r.id));

      actionBox.appendChild(inspectBtn);
      actionBox.appendChild(delBtn);
      tdAction.appendChild(actionBox);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    }
  } catch (err) {
    tbody.textContent = "";
    const errTr = document.createElement("tr");
    const errTd = document.createElement("td");
    errTd.colSpan = 9;
    errTd.className = "muted-cell";
    errTd.textContent = "Could not load forecast runs.";
    errTr.appendChild(errTd);
    tbody.appendChild(errTr);
    showHistoryError(err.message);
  }
}

function appendDlItem(container, term, val) {
  const wrap = document.createElement("div");
  wrap.className = container.id === "modal-meta-grid" ? "modal-meta-item" : "";
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = val;
  wrap.appendChild(dt);
  wrap.appendChild(dd);
  container.appendChild(wrap);
}

function renderModalChart(run) {
  const chartEl = el("modal-chart");
  const emptyEl = el("modal-empty");
  const values = Array.isArray(run.values) ? run.values : [];

  if (values.length === 0) {
    emptyEl.hidden = false;
    chartEl.hidden = true;
    if (typeof Plotly !== "undefined") Plotly.purge(chartEl);
    return;
  }

  emptyEl.hidden = true;
  chartEl.hidden = false;
  if (typeof Plotly === "undefined") return;

  const dates = values.map((v) => v.timestamp);
  const median = values.map((v) => v.predicted_median);
  const expected = values.map((v) => (v.expected !== null && v.expected !== undefined ? v.expected : v.predicted_median));
  const q10 = values.map((v) => v.lower_bound);
  const q90 = values.map((v) => v.upper_bound);

  const traces = [];
  const tail = run.history_tail || { dates: [], sales: [] };
  if (Array.isArray(tail.dates) && tail.dates.length > 0) {
    traces.push({
      x: tail.dates,
      y: tail.sales,
      type: "scatter",
      mode: "lines",
      name: "Historical sales",
      line: { color: COLORS.primary, width: 1.6 },
      hovertemplate: "Historical sales: %{y:,.1f} units<extra></extra>",
    });
  }

  traces.push(
    {
      x: dates,
      y: q90,
      type: "scatter",
      mode: "lines",
      line: { color: "transparent", width: 0 },
      showlegend: false,
      hoverinfo: "skip",
    },
    {
      x: dates,
      y: q10,
      type: "scatter",
      mode: "lines",
      fill: "tonexty",
      fillcolor: COLORS.intervalFill,
      line: { color: "transparent", width: 0 },
      name: "80% prediction interval",
      hovertemplate: "80% interval: %{y:,.1f} - %{customdata:,.1f} units<extra></extra>",
      customdata: q90,
    },
    {
      x: dates,
      y: median,
      type: "scatter",
      mode: "lines+markers",
      name: "Predicted demand (median)",
      line: { color: COLORS.custom, width: 2.3 },
      marker: { size: 4 },
      hovertemplate: "Median: %{y:,.1f} units<extra></extra>",
    },
    {
      x: dates,
      y: expected,
      type: "scatter",
      mode: "lines",
      name: "Expected demand",
      line: { color: COLORS.actual, width: 1.8, dash: "dot" },
      hovertemplate: "Expected: %{y:,.1f} units<extra></extra>",
    }
  );

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: COLORS.plotBg,
    margin: { l: 58, r: 16, t: 44, b: 34 },
    height: 380,
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "#FFFFFF",
      bordercolor: COLORS.border,
      font: { family: "Inter, system-ui, sans-serif", size: 13, color: COLORS.text },
    },
    legend: { orientation: "h", x: 0, y: 1.14, font: { size: 12, color: COLORS.text } },
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: COLORS.text },
    xaxis: {
      type: "date",
      gridcolor: COLORS.grid,
      showspikes: false,
      hoverformat: "%a, %d %b %Y",
      tickfont: { color: COLORS.tick, size: 12 },
    },
    yaxis: {
      gridcolor: COLORS.grid,
      title: { text: "Units sold", font: { size: 13, color: COLORS.text } },
      tickfont: { color: COLORS.tick, size: 12 },
      tickformat: ",.0f",
      rangemode: "tozero",
    },
    shapes: [
      {
        type: "line",
        x0: dates[0],
        x1: dates[0],
        y0: 0,
        y1: 1,
        yref: "paper",
        line: { color: COLORS.tick, width: 1.1, dash: "dash" },
      },
    ],
    annotations: [
      {
        x: dates[0],
        y: 1,
        yref: "paper",
        text: "Forecast start",
        showarrow: false,
        xanchor: "left",
        yanchor: "bottom",
        xshift: 4,
        font: { size: 11, color: COLORS.tick },
      },
    ],
  };

  Plotly.react(chartEl, traces, layout, { responsive: true, displaylogo: false });
}

function renderModalValuesTable(run) {
  const tbody = el("modal-values-tbody");
  tbody.textContent = "";
  const values = Array.isArray(run.values) ? run.values : [];
  if (values.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.className = "muted-cell";
    td.textContent = "No stored daily rows.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const v of values) {
    const tr = document.createElement("tr");
    const expVal = v.expected !== null && v.expected !== undefined ? v.expected : v.predicted_median;
    const cells = [
      { text: formatDate(v.timestamp), cls: "" },
      { text: v.predicted_median !== null && v.predicted_median !== undefined ? dec1Fmt.format(v.predicted_median) : "-", cls: "num" },
      { text: expVal !== null && expVal !== undefined ? dec1Fmt.format(expVal) : "-", cls: "num" },
      { text: v.lower_bound !== null && v.lower_bound !== undefined ? dec1Fmt.format(v.lower_bound) : "-", cls: "num" },
      { text: v.upper_bound !== null && v.upper_bound !== undefined ? dec1Fmt.format(v.upper_bound) : "-", cls: "num" },
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

function renderInspectedRun(run) {
  state.inspectedRun = run;
  el("modal-run-title").textContent = `Forecast Run Inspection: ${run.id}`;

  const metaGrid = el("modal-meta-grid");
  metaGrid.textContent = "";
  appendDlItem(metaGrid, "Run ID", run.id || "-");
  appendDlItem(metaGrid, "Engine", run.engine_label || run.model_type || "-");
  appendDlItem(metaGrid, "Model ID", run.model_id || "-");
  appendDlItem(metaGrid, "Series", run.series_id || "-");
  appendDlItem(metaGrid, "Horizon", `${run.horizon} days`);
  appendDlItem(metaGrid, "Device", String(run.device || "-").toUpperCase());
  appendDlItem(metaGrid, "Execution Time", run.execution_time_sec !== null && run.execution_time_sec !== undefined ? `${run.execution_time_sec}s` : "-");
  appendDlItem(metaGrid, "Created At", formatDateTime(run.created_at));

  const reproGrid = el("modal-repro-grid");
  reproGrid.textContent = "";
  const r = run.reproducibility || {};
  const pkgs = r.packages || {};
  const pkgStr = Object.entries(pkgs).map(([k, v]) => `${k}=${v}`).join(", ") || "-";
  const params = r.parameters || {};
  const ctxStr = params.context_length === null || params.context_length === undefined ? "model default" : String(params.context_length);
  const qStr = Array.isArray(params.quantile_levels) ? params.quantile_levels.join(", ") : "-";

  appendDlItem(reproGrid, "Model ID / Engine", `${r.model_id || run.model_id || "-"} (${r.engine || run.engine_label || "-"})`);
  appendDlItem(reproGrid, "Package Versions", pkgStr);
  appendDlItem(reproGrid, "Data File", r.data_file || "-");
  appendDlItem(reproGrid, "Data SHA-256", r.data_sha256 ? `${r.data_sha256.slice(0, 16)}...` : "-");
  appendDlItem(reproGrid, "Parameters", `context_length=${ctxStr}; quantiles=[${qStr}]`);
  appendDlItem(reproGrid, "Post-processing", r.post_processing || "Clip negative values at 0");

  el("modal-download-btn").disabled = !Array.isArray(run.values) || run.values.length === 0;
  el("modal-delete-confirm").hidden = true;
  el("modal-notice").textContent = "";

  renderModalChart(run);
  renderModalValuesTable(run);
}

async function inspectRun(runId, triggerEl = null) {
  state.modalTriggerEl = triggerEl || document.activeElement;
  state.inspectedRun = null;

  const modal = el("hist-modal");
  const body = el("modal-body");
  el("modal-run-title").textContent = `Forecast Run Inspection: ${runId}`;
  el("modal-loading").hidden = false;
  el("modal-error").hidden = true;
  el("modal-error").textContent = "";
  el("modal-content").hidden = true;
  modal.hidden = false;
  body.setAttribute("aria-busy", "true");
  el("modal-close-btn").focus();

  try {
    const run = await api.getRunDetails(runId);
    el("modal-loading").hidden = true;
    el("modal-content").hidden = false;
    renderInspectedRun(run);
  } catch (err) {
    el("modal-loading").hidden = true;
    el("modal-error").textContent = `Failed to load run '${runId}': ${err.message}`;
    el("modal-error").hidden = false;
  } finally {
    body.setAttribute("aria-busy", "false");
  }
}

function closeInspectModal() {
  const modal = el("hist-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  el("modal-delete-confirm").hidden = true;
  el("modal-notice").textContent = "";
  if (typeof Plotly !== "undefined") {
    Plotly.purge(el("modal-chart"));
  }
  const trigger = state.modalTriggerEl;
  state.modalTriggerEl = null;
  if (trigger && typeof trigger.focus === "function" && document.contains(trigger)) {
    trigger.focus();
  }
}

function downloadInspectedRunCsv() {
  const run = state.inspectedRun;
  if (!run || !Array.isArray(run.values) || run.values.length === 0) return;
  const lines = ["date,median,expected,q10,q90"];
  for (const v of run.values) {
    const expVal = v.expected !== null && v.expected !== undefined ? v.expected : v.predicted_median;
    lines.push(
      `${v.timestamp},${Number(v.predicted_median ?? 0).toFixed(2)},${Number(expVal ?? 0).toFixed(2)},` +
      `${Number(v.lower_bound ?? 0).toFixed(2)},${Number(v.upper_bound ?? 0).toFixed(2)}`
    );
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `run_${run.id}_${run.series_id}_${run.horizon}d.csv`.replace(/[^a-zA-Z0-9._-]+/g, "_");
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function handleModalRerun() {
  const run = state.inspectedRun;
  if (!run) return;
  const btn = el("modal-rerun-btn");
  const spinner = el("modal-rerun-spinner");
  const label = el("modal-rerun-label");
  btn.disabled = true;
  spinner.hidden = false;
  label.textContent = "Re-running...";
  el("modal-notice").textContent = "";

  try {
    const newRun = await api.rerunForecast(run.id);
    await loadHistoryView();
    await inspectRun(newRun.run_id, state.modalTriggerEl);
    el("modal-notice").textContent = `Created new run ${newRun.run_id} (original ${run.id} preserved).`;
  } catch (err) {
    el("modal-error").textContent = `Re-run failed: ${err.message}`;
    el("modal-error").hidden = false;
  } finally {
    btn.disabled = false;
    spinner.hidden = true;
    label.textContent = "Re-run with same settings";
  }
}

async function executeDeleteRun(runId, fromModal = false) {
  try {
    await api.deleteRun(runId);
    if (fromModal) {
      closeInspectModal();
    } else {
      hideHistoryDeleteConfirm();
    }
    await loadHistoryView();
    showAlert(`Deleted forecast run ${runId}.`, "success");
  } catch (err) {
    if (fromModal) {
      el("modal-error").textContent = `Delete failed: ${err.message}`;
      el("modal-error").hidden = false;
    } else {
      showHistoryError(`Delete failed: ${err.message}`);
    }
  }
}

// --- Model Training Controller ---

let trainingPollTimer = null;

async function loadTrainingView() {
  try {
    const datasets = await api.getDatasets();
    const sel = el("train-dataset-select");
    sel.innerHTML = "";
    if (!datasets || datasets.length === 0) {
      sel.innerHTML = `<option value="">No imported datasets found</option>`;
      return;
    }
    datasets.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = `${d.name} (${d.num_series} series, ${d.frequency || "D"})`;
      sel.appendChild(opt);
    });

    if (state.selectedDatasetId && datasets.some((d) => d.id === state.selectedDatasetId)) {
      sel.value = state.selectedDatasetId;
    } else {
      sel.value = datasets[0].id;
    }

    updateTrainDatasetMetadata(datasets.find((d) => d.id === sel.value));

    sel.onchange = () => {
      const ds = datasets.find((d) => d.id === sel.value);
      updateTrainDatasetMetadata(ds);
    };

    await loadTrainedModels();
  } catch (err) {
    showAlert(err.message);
  }
}

function updateTrainDatasetMetadata(ds) {
  if (!ds) return;
  el("train-info-series").textContent = ds.num_series || "--";
  el("train-info-records").textContent = intFmt.format(ds.num_records || 0);
  el("train-info-freq").textContent = ds.frequency || "D";
  el("train-info-dates").textContent = `${ds.date_start || "--"} to ${ds.date_end || "--"}`;
  el("train-info-target").textContent = ds.target_col || "--";

  if (!el("train-model-name").value) {
    el("train-model-name").value = `Custom-Model-${ds.name.replace(/\s+/g, "-")}-v1`;
  }
}

async function loadTrainedModels() {
  try {
    const models = await api.getModels();
    const tbody = el("trained-models-tbody");
    tbody.innerHTML = "";
    if (!models || models.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" class="muted-cell" style="text-align:center; padding:20px;">No custom models trained yet. Configure above and click "Start Training".</td></tr>`;
      return;
    }

    models.forEach((m) => {
      const tr = document.createElement("tr");
      const nameDisp = (m.name || "Custom Model").replace(/LightGBM/gi, "Custom Model");
      const met = m.metrics || {};
      tr.innerHTML = `
        <td><strong>${nameDisp}</strong><br><small class="text-muted"><code>${m.model_id}</code></small></td>
        <td><code>${m.dataset_id}</code></td>
        <td class="num">${m.num_series || "-"}</td>
        <td class="num">${m.num_samples ? intFmt.format(m.num_samples) : "-"}</td>
        <td class="num">${m.duration_sec !== undefined ? m.duration_sec + "s" : "-"}</td>
        <td class="num">${met.mae !== undefined ? dec2Fmt.format(met.mae) : "-"}</td>
        <td class="num">${met.rmse !== undefined ? dec2Fmt.format(met.rmse) : "-"}</td>
        <td class="num">${met.wape !== undefined ? (met.wape * 100).toFixed(1) + "%" : "-"}</td>
        <td class="num">${met.coverage_80 !== undefined ? (met.coverage_80 * 100).toFixed(1) + "%" : "-"}</td>
        <td><span class="pill" style="color:var(--success); font-weight:600;">${m.status || "COMPLETED"}</span></td>
        <td>
          <button type="button" class="btn-sm activate-model-btn" data-model-id="${m.model_id}" data-model-name="${nameDisp}" style="background:var(--surface); box-shadow:var(--neu-raised-sm); border:0; padding:4px 10px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:600; color:var(--primary);">
            Use for Forecast
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll(".activate-model-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.selectedModel = "custom";
        const modelSelect = el("model-select");
        if (modelSelect) modelSelect.value = "custom";
        switchTab("forecasting");
        showAlert(`Model "${btn.dataset.modelName}" activated for forecasting.`, "success");
      });
    });
  } catch (err) {
    showAlert("Failed to load trained models: " + err.message);
  }
}

async function handleStartTraining() {
  const datasetId = el("train-dataset-select").value;
  if (!datasetId) {
    showAlert("Please select a target dataset for training.");
    return;
  }

  const modelName = el("train-model-name").value.trim() || `Custom-Model-${datasetId}`;
  const valFraction = parseFloat(el("train-val-fraction").value) || 0.15;
  const nEstimators = parseInt(el("hp-n-estimators").value, 10) || 100;
  const learningRate = parseFloat(el("hp-learning-rate").value) || 0.05;
  const maxDepth = parseInt(el("hp-max-depth").value, 10) || 6;
  const numLeaves = parseInt(el("hp-num-leaves").value, 10) || 31;
  const minChildSamples = parseInt(el("hp-min-child").value, 10) || 20;

  const lagStr = el("train-lags").value;
  const lags = lagStr
    .split(",")
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !isNaN(n) && n > 0);

  const rollStr = el("train-rolling").value;
  const rollingWindows = rollStr
    .split(",")
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !isNaN(n) && n > 0);

  const payload = {
    dataset_id: datasetId,
    model_name: modelName,
    val_fraction: valFraction,
    n_estimators: nEstimators,
    learning_rate: learningRate,
    max_depth: maxDepth,
    num_leaves: numLeaves,
    min_child_samples: minChildSamples,
    lags: lags.length > 0 ? lags : undefined,
    rolling_windows: rollingWindows.length > 0 ? rollingWindows : undefined,
  };

  const startBtn = el("train-start-btn");
  const spinner = el("train-spinner");
  const badge = el("train-status-badge");
  const telemetryBox = el("train-telemetry-box");
  const liveStatusText = el("train-live-status-text");
  const liveElapsed = el("train-live-elapsed");
  const progressBar = el("train-progress-bar");
  const resultsPanel = el("train-results-panel");

  startBtn.disabled = true;
  spinner.hidden = false;
  badge.textContent = "TRAINING";
  badge.style.color = "var(--forecast)";
  telemetryBox.hidden = false;
  resultsPanel.hidden = true;
  liveStatusText.textContent = "Initializing dataset & engineering features...";
  progressBar.style.width = "20%";

  const startTime = performance.now();
  let elapsedSec = 0;

  if (trainingPollTimer) clearInterval(trainingPollTimer);

  const timerTicker = setInterval(() => {
    elapsedSec = ((performance.now() - startTime) / 1000).toFixed(1);
    liveElapsed.textContent = `${elapsedSec}s elapsed`;
  }, 200);

  try {
    const res = await api.postTrainModel(payload);
    const runId = res.run_id;

    trainingPollTimer = setInterval(async () => {
      try {
        const job = await api.getTrainStatus(runId);
        if (job.status === "RUNNING") {
          liveStatusText.textContent = job.progress || "Fitting recursive quantile models...";
          progressBar.style.width = "65%";
        } else if (job.status === "COMPLETED") {
          clearInterval(trainingPollTimer);
          clearInterval(timerTicker);
          trainingPollTimer = null;

          progressBar.style.width = "100%";
          liveStatusText.textContent = "Custom Model trained and validated successfully!";
          badge.textContent = "COMPLETED";
          badge.style.color = "var(--success)";
          startBtn.disabled = false;
          spinner.hidden = true;

          const m = job.metrics || {};
          el("res-val-mae").textContent = m.mae !== undefined ? dec2Fmt.format(m.mae) : "--";
          el("res-val-rmse").textContent = m.rmse !== undefined ? dec2Fmt.format(m.rmse) : "--";
          el("res-val-wape").textContent = m.wape !== undefined ? (m.wape * 100).toFixed(1) + "%" : "--";
          el("res-val-cov").textContent = m.coverage_80 !== undefined ? (m.coverage_80 * 100).toFixed(1) + "%" : "--";
          el("res-val-width").textContent = m.mean_interval_width !== undefined ? dec1Fmt.format(m.mean_interval_width) : "--";
          el("res-val-pinball").textContent = m.pinball_loss_q50 !== undefined ? dec2Fmt.format(m.pinball_loss_q50) : "--";
          resultsPanel.hidden = false;

          await loadTrainedModels();
          showAlert(`Custom model "${modelName}" successfully trained!`, "success");
        } else if (job.status === "FAILED") {
          clearInterval(trainingPollTimer);
          clearInterval(timerTicker);
          trainingPollTimer = null;

          progressBar.style.width = "100%";
          progressBar.style.background = "var(--error)";
          liveStatusText.textContent = `Training failed: ${job.error || "Unknown error"}`;
          badge.textContent = "FAILED";
          badge.style.color = "var(--error)";
          startBtn.disabled = false;
          spinner.hidden = true;
          showAlert("Model training failed: " + (job.error || "Unknown error"));
        }
      } catch (pollErr) {
        // Polling error
      }
    }, 1200);
  } catch (err) {
    clearInterval(timerTicker);
    startBtn.disabled = false;
    spinner.hidden = true;
    badge.textContent = "FAILED";
    badge.style.color = "var(--error)";
    liveStatusText.textContent = `Error: ${err.message}`;
    showAlert("Failed to start training: " + err.message);
  }
}

function initTrainingEvents() {
  const startBtn = el("train-start-btn");
  if (startBtn) startBtn.addEventListener("click", handleStartTraining);

  const refreshBtn = el("refresh-models-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", loadTrainedModels);

  const pFast = el("preset-fast");
  const pDef = el("preset-default");
  const pDeep = el("preset-deep");

  function setPreset(activeBtn, nEst, lr, depth, leaves, child) {
    [pFast, pDef, pDeep].forEach((b) => b && b.classList.remove("active"));
    if (activeBtn) activeBtn.classList.add("active");
    el("hp-n-estimators").value = nEst;
    el("hp-learning-rate").value = lr;
    el("hp-max-depth").value = depth;
    el("hp-num-leaves").value = leaves;
    el("hp-min-child").value = child;
  }

  if (pFast) pFast.addEventListener("click", () => setPreset(pFast, 50, 0.08, 4, 15, 10));
  if (pDef) pDef.addEventListener("click", () => setPreset(pDef, 100, 0.05, 6, 31, 20));
  if (pDeep) pDeep.addEventListener("click", () => setPreset(pDeep, 200, 0.03, 8, 63, 30));
}

// --- Setup & Bootstrap ---

function setupEvents() {
  initNavigation();
  initDatasetWizard();
  initTrainingEvents();

  el("product-select").addEventListener("change", (e) => {
    state.selectedProduct = e.target.value;
    populateStores();
    loadSelectedHistory();
  });

  el("store-select").addEventListener("change", (e) => {
    state.selectedStore = e.target.value;
    loadSelectedHistory();
  });

  el("model-select").addEventListener("change", (e) => {
    state.selectedModel = e.target.value;
    renderAbout();
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
  el("run-eval-btn").addEventListener("click", handleRunEvaluation);
  el("download-csv-btn").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    downloadForecastCsv();
  });

  // Comparison events
  el("cmp-horizon-group").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-horizon]");
    if (!btn) return;
    el("cmp-horizon-group").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.horizon = Number(btn.dataset.horizon);
  });
  el("cmp-run-btn").addEventListener("click", handleRunComparison);

  // History toolbar, pagination & modal events
  el("hist-filter-series").addEventListener("change", (e) => {
    state.historyQuery.seriesId = e.target.value;
    state.historyQuery.offset = 0;
    loadHistoryView();
  });
  el("hist-filter-engine").addEventListener("change", (e) => {
    state.historyQuery.modelType = e.target.value;
    state.historyQuery.offset = 0;
    loadHistoryView();
  });
  el("hist-sort-select").addEventListener("change", (e) => {
    state.historyQuery.sort = e.target.value;
    state.historyQuery.offset = 0;
    loadHistoryView();
  });
  el("hist-refresh-btn").addEventListener("click", loadHistoryView);
  el("hist-prev-btn").addEventListener("click", () => {
    state.historyQuery.offset = Math.max(0, state.historyQuery.offset - state.historyQuery.limit);
    loadHistoryView();
  });
  el("hist-next-btn").addEventListener("click", () => {
    state.historyQuery.offset += state.historyQuery.limit;
    loadHistoryView();
  });
  el("hist-delete-yes").addEventListener("click", () => {
    if (state.pendingDeleteRunId) executeDeleteRun(state.pendingDeleteRunId, false);
  });
  el("hist-delete-no").addEventListener("click", hideHistoryDeleteConfirm);

  el("modal-close-btn").addEventListener("click", closeInspectModal);
  el("hist-modal").addEventListener("click", (e) => {
    if (e.target === el("hist-modal")) closeInspectModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !el("hist-modal").hidden) {
      closeInspectModal();
    }
  });
  el("modal-download-btn").addEventListener("click", downloadInspectedRunCsv);
  el("modal-rerun-btn").addEventListener("click", handleModalRerun);
  el("modal-delete-btn").addEventListener("click", () => {
    el("modal-delete-confirm").hidden = false;
  });
  el("modal-delete-no").addEventListener("click", () => {
    el("modal-delete-confirm").hidden = true;
  });
  el("modal-delete-yes").addEventListener("click", () => {
    if (state.inspectedRun) executeDeleteRun(state.inspectedRun.id, true);
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
