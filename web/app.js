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
  getHistoryRuns: () => apiFetch("/api/history/runs"),
  getRunDetails: (runId) => apiFetch(`/api/history/runs/${runId}`),
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

// --- Forecast History Controller ---

async function loadHistoryView() {
  try {
    const runs = await api.getHistoryRuns();
    const tbody = el("hist-runs-tbody");
    tbody.innerHTML = "";
    if (runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted-cell">No archived runs found.</td></tr>`;
      return;
    }
    runs.forEach((r) => {
      const tr = document.createElement("tr");
      const modelDisp = r.model_type === "custom" || r.model_type === "lightgbm" ? "Custom Model" : r.model_type.toUpperCase();
      tr.innerHTML = `
        <td><code>${r.id}</code></td>
        <td><strong>${modelDisp}</strong></td>
        <td><small>${r.model_id}</small></td>
        <td>${r.series_id}</td>
        <td class="num">${r.horizon}</td>
        <td class="num">${r.execution_time_sec !== undefined ? r.execution_time_sec + "s" : "-"}</td>
        <td>${new Date(r.created_at).toLocaleDateString()}</td>
        <td><button type="button" class="btn-secondary" data-inspect-run="${r.id}">Inspect</button></td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll("[data-inspect-run]").forEach((b) => {
      b.onclick = () => inspectRun(b.dataset.inspectRun);
    });
  } catch (err) {
    showAlert(err.message);
  }
}

async function inspectRun(runId) {
  try {
    const run = await api.getRunDetails(runId);
    el("modal-run-title").textContent = `Forecast Run: ${run.id} (${run.model_type.toUpperCase()})`;
    el("hist-modal").hidden = false;

    const dates = run.values.map((v) => v.timestamp);
    const median = run.values.map((v) => v.predicted_median);
    const q10 = run.values.map((v) => v.lower_bound);
    const q90 = run.values.map((v) => v.upper_bound);

    const traces = [
      { x: dates, y: q90, type: "scatter", mode: "lines", line: { color: "transparent" }, showlegend: false },
      { x: dates, y: q10, type: "scatter", mode: "lines", fill: "tonexty", fillcolor: COLORS.intervalFill, line: { color: "transparent" }, name: "80% Interval" },
      { x: dates, y: median, type: "scatter", mode: "lines+markers", name: "Predicted Demand", line: { color: COLORS.custom, width: 2.2 } },
    ];

    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: COLORS.plotBg,
      margin: { l: 50, r: 16, t: 20, b: 36 },
      height: 420,
      font: { family: "Inter, sans-serif", size: 12 },
      xaxis: { gridcolor: COLORS.grid },
      yaxis: { gridcolor: COLORS.grid, title: "Units" },
    };

    Plotly.react("modal-chart", traces, layout, { responsive: true, displaylogo: false });
  } catch (err) {
    showAlert(err.message);
  }
}

// --- Setup & Bootstrap ---

function setupEvents() {
  initNavigation();
  initDatasetWizard();

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

  // Modal events
  el("modal-close-btn").addEventListener("click", () => {
    el("hist-modal").hidden = true;
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
