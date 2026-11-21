import { animate, stagger } from "https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm";

// Single application state object
const state = {
  activeTab: "forecasting",
  seriesByProduct: new Map(),
  selectedProduct: "",
  selectedStore: "",
  selectedModel: "chronos",
  horizon: 28,
  rangeKey: "1Y",
  showMa7: false,
  useCalendarCovariates: false,
  calendarEvents: [],
  promotions: [],
  health: null,
  history: null,
  forecast: null,
  calibration: null,
  inventoryData: null,
  evalMetrics: null,
  lastComparison: null,
  cmpIntervalEngines: new Set(),
  loadingInitial: true,
  loadingForecast: false,
  loadingEval: false,
  activeDatasetLabel: "",
  error: "",
  canRetryInit: false,
  animToken: 0,
  rafId: 0,
  selectedFile: null,
  wizardMeta: null,
  wizardValidation: null,
  pendingDeleteDatasetId: null,
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
  const method = (options.method || "GET").toUpperCase();
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error(`${method} ${url} failed: Cannot reach the server. Is it running on port 8000?`);
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload && payload.detail ? String(payload.detail) : response.statusText || "Request failed";
    throw new Error(`${method} ${url} (${response.status}): ${detail}`);
  }
  return payload;
}

const api = {
  getHealth: () => apiFetch("/api/health"),
  getSeries: () => apiFetch("/api/series"),
  getHistory: (seriesId) => apiFetch(`/api/history?series_id=${encodeURIComponent(seriesId)}`),
  getCalibration: (seriesId, modelType) =>
    apiFetch(`/api/calibration?series_id=${encodeURIComponent(seriesId)}&model_type=${encodeURIComponent(modelType)}`),
  runCalibration: (seriesId, modelType, horizon) =>
    apiFetch("/api/calibration/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series_id: seriesId, model_type: modelType, horizon }),
    }),
  postForecast: (seriesId, horizon, modelType, useCalendarCovariates = false) =>
    apiFetch("/api/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        series_id: seriesId,
        horizon,
        model_type: modelType,
        use_calendar_covariates: useCalendarCovariates,
      }),
    }),
  getCalendarEvents: (seriesId) =>
    apiFetch(seriesId ? `/api/calendar/events?series_id=${encodeURIComponent(seriesId)}` : "/api/calendar/events"),
  getPromotions: () => apiFetch("/api/promotions"),
  createPromotion: (payload) =>
    apiFetch("/api/promotions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deletePromotion: (promoId) =>
    apiFetch(`/api/promotions/${encodeURIComponent(promoId)}`, { method: "DELETE" }),
  getInventory: (datasetId) =>
    apiFetch(datasetId ? `/api/inventory?dataset_id=${encodeURIComponent(datasetId)}` : "/api/inventory"),
  saveInventoryOverride: (payload) =>
    apiFetch("/api/inventory/override", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  calculateManualInventory: (payload) =>
    apiFetch("/api/inventory/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  runWhatIf: (payload) =>
    apiFetch("/api/inventory/what-if", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getAutomationSchedules: () => apiFetch("/api/automation/schedules"),
  createAutomationSchedule: (payload) =>
    apiFetch("/api/automation/schedules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  runAutomationSchedule: (scheduleId) =>
    apiFetch(`/api/automation/schedules/${encodeURIComponent(scheduleId)}/run`, { method: "POST" }),
  deleteAutomationSchedule: (scheduleId) =>
    apiFetch(`/api/automation/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" }),
  refreshInventoryForecasts: (datasetId = "retail-demand-m5", horizon = 28) =>
    apiFetch("/api/inventory/refresh-forecasts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId, horizon }),
    }),
  getInventoryRefreshStatus: (jobId) =>
    apiFetch(`/api/inventory/refresh-status/${encodeURIComponent(jobId)}`),
  postCompare: (seriesId, horizon, cutoffIndex) =>
    apiFetch("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series_id: seriesId, horizon, cutoff_index: cutoffIndex }),
    }),
  getOverview: () => apiFetch("/api/overview"),
  getDatasets: () => apiFetch("/api/datasets"),
  deleteDataset: (datasetId) => apiFetch(`/api/datasets/${encodeURIComponent(datasetId)}`, { method: "DELETE" }),
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
  } else if (tabId === "inventory") {
    loadInventoryView();
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
  const errorTextEl = el("error-text");
  const retryBtn = el("retry-init-btn");

  if (state.loadingInitial) {
    summaryEl.textContent = "Loading products...";
  } else if (state.history && state.history.summary) {
    const s = state.history.summary;
    const dsPrefix = state.activeDatasetLabel ? `Dataset: ${state.activeDatasetLabel} | ` : "";
    summaryEl.textContent =
      `${dsPrefix}${formatDate(s.start)} to ${formatDate(s.end)} | ${intFmt.format(s.days)} days | ` +
      `${intFmt.format(s.zero_days)} zero-sales days kept | ${intFmt.format(s.missing_days)} missing days`;
  } else if (state.error) {
    summaryEl.textContent = "Could not load series summary.";
  }

  loadingEl.hidden = !state.loadingForecast;
  hintEl.hidden = Boolean(state.loadingInitial || state.loadingForecast || state.forecast || state.error);

  if (state.error) {
    errorTextEl.textContent = state.error;
    retryBtn.hidden = !state.canRetryInit;
    errorEl.hidden = false;
  } else {
    errorTextEl.textContent = "";
    retryBtn.hidden = true;
    errorEl.hidden = true;
  }
}

function renderKpis(animateCount = false) {
  el("kpi-total-label").textContent = `Total predicted demand (${state.horizon} days)`;
  const totalEl = el("kpi-total-value");
  const avgEl = el("kpi-avg-value");
  const changeEl = el("kpi-change-value");
  const totalUnit = el("kpi-total-unit");
  const avgUnit = el("kpi-avg-unit");

  if (!state.forecast) {
    totalEl.textContent = "Click Generate Forecast";
    avgEl.textContent = "Click Generate Forecast";
    changeEl.textContent = "Compared after forecast";
    totalEl.classList.add("kpi-placeholder");
    avgEl.classList.add("kpi-placeholder");
    changeEl.classList.add("kpi-placeholder");
    totalUnit.hidden = true;
    avgUnit.hidden = true;
    return;
  }

  totalEl.classList.remove("kpi-placeholder");
  avgEl.classList.remove("kpi-placeholder");
  changeEl.classList.remove("kpi-placeholder");
  totalUnit.hidden = false;
  avgUnit.hidden = false;
  const pct = computePrevPeriodChange(state.history, state.forecast);

  if (animateCount) {
    animateKpiCountUp(state.forecast, pct, state.animToken);
  } else {
    totalEl.textContent = intFmt.format(Math.round(state.forecast.total));
    avgEl.textContent = dec1Fmt.format(state.forecast.daily_average);
    changeEl.textContent = pct === null ? "n/a" : `${pct >= 0 ? "+" : ""}${dec1Fmt.format(pct)}%`;
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

function computeRollingMean7(sales) {
  const out = [];
  const win = [];
  for (let i = 0; i < sales.length; i += 1) {
    const val = sales[i];
    if (val !== null && val !== undefined && Number.isFinite(val)) {
      win.push(val);
      if (win.length > 7) win.shift();
      out.push(win.reduce((a, b) => a + b, 0) / win.length);
    } else {
      out.push(null);
    }
  }
  return out;
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
    hoverlabel: {
      bgcolor: "#FFFFFF",
      bordercolor: COLORS.border,
      font: { family: "Inter, system-ui, sans-serif", size: 13, color: COLORS.text },
    },
    xaxis: {
      type: "date",
      showgrid: true,
      gridcolor: COLORS.grid,
      gridwidth: 1,
      showspikes: false,
      hoverformat: "%a, %d %b %Y",
      zeroline: false,
      tickcolor: COLORS.border,
      tickfont: { color: COLORS.tick, size: 12 },
      rangeslider: { visible: false },
    },
    yaxis: {
      title: { text: "Units sold", font: { size: 12, color: COLORS.tick } },
      showgrid: true,
      gridcolor: COLORS.grid,
      gridwidth: 1,
      zeroline: true,
      zerolinecolor: COLORS.border,
      rangemode: "tozero",
      tickformat: ",.0f",
      tickfont: { color: COLORS.tick, size: 12 },
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
      hovertemplate: "Actual sales: %{y:,.1f} units<extra></extra>",
    },
  ];

  if (state.showMa7) {
    traces.push({
      x: hDates,
      y: computeRollingMean7(hSales),
      type: "scatter",
      mode: "lines",
      name: "7-day average (actual)",
      line: { color: "#0F766E", width: 1.8, dash: "dot" },
      hovertemplate: "7-day average: %{y:,.1f} units<extra></extra>",
    });
  }

  if (hasForecast) {
    const f = state.forecast;
    const modelName = state.selectedModel === "custom" ? "Custom Model" : state.selectedModel === "baseline" ? "Seasonal Baseline" : "Chronos-2";

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
        hovertemplate: "80% interval: %{y:,.1f} - %{customdata:,.1f} units<extra></extra>",
        customdata: f.q90,
      },
      {
        x: f.dates,
        y: f.median,
        type: "scatter",
        mode: "lines",
        name: `${modelName} (median)`,
        line: { color: COLORS.custom, width: 2.4 },
        hovertemplate: `${modelName} (median): %{y:,.1f} units<extra></extra>`,
      }
    );

    if (f.promo_adjusted && Array.isArray(f.promo_adjusted.adjusted_median)) {
      traces.push({
        x: f.dates,
        y: f.promo_adjusted.adjusted_median,
        type: "scatter",
        mode: "lines",
        name: "Promo-adjusted (user assumption)",
        line: { color: "#7C3AED", width: 2, dash: "dash" },
        hovertemplate: "Promo-adjusted: %{y:,.1f} units<extra></extra>",
      });
    }
  }

  const layout = buildChartLayout(hasForecast);
  const shapes = [];
  const annotations = [];
  const minDate = hDates[0];
  const maxDate = hasForecast ? state.forecast.dates[state.forecast.dates.length - 1] : hDates[hDates.length - 1];

  // Overlay reference calendar events in forecast horizon (and recent tail)
  const calEvents = (hasForecast && state.forecast.events_in_horizon?.calendar_events) || [];
  calEvents.slice(0, 12).forEach((ev) => {
    if (ev.date >= minDate && ev.date <= maxDate) {
      shapes.push({
        type: "line",
        x0: ev.date,
        x1: ev.date,
        y0: 0,
        y1: 1,
        yref: "paper",
        line: { color: "rgba(15, 118, 110, 0.55)", width: 1.2, dash: "dot" },
      });
      annotations.push({
        x: ev.date,
        y: 0.98,
        yref: "paper",
        text: ev.event_name_1,
        showarrow: false,
        textangle: -35,
        font: { size: 10, color: "#0F766E" },
        xanchor: "left",
      });
    }
  });

  // Overlay promotion windows
  (state.promotions || []).forEach((p) => {
    const sid = currentSeriesId();
    if (p.series_id && p.series_id !== sid) return;
    if (p.end_date >= minDate && p.start_date <= maxDate) {
      shapes.push({
        type: "rect",
        x0: p.start_date,
        x1: p.end_date,
        y0: 0,
        y1: 1,
        yref: "paper",
        fillcolor: "rgba(124, 58, 237, 0.10)",
        line: { width: 1, color: "rgba(124, 58, 237, 0.4)" },
      });
    }
  });

  if (shapes.length) layout.shapes = shapes;
  if (annotations.length) layout.annotations = annotations;

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

function renderHealth() {
  const pill = el("device-pill");
  const ovDev = el("ov-device");
  if (!state.health) return;
  const label = state.health.device_label || state.health.chronos_device || "CPU";
  if (pill) pill.textContent = label;
  if (ovDev) ovDev.textContent = label;
}

function renderAbout() {
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
    el("about-device").textContent = String(state.forecast.device || "CPU").toUpperCase();
  } else {
    el("about-device").textContent = "-";
  }

  const aboutCal = el("about-calibration");
  if (aboutCal) {
    const cal = (state.forecast && state.forecast.calibration) || state.calibration;
    if (cal && cal.calibrated) {
      const rawPct = cal.raw_coverage_80 != null ? `${(cal.raw_coverage_80 * 100).toFixed(1)}%` : "-";
      const calPct = cal.calibrated_coverage_80 != null ? `${(cal.calibrated_coverage_80 * 100).toFixed(1)}%` : "-";
      aboutCal.textContent = `Calibrated (k = ${Number(cal.scale_k).toFixed(2)}, Val Cov80: ${rawPct} -> ${calPct})`;
    } else {
      aboutCal.textContent = "Uncalibrated (k = 1.00)";
    }
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
  state.calibration = null;
  state.rangeKey = "1Y";
  state.error = "";
  renderAll();

  try {
    const sid = currentSeriesId();
    const [hist, cal, promos] = await Promise.all([
      api.getHistory(sid),
      api.getCalibration(sid, state.selectedModel).catch(() => null),
      api.getPromotions().catch(() => []),
    ]);
    state.history = hist;
    state.calibration = cal;
    state.promotions = Array.isArray(promos) ? promos : [];
    renderEventsAndPromos();
  } catch (err) {
    state.history = null;
    state.error = err.message;
  }
  renderAll();
}

async function handleRunCalibration() {
  if (!state.selectedProduct || !state.selectedStore) return;
  const btn = el("calibrate-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Calibrating...";
  }
  state.error = "";
  try {
    const res = await api.runCalibration(currentSeriesId(), state.selectedModel, state.horizon);
    state.calibration = res;
    renderAbout();
  } catch (err) {
    state.error = `Calibration failed: ${err.message}`;
    renderStatus();
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Calibrate 80% Interval";
    }
  }
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
    const res = await api.postForecast(
      currentSeriesId(),
      state.horizon,
      state.selectedModel,
      state.useCalendarCovariates
    );
    if (state.animToken !== token) return;
    state.forecast = res;
    if (res && res.calibration) {
      state.calibration = res.calibration;
    }
    state.rangeKey = "6M";
    renderEventsAndPromos();
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
    const devLabel = data.device_label || data.device || "CPU";
    el("ov-device").textContent = devLabel;
    if (el("device-pill")) el("device-pill").textContent = devLabel;

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
    state.lastComparison = comp;
    const winner = (comp.best_models && comp.best_models.mae) || "chronos";
    state.cmpIntervalEngines = new Set([winner]);
    renderComparisonIntervalToggles(comp);
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

function renderComparisonIntervalToggles(data) {
  const box = el("cmp-interval-toggles");
  if (!box) return;
  box.textContent = "";
  const labels = { chronos: "Chronos-2 80% Interval", custom: "Custom Model 80% Interval" };
  for (const key of ["chronos", "custom"]) {
    const fc = data.forecasts && data.forecasts[key];
    if (!fc || fc.error || !fc.q10 || !fc.q90) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-toggle";
    btn.setAttribute("aria-pressed", String(state.cmpIntervalEngines.has(key)));
    btn.textContent = labels[key];
    btn.addEventListener("click", () => {
      if (state.cmpIntervalEngines.has(key)) state.cmpIntervalEngines.delete(key);
      else state.cmpIntervalEngines.add(key);
      btn.setAttribute("aria-pressed", String(state.cmpIntervalEngines.has(key)));
      renderComparisonChart(state.lastComparison);
    });
    box.appendChild(btn);
  }
}

function renderComparisonChart(data) {
  const chartEl = el("cmp-chart");
  if (!data || typeof Plotly === "undefined") return;

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
      hovertemplate: "Actual Demand: %{y:,.1f} units<extra></extra>",
    });
  }

  const modelMap = {
    chronos: { name: "Chronos-2 (median)", color: COLORS.chronos, dash: "solid" },
    custom: { name: "Custom Model (median)", color: COLORS.custom, dash: "solid" },
    lightgbm: { name: "Custom Model (median)", color: COLORS.custom, dash: "solid" },
    baseline: { name: "Seasonal Baseline (median)", color: COLORS.baseline, dash: "dash" },
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
      hovertemplate: `${info.name}: %{y:,.1f} units<extra></extra>`,
    });

    if (fc.q10 && fc.q90 && key !== "baseline" && state.cmpIntervalEngines.has(key)) {
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
          name: `${info.name.replace(" (median)", "")} 80% Interval`,
          hovertemplate: `${info.name.replace(" (median)", "")} 80% interval: %{y:,.1f} - %{customdata:,.1f} units<extra></extra>`,
          customdata: fc.q90,
        }
      );
    }
  }

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: COLORS.plotBg,
    margin: { l: 58, r: 16, t: 36, b: 30 },
    height: 440,
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "#FFFFFF",
      bordercolor: COLORS.border,
      font: { family: "Inter, system-ui, sans-serif", size: 13, color: COLORS.text },
    },
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

function hideDatasetDeleteConfirm() {
  state.pendingDeleteDatasetId = null;
  const box = el("ds-delete-confirm");
  if (box) box.hidden = true;
}

function requestDatasetDelete(ds) {
  state.pendingDeleteDatasetId = ds.id;
  const usedParts = [];
  if (ds.model_count > 0) usedParts.push(`${ds.model_count} trained model(s)`);
  if (ds.run_count > 0) usedParts.push(`${ds.run_count} forecast run(s)`);
  const warnText = usedParts.length > 0 ? ` Warning: used by ${usedParts.join(" and ")}.` : "";
  el("ds-delete-msg").textContent = `Delete dataset "${ds.name}" (${ds.id}) and all ${ds.version_count || ds.version_num || 1} version(s)?${warnText}`;
  el("ds-delete-confirm").hidden = false;
}

async function loadDatasetsView() {
  hideDatasetDeleteConfirm();
  try {
    const list = await api.getDatasets();
    const tbody = el("ds-list-tbody");
    tbody.textContent = "";
    if (!list || list.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.className = "muted-cell";
      td.textContent = "No datasets imported yet.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    for (const d of list) {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      const strong = document.createElement("strong");
      strong.textContent = d.name;
      const br = document.createElement("br");
      const code = document.createElement("code");
      code.textContent = d.id;
      tdName.appendChild(strong);
      tdName.appendChild(br);
      tdName.appendChild(code);
      tr.appendChild(tdName);

      const tdVer = document.createElement("td");
      tdVer.textContent = `v${d.version_num}`;
      tr.appendChild(tdVer);

      const tdRec = document.createElement("td");
      tdRec.className = "num";
      tdRec.textContent = intFmt.format(d.num_records || 0);
      tr.appendChild(tdRec);

      const tdSer = document.createElement("td");
      tdSer.className = "num";
      tdSer.textContent = intFmt.format(d.num_series || 0);
      tr.appendChild(tdSer);

      const tdCov = document.createElement("td");
      tdCov.textContent = `${d.date_start || "-"} to ${d.date_end || "-"}`;
      tr.appendChild(tdCov);

      const tdStatus = document.createElement("td");
      const pill = document.createElement("span");
      pill.className = "pill";
      pill.textContent = d.quality_report ? d.quality_report.quality_status : "HEALTHY";
      tdStatus.appendChild(pill);
      tr.appendChild(tdStatus);

      const tdAct = document.createElement("td");
      const actBox = document.createElement("div");
      actBox.className = "history-actions";

      const viewBtn = document.createElement("button");
      viewBtn.type = "button";
      viewBtn.className = "btn-secondary";
      viewBtn.textContent = "View report";
      viewBtn.addEventListener("click", () => showDatasetQuality(d));

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn-danger-outline";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => requestDatasetDelete(d));

      actBox.appendChild(viewBtn);
      actBox.appendChild(delBtn);
      tdAct.appendChild(actBox);
      tr.appendChild(tdAct);

      tbody.appendChild(tr);
    }
  } catch (err) {
    showAlert(err.message);
  }
}

function showDatasetQuality(ds) {
  const card = el("ds-quality-card");
  const content = el("ds-quality-content");
  const warnEl = el("ds-quality-warnings");
  if (!ds.quality_report) {
    card.hidden = true;
    return;
  }
  const q = ds.quality_report;
  card.hidden = false;
  el("ds-quality-title").textContent = `Data Quality Report: ${ds.name} (v${ds.version_num})`;
  content.textContent = "";
  appendDlItem(content, "Records", intFmt.format(q.num_records || 0));
  appendDlItem(content, "Series Count", intFmt.format(q.num_series || 0));
  appendDlItem(content, "Zero-Sales Days Kept", intFmt.format(q.zero_sales_count || 0));
  appendDlItem(content, "Missing Target NaNs", intFmt.format(q.missing_target_count || 0));
  appendDlItem(content, "Negative Values", intFmt.format(q.negative_sales_count || 0));
  appendDlItem(content, "Duplicates", intFmt.format(q.duplicate_count || 0));
  appendDlItem(content, "Timeline Gaps", intFmt.format(q.gap_count || 0));

  warnEl.textContent = "";
  if (Array.isArray(q.warnings) && q.warnings.length > 0) {
    const ul = document.createElement("ul");
    ul.className = "validation-list validation-warnings";
    for (const w of q.warnings) {
      const li = document.createElement("li");
      li.textContent = w;
      ul.appendChild(li);
    }
    warnEl.appendChild(ul);
  }
}

function renderPreviewTable(columns, previewRows) {
  const thead = el("file-preview-thead");
  const tbody = el("file-preview-tbody");
  thead.textContent = "";
  tbody.textContent = "";

  if (!columns || columns.length === 0) {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.textContent = "Preview";
    tr.appendChild(th);
    thead.appendChild(tr);
    const bodyTr = document.createElement("tr");
    const td = document.createElement("td");
    td.className = "muted-cell";
    td.textContent = "Select a file to preview the first 10 rows.";
    bodyTr.appendChild(td);
    tbody.appendChild(bodyTr);
    return;
  }

  const headTr = document.createElement("tr");
  for (const col of columns) {
    const th = document.createElement("th");
    th.textContent = col;
    headTr.appendChild(th);
  }
  thead.appendChild(headTr);

  if (!previewRows || previewRows.length === 0) {
    const bodyTr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = columns.length;
    td.className = "muted-cell";
    td.textContent = "File contains no preview rows.";
    bodyTr.appendChild(td);
    tbody.appendChild(bodyTr);
    return;
  }

  for (const row of previewRows) {
    const tr = document.createElement("tr");
    for (const col of columns) {
      const td = document.createElement("td");
      const val = row[col];
      td.textContent = val === null || val === undefined ? "NaN" : String(val);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function renderWizardColumnChips(meta) {
  const seriesBox = el("map-series-chips");
  const covBox = el("map-covariates-chips");
  seriesBox.textContent = "";
  covBox.textContent = "";

  const timeCol = el("map-time-select").value;
  const targetCol = el("map-target-select").value;
  const suggestedSeries = new Set(meta.suggested_series_cols || []);
  const suggestedCovs = new Set(meta.suggested_covariates || []);
  const covRoles = meta.suggested_covariate_roles || {};

  const candidateCols = meta.columns.filter((c) => c !== timeCol && c !== targetCol);
  if (candidateCols.length === 0) {
    seriesBox.innerHTML = `<span class="muted-cell">No extra columns (single-series mode)</span>`;
    covBox.innerHTML = `<span class="muted-cell">No covariate columns available</span>`;
    return;
  }

  for (const col of candidateCols) {
    const sLabel = document.createElement("label");
    sLabel.className = "chip-check";
    const sCb = document.createElement("input");
    sCb.type = "checkbox";
    sCb.value = col;
    sCb.checked = suggestedSeries.has(col);
    sCb.addEventListener("change", () => {
      syncCovariateChipDisabledState();
      clearWizardValidation();
    });
    const sSpan = document.createElement("span");
    sSpan.textContent = col;
    sLabel.appendChild(sCb);
    sLabel.appendChild(sSpan);
    seriesBox.appendChild(sLabel);

    const cWrap = document.createElement("div");
    cWrap.className = "cov-chip";
    const cLabel = document.createElement("label");
    cLabel.className = "chip-check";
    cLabel.style.boxShadow = "none";
    cLabel.style.padding = "0";
    const cCb = document.createElement("input");
    cCb.type = "checkbox";
    cCb.value = col;
    cCb.checked = suggestedCovs.has(col) && !suggestedSeries.has(col);
    cCb.addEventListener("change", clearWizardValidation);
    const cSpan = document.createElement("span");
    cSpan.textContent = col;
    cLabel.appendChild(cCb);
    cLabel.appendChild(cSpan);

    const roleSel = document.createElement("select");
    roleSel.className = "cov-role-select";
    roleSel.setAttribute("aria-label", `Covariate role for ${col}`);
    roleSel.appendChild(new Option("past-only", "past-only"));
    roleSel.appendChild(new Option("known-future", "known-future"));
    roleSel.value = covRoles[col] || "past-only";
    roleSel.addEventListener("change", clearWizardValidation);

    cWrap.appendChild(cLabel);
    cWrap.appendChild(roleSel);
    covBox.appendChild(cWrap);
  }
  syncCovariateChipDisabledState();
}

function syncCovariateChipDisabledState() {
  const selectedSeries = new Set(getSelectedSeriesCols());
  for (const wrap of el("map-covariates-chips").querySelectorAll(".cov-chip")) {
    const cb = wrap.querySelector('input[type="checkbox"]');
    const sel = wrap.querySelector("select");
    if (!cb) continue;
    const isSeries = selectedSeries.has(cb.value);
    if (isSeries) cb.checked = false;
    cb.disabled = isSeries;
    if (sel) sel.disabled = isSeries;
  }
}

function getSelectedSeriesCols() {
  return Array.from(el("map-series-chips").querySelectorAll('input[type="checkbox"]:checked')).map((cb) => cb.value);
}

function getSelectedCovariates() {
  const out = [];
  for (const wrap of el("map-covariates-chips").querySelectorAll(".cov-chip")) {
    const cb = wrap.querySelector('input[type="checkbox"]');
    const sel = wrap.querySelector("select");
    if (cb && cb.checked && !cb.disabled) {
      out.push({ name: cb.value, role: sel ? sel.value : "past-only" });
    }
  }
  return out;
}

function clearWizardValidation() {
  state.wizardValidation = null;
  const panel = el("wiz-validation-panel");
  if (panel) panel.hidden = true;
  if (state.selectedFile) el("wiz-submit-btn").disabled = false;
}

function renderValidationReport(rep) {
  state.wizardValidation = rep;
  const panel = el("wiz-validation-panel");
  const errBox = el("wiz-val-errors");
  const warnBox = el("wiz-val-warnings");
  const metricsBox = el("wiz-val-metrics");
  panel.hidden = false;

  errBox.textContent = "";
  if (rep.errors && rep.errors.length > 0) {
    errBox.hidden = false;
    const ul = document.createElement("ul");
    ul.className = "validation-list validation-errors";
    for (const e of rep.errors) {
      const li = document.createElement("li");
      li.textContent = e;
      ul.appendChild(li);
    }
    errBox.appendChild(ul);
  } else {
    errBox.hidden = true;
  }

  warnBox.textContent = "";
  if (rep.warnings && rep.warnings.length > 0) {
    warnBox.hidden = false;
    const ul = document.createElement("ul");
    ul.className = "validation-list validation-warnings";
    for (const w of rep.warnings) {
      const li = document.createElement("li");
      li.textContent = w;
      ul.appendChild(li);
    }
    warnBox.appendChild(ul);
  } else {
    warnBox.hidden = true;
  }

  metricsBox.textContent = "";
  appendDlItem(metricsBox, "Status", rep.quality_status || "-");
  appendDlItem(metricsBox, "Rows", intFmt.format(rep.num_records || 0));
  appendDlItem(metricsBox, "Series Count", intFmt.format(rep.num_series || 0));
  appendDlItem(metricsBox, "Date Range", rep.date_start ? `${rep.date_start} to ${rep.date_end}` : "-");
  appendDlItem(metricsBox, "Duplicate (Series, Date)", intFmt.format(rep.duplicate_count || 0));
  appendDlItem(metricsBox, "Missing Days (Total)", intFmt.format(rep.missing_days_total || 0));
  appendDlItem(metricsBox, "Target NaNs", intFmt.format(rep.missing_target_count || 0));
  appendDlItem(metricsBox, "Negative Values", intFmt.format(rep.negative_sales_count || 0));
  appendDlItem(metricsBox, "Zero-Sales Share", `${((rep.zero_sales_share || 0) * 100).toFixed(1)}%`);

  const covNans = rep.covariate_nan_counts || {};
  const covNanStr = Object.entries(covNans).map(([k, v]) => `${k}: ${v}`).join(", ") || "None selected";
  appendDlItem(metricsBox, "Covariate NaNs", covNanStr);

  el("wiz-submit-btn").disabled = !rep.valid;
}

function buildWizardFormData(includeDatasetName = true) {
  const fd = new FormData();
  fd.append("file", state.selectedFile);
  if (includeDatasetName) fd.append("dataset_name", el("ds-name-input").value.trim());
  fd.append("time_col", el("map-time-select").value);
  fd.append("target_col", el("map-target-select").value);
  fd.append("series_cols", getSelectedSeriesCols().join(","));
  fd.append("covariates", JSON.stringify(getSelectedCovariates()));
  fd.append("frequency", el("map-freq-select").value);
  return fd;
}

function initDatasetWizard() {
  const dropZone = el("file-drop-zone");
  const fileInput = el("file-input");

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) handleFileSelected(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleFileSelected(e.target.files[0]);
  });

  el("map-time-select").addEventListener("change", () => {
    if (state.wizardMeta) renderWizardColumnChips(state.wizardMeta);
    clearWizardValidation();
  });
  el("map-target-select").addEventListener("change", () => {
    if (state.wizardMeta) renderWizardColumnChips(state.wizardMeta);
    clearWizardValidation();
  });
  el("map-freq-select").addEventListener("change", clearWizardValidation);
  el("wiz-validate-btn").addEventListener("click", handleValidateDataset);
  el("import-form").addEventListener("submit", handleImportSubmit);
  el("ds-refresh-btn").addEventListener("click", loadDatasetsView);
  el("ds-delete-no").addEventListener("click", hideDatasetDeleteConfirm);
  el("ds-delete-yes").addEventListener("click", async () => {
    if (!state.pendingDeleteDatasetId) return;
    try {
      await api.deleteDataset(state.pendingDeleteDatasetId);
      showAlert(`Deleted dataset '${state.pendingDeleteDatasetId}'.`, "success");
      hideDatasetDeleteConfirm();
      el("ds-quality-card").hidden = true;
      await loadDatasetsView();
    } catch (err) {
      showAlert("Delete failed: " + err.message);
    }
  });
}

async function handleFileSelected(file) {
  const lower = file.name.toLowerCase();
  if (![".csv", ".xlsx", ".parquet"].some((ext) => lower.endsWith(ext))) {
    showAlert("Unsupported file extension. Please choose a .csv, .xlsx, or .parquet file.");
    return;
  }

  state.selectedFile = file;
  el("file-name-lbl").textContent = file.name;
  el("file-size-lbl").textContent = `${(file.size / 1024).toFixed(1)} KB`;
  el("file-shape-lbl").textContent = "Inspecting...";
  el("wiz-progress-text").textContent = "Inspecting columns and preview...";
  el("import-fieldset").disabled = true;
  clearWizardValidation();

  const formData = new FormData();
  formData.append("file", file);

  try {
    const meta = await apiFetch("/api/datasets/inspect", { method: "POST", body: formData });
    state.wizardMeta = meta;
    el("file-shape-lbl").textContent = `${intFmt.format(meta.num_rows)} rows | ${meta.num_columns} columns`;

    const timeSelect = el("map-time-select");
    const targetSelect = el("map-target-select");
    timeSelect.textContent = "";
    targetSelect.textContent = "";

    for (const c of meta.columns) {
      timeSelect.appendChild(new Option(c, c, false, c === meta.suggested_time_col));
      targetSelect.appendChild(new Option(c, c, false, c === meta.suggested_target_col));
    }

    el("map-freq-select").value = meta.suggested_frequency || "D";
    el("ds-name-input").value = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
    renderWizardColumnChips(meta);
    renderPreviewTable(meta.columns, meta.sample_preview);
    el("import-fieldset").disabled = false;
    el("wiz-progress-text").textContent = "Review detected columns, then click Validate or Validate & Complete Import.";
  } catch (err) {
    state.selectedFile = null;
    state.wizardMeta = null;
    el("file-shape-lbl").textContent = "Inspection failed";
    el("wiz-progress-text").textContent = "";
    renderPreviewTable([], []);
    showAlert("File inspection failed: " + err.message);
  }
}

async function handleValidateDataset() {
  if (!state.selectedFile) return null;
  const valBtn = el("wiz-validate-btn");
  valBtn.disabled = true;
  el("wiz-progress-text").textContent = "Validating data quality...";

  try {
    const report = await apiFetch("/api/datasets/validate", {
      method: "POST",
      body: buildWizardFormData(false),
    });
    renderValidationReport(report);
    el("wiz-progress-text").textContent = report.valid
      ? "Validation passed. Ready to import."
      : "Validation found blocking errors. Fix them before importing.";
    return report;
  } catch (err) {
    el("wiz-progress-text").textContent = "";
    showAlert("Validation failed: " + err.message);
    return null;
  } finally {
    valBtn.disabled = false;
  }
}

async function handleImportSubmit(e) {
  e.preventDefault();
  if (!state.selectedFile) return;

  const btn = el("wiz-submit-btn");
  const spinner = el("wiz-spinner");
  btn.disabled = true;
  spinner.hidden = false;

  try {
    const report = await handleValidateDataset();
    if (!report || !report.valid) {
      return;
    }

    el("wiz-progress-text").textContent = "Importing dataset to versioned Parquet store...";
    const res = await apiFetch("/api/datasets/import", {
      method: "POST",
      body: buildWizardFormData(true),
    });
    el("wiz-progress-text").textContent = `Imported '${res.dataset_name}' (${res.version_id}) successfully.`;
    showAlert(`Dataset '${res.dataset_name}' (v${res.version_num}) imported successfully!`, "success");
    await loadDatasetsView();
  } catch (err) {
    el("wiz-progress-text").textContent = "";
    showAlert("Import failed: " + err.message);
  } finally {
    spinner.hidden = true;
    btn.disabled = Boolean(state.wizardValidation && !state.wizardValidation.valid);
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

  el("toggle-ma7").addEventListener("change", (e) => {
    state.showMa7 = Boolean(e.target.checked);
    renderChart(false);
  });
  const calCovToggle = el("toggle-calendar-cov");
  if (calCovToggle) {
    calCovToggle.addEventListener("change", (e) => {
      state.useCalendarCovariates = Boolean(e.target.checked);
    });
  }
  const promoAddBtn = el("promo-add-btn");
  if (promoAddBtn) promoAddBtn.addEventListener("click", handleAddPromotion);

  el("generate-btn").addEventListener("click", handleGenerateForecast);
  el("retry-init-btn").addEventListener("click", () => {
    state.loadingInitial = true;
    state.error = "";
    state.canRetryInit = false;
    loadInitialForecastingData();
  });
  el("run-eval-btn").addEventListener("click", handleRunEvaluation);
  const calibrateBtn = el("calibrate-btn");
  if (calibrateBtn) calibrateBtn.addEventListener("click", handleRunCalibration);

  const invRefreshBtn = el("inv-refresh-btn");
  if (invRefreshBtn) invRefreshBtn.addEventListener("click", handleRefreshInventoryForecasts);
  const invStatusFilter = el("inv-status-filter");
  if (invStatusFilter) invStatusFilter.addEventListener("change", renderInventoryTable);
  const invSearchInput = el("inv-search-input");
  if (invSearchInput) invSearchInput.addEventListener("input", renderInventoryTable);
  const mcCalcBtn = el("mc-calc-btn");
  if (mcCalcBtn) mcCalcBtn.addEventListener("click", handleManualCalculate);

  const wiDemand = el("wi-demand-mult");
  if (wiDemand) {
    wiDemand.addEventListener("input", () => {
      if (el("wi-demand-lbl")) el("wi-demand-lbl").textContent = `${Number(wiDemand.value).toFixed(2)}x`;
    });
  }
  const wiLt = el("wi-lt-delta");
  if (wiLt) {
    wiLt.addEventListener("input", () => {
      const v = Number(wiLt.value);
      if (el("wi-lt-lbl")) el("wi-lt-lbl").textContent = `${v >= 0 ? "+" : ""}${v.toFixed(1)}d`;
    });
  }
  const wiRunBtn = el("wi-run-btn");
  if (wiRunBtn) wiRunBtn.addEventListener("click", handleRunWhatIf);
  const autoAddBtn = el("auto-add-btn");
  if (autoAddBtn) autoAddBtn.addEventListener("click", handleAddSchedule);
  el("download-csv-btn").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    downloadForecastCsv();
  });

  // Comparison events
  const cmpGroup = el("cmp-horizon-group");
  function selectCmpHorizon(btn) {
    cmpGroup.querySelectorAll("button[data-horizon]").forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-checked", "false");
      b.tabIndex = -1;
    });
    btn.classList.add("active");
    btn.setAttribute("aria-checked", "true");
    btn.tabIndex = 0;
    state.horizon = Number(btn.dataset.horizon);
  }
  cmpGroup.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-horizon]");
    if (btn) selectCmpHorizon(btn);
  });
  cmpGroup.addEventListener("keydown", (e) => {
    const buttons = Array.from(cmpGroup.querySelectorAll("button[data-horizon]"));
    const idx = buttons.indexOf(document.activeElement);
    if (idx === -1) return;
    let nextIdx = -1;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") nextIdx = (idx + 1) % buttons.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") nextIdx = (idx - 1 + buttons.length) % buttons.length;
    if (nextIdx !== -1) {
      e.preventDefault();
      buttons[nextIdx].focus();
      selectCmpHorizon(buttons[nextIdx]);
    }
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

async function loadInitialForecastingData() {
  state.loadingInitial = true;
  state.error = "";
  state.canRetryInit = false;
  renderAll();

  const [seriesRes, healthRes, datasetsRes] = await Promise.allSettled([
    api.getSeries(),
    api.getHealth(),
    api.getDatasets(),
  ]);

  if (healthRes.status === "fulfilled") {
    state.health = healthRes.value;
    renderHealth();
  } else if (el("device-pill")) {
    el("device-pill").textContent = "Device unavailable";
  }

  if (datasetsRes.status === "fulfilled" && Array.isArray(datasetsRes.value) && datasetsRes.value.length > 0) {
    const ds = datasetsRes.value[0];
    state.activeDatasetLabel = `${ds.name} (v${ds.version_num})`;
  }

  if (seriesRes.status === "rejected") {
    state.loadingInitial = false;
    state.error = seriesRes.reason ? seriesRes.reason.message : "Failed to load products.";
    state.canRetryInit = true;
    const pSel = el("product-select");
    const sSel = el("store-select");
    pSel.textContent = "";
    sSel.textContent = "";
    pSel.appendChild(new Option("Error loading products", ""));
    sSel.appendChild(new Option("Error loading stores", ""));
    renderAll();
    return;
  }

  state.seriesByProduct = buildProductStoreMap(seriesRes.value);
  populateProducts();
  populateStores();
  state.loadingInitial = false;
  await loadSelectedHistory();
}

// --- Stage 1: Inventory & Reorder Controller ---

function renderAgreementMatrix(matrix) {
  const tbody = el("inv-agreement-body");
  if (!tbody) return;
  tbody.innerHTML = "";
  const engines = ["CRITICAL", "LOW", "HEALTHY", "EXCESS"];
  const labels = ["critical", "low", "medium", "healthy"];
  engines.forEach((eng) => {
    const tr = document.createElement("tr");
    const row = matrix[eng] || {};
    tr.innerHTML = `
      <td><span class="inv-badge inv-badge-${eng.toLowerCase()}">${eng}</span></td>
      ${labels.map((lbl) => `<td class="num">${row[lbl] ?? 0}</td>`).join("")}
    `;
    tbody.appendChild(tr);
  });
}

function renderInventoryTable() {
  const tbody = el("inv-table-body");
  if (!tbody || !state.inventoryData) return;
  const statusFilter = el("inv-status-filter")?.value || "ALL";
  const search = (el("inv-search-input")?.value || "").trim().toLowerCase();
  const items = state.inventoryData.items || [];

  const filtered = items.filter((item) => {
    if (statusFilter !== "ALL" && item.status !== statusFilter) return false;
    if (search && !item.series_id.toLowerCase().includes(search)) return false;
    return true;
  });

  tbody.innerHTML = "";
  filtered.forEach((item) => {
    const tr = document.createElement("tr");
    const stClass = `inv-badge-${String(item.status || "").toLowerCase()}`;
    const ltBadge = item.low_confidence_lt
      ? `<div><span class="inv-badge inv-badge-warn">Low confidence (&lt;30 orders)</span></div>`
      : "";
    const etaText = item.has_forecast
      ? (item.eta_expected_days != null
          ? `${item.eta_expected_days.toFixed(1)}d (${item.stockout_date || "-"})`
          : (item.days_of_cover != null ? `${item.days_of_cover.toFixed(1)}d cover` : "∞"))
      : "-";

    tr.innerHTML = `
      <td><strong>${item.material}</strong><br><small style="color:var(--muted)">${item.area}</small></td>
      <td><span class="inv-badge ${stClass}">${item.status}</span></td>
      <td>${item.simulated_label}</td>
      <td class="num"><input class="inv-input-sm" data-field="on_hand" type="number" step="1" value="${item.on_hand}" /></td>
      <td class="num"><input class="inv-input-sm" data-field="in_transit" type="number" step="1" min="0" value="${item.in_transit}" /></td>
      <td class="num">${item.L_mean.toFixed(2)} &plusmn; ${item.L_std.toFixed(2)} (${item.order_count})${ltBadge}</td>
      <td class="num">${item.median_order_qty} u</td>
      <td class="num">${item.avg_daily_demand != null ? item.avg_daily_demand.toFixed(2) : "-"}</td>
      <td class="num">${item.safety_stock != null ? item.safety_stock.toFixed(1) : "-"}</td>
      <td class="num">${item.rop != null ? item.rop.toFixed(1) : "-"}</td>
      <td class="num">${item.order_up_to_S != null ? item.order_up_to_S.toFixed(1) : "-"}</td>
      <td class="num"><input class="inv-input-sm" data-field="review_period" type="number" step="1" min="1" value="${item.review_period}" /></td>
      <td class="num">
        <input class="inv-input-sm" data-field="pack_size" type="number" step="1" min="1" value="${item.pack_size}" title="Pack Size" />
        <input class="inv-input-sm" data-field="moq" type="number" step="1" min="0" value="${item.moq}" title="MOQ" style="margin-top:2px" />
      </td>
      <td class="num"><strong>${item.order_qty != null ? item.order_qty : "-"}</strong></td>
      <td class="num">${etaText}</td>
      <td><button type="button" class="btn-secondary inv-save-btn">Save</button></td>
    `;

    tr.querySelector(".inv-save-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "Saving...";
      const readNum = (field, fallback) => {
        const inp = tr.querySelector(`input[data-field="${field}"]`);
        const v = Number(inp?.value);
        return Number.isFinite(v) ? v : fallback;
      };
      try {
        await api.saveInventoryOverride({
          series_id: item.series_id,
          dataset_id: state.inventoryData.dataset_id || "retail-demand-m5",
          on_hand: readNum("on_hand", item.on_hand),
          in_transit: readNum("in_transit", item.in_transit),
          review_period: readNum("review_period", item.review_period),
          pack_size: Math.max(1, Math.round(readNum("pack_size", item.pack_size))),
          moq: Math.max(0, Math.round(readNum("moq", item.moq))),
          service_level: item.service_level || 0.95,
          excess_days_threshold: item.excess_days_threshold || 60,
        });
        await loadInventoryView();
      } catch (err) {
        state.error = `Failed to save inventory override: ${err.message}`;
        renderStatus();
      } finally {
        btn.disabled = false;
        btn.textContent = "Save";
      }
    });

    tbody.appendChild(tr);
  });
}

async function loadInventoryView() {
  try {
    const data = await api.getInventory();
    state.inventoryData = data;
    const sum = data.summary || {};
    el("inv-sum-total").textContent = sum.total ?? 0;
    el("inv-sum-critical").textContent = sum.critical ?? 0;
    el("inv-sum-low").textContent = sum.low ?? 0;
    el("inv-sum-healthy").textContent = sum.healthy ?? 0;
    el("inv-sum-excess").textContent = sum.excess ?? 0;

    const noDataBanner = el("inv-no-data-banner");
    const mainContent = el("inv-main-content");
    if (!data.has_inventory_data) {
      if (noDataBanner) noDataBanner.hidden = false;
      if (el("inv-no-data-msg")) el("inv-no-data-msg").textContent = data.message || "No inventory data for this dataset.";
      if (mainContent) mainContent.hidden = true;
      return;
    }

    if (noDataBanner) noDataBanner.hidden = true;
    if (mainContent) mainContent.hidden = false;
    renderAgreementMatrix(data.agreement_matrix || {});
    renderInventoryTable();

    const wiSelect = el("wi-series-select");
    if (wiSelect && Array.isArray(data.items) && wiSelect.options.length === 0) {
      data.items.forEach((it) => {
        wiSelect.appendChild(new Option(it.series_id, it.series_id));
      });
    }
    loadAutomationSchedules();
  } catch (err) {
    state.error = `Inventory load failed: ${err.message}`;
    renderStatus();
  }
}

async function handleRefreshInventoryForecasts() {
  const btn = el("inv-refresh-btn");
  const wrap = el("inv-progress-wrap");
  const fill = el("inv-progress-fill");
  const label = el("inv-progress-label");
  if (btn) btn.disabled = true;
  if (wrap) wrap.hidden = false;
  if (fill) fill.style.width = "2%";
  if (label) label.textContent = "Starting batch Chronos-2 forecasts for 75 series...";

  try {
    const start = await api.refreshInventoryForecasts("retail-demand-m5", 28);
    const jobId = start.job_id;
    while (true) {
      await new Promise((r) => setTimeout(r, 900));
      const st = await api.getInventoryRefreshStatus(jobId);
      const total = Math.max(1, st.total_series || 75);
      const done = st.completed_series || 0;
      const pct = Math.min(100, Math.round((done / total) * 100));
      if (fill) fill.style.width = `${pct}%`;
      if (label) {
        label.textContent = st.status === "completed"
          ? `Completed ${done}/${total} series in ${st.duration_sec}s (logged in Forecasting History).`
          : `Forecasting ${done}/${total}: ${st.current_series || "..."}`;
      }
      if (st.status === "completed") {
        await loadInventoryView();
        break;
      }
      if (st.status === "failed") {
        state.error = `Batch forecast failed: ${st.error_message || "Unknown error"}`;
        renderStatus();
        break;
      }
    }
  } catch (err) {
    state.error = `Batch refresh failed: ${err.message}`;
    renderStatus();
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleManualCalculate() {
  const num = (id, fb) => {
    const v = Number(el(id)?.value);
    return Number.isFinite(v) ? v : fb;
  };
  const out = el("mc-result");
  try {
    const res = await api.calculateManualInventory({
      on_hand: num("mc-on-hand", 0),
      in_transit: num("mc-in-transit", 0),
      daily_demand_mean: num("mc-demand-mean", 10),
      daily_demand_std: num("mc-demand-std", 3),
      lead_time_mean: num("mc-lt-mean", 4),
      lead_time_std: num("mc-lt-std", 1),
      review_period: num("mc-r", 7),
      service_level: num("mc-svc", 0.95),
      pack_size: Math.max(1, Math.round(num("mc-pack", 1))),
      moq: Math.max(0, Math.round(num("mc-moq", 0))),
    });
    if (out) {
      out.hidden = false;
      out.innerHTML = `
        <span><strong>Status:</strong> <span class="inv-badge inv-badge-${res.status.toLowerCase()}">${res.status}</span></span>
        <span><strong>Safety Stock:</strong> ${res.safety_stock.toFixed(1)} u</span>
        <span><strong>ROP:</strong> ${res.rop.toFixed(1)} u</span>
        <span><strong>Order-up-to S:</strong> ${res.order_up_to_S.toFixed(1)} u</span>
        <span><strong>Order Qty:</strong> <strong>${res.order_qty} u</strong></span>
        <span><strong>Runway ETA:</strong> ${res.eta_expected_days != null ? `${res.eta_expected_days.toFixed(1)}d` : "∞"}</span>
      `;
    }
  } catch (err) {
    state.error = `Manual calculator error: ${err.message}`;
    renderStatus();
  }
}

// --- Stage 2: Calendar Events & Promotions Controller ---

function renderEventsAndPromos() {
  const listEl = el("events-horizon-list");
  const badgeEl = el("events-horizon-badge");
  const promoListEl = el("promo-list");

  if (listEl && badgeEl) {
    const evData = state.forecast?.events_in_horizon;
    const cal = evData?.calendar_events || [];
    const prs = evData?.promotions || [];
    const total = cal.length + prs.length;
    badgeEl.textContent = `${total} in horizon`;
    if (!state.forecast) {
      listEl.textContent = "Generate a forecast to inspect events in the forecast window.";
    } else if (total === 0) {
      listEl.textContent = "No calendar events or promotions fall inside this forecast horizon.";
    } else {
      listEl.innerHTML = [
        ...cal.map((e) => `<span class="pill">${e.date}: ${e.label}</span>`),
        ...prs.map((p) => `<span class="pill pill-demo">Promo: ${p.name} (${p.start_date} to ${p.end_date}, ${p.uplift_pct >= 0 ? "+" : ""}${p.uplift_pct}% assumed)</span>`),
      ].join("");
    }
  }

  if (promoListEl) {
    const promos = state.promotions || [];
    if (promos.length === 0) {
      promoListEl.innerHTML = `<span style="color:var(--muted)">No saved promotions yet.</span>`;
    } else {
      promoListEl.innerHTML = promos
        .map(
          (p) => `
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);">
            <span>
              <strong>${p.name}</strong> (${p.series_id || "All series"}) &mdash; ${p.start_date} to ${p.end_date}
              &bull; Assumed uplift: <strong>${p.uplift_pct >= 0 ? "+" : ""}${p.uplift_pct}%</strong>
            </span>
            <button type="button" class="btn-danger-outline promo-del-btn" data-promo-id="${p.id}">Delete</button>
          </div>`
        )
        .join("");

      promoListEl.querySelectorAll(".promo-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            await api.deletePromotion(btn.dataset.promoId);
            state.promotions = await api.getPromotions();
            renderEventsAndPromos();
            renderChart(false);
          } catch (err) {
            state.error = `Delete promotion failed: ${err.message}`;
            renderStatus();
          }
        });
      });
    }
  }
}

async function loadAutomationSchedules() {
  const listEl = el("auto-schedules-list");
  if (!listEl) return;
  try {
    const data = await api.getAutomationSchedules();
    const schedules = data.schedules || [];
    const logs = data.logs || [];
    const apNote = data.apscheduler_available
      ? ""
      : `<div style="margin-bottom:8px;color:#9A3F0E;">Note: APScheduler not installed; schedules can still be saved and triggered manually via Run Now.</div>`;
    if (schedules.length === 0) {
      listEl.innerHTML = `${apNote}<span style="color:var(--muted)">No scheduled jobs yet.</span>`;
      return;
    }
    listEl.innerHTML = `${apNote}` + schedules
      .map(
        (s) => `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);">
          <span>
            <strong>${s.name}</strong> &bull; <code>${s.job_type}</code> &bull; cron <code>${s.cron_expr}</code>
            ${s.last_run_at ? `&bull; Last: ${s.last_status} (${s.last_run_at})` : ""}
          </span>
          <span style="display:inline-flex;gap:6px;">
            <button type="button" class="btn-secondary auto-run-btn" data-id="${s.id}">Run Now</button>
            <button type="button" class="btn-danger-outline auto-del-btn" data-id="${s.id}">Delete</button>
          </span>
        </div>`
      )
      .join("") + (logs.length ? `<div style="margin-top:8px;color:var(--muted);">Latest log: ${logs[0].created_at} &mdash; ${logs[0].message}</div>` : "");

    listEl.querySelectorAll(".auto-run-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await api.runAutomationSchedule(btn.dataset.id);
          await loadAutomationSchedules();
        } catch (err) {
          state.error = `Run schedule failed: ${err.message}`;
          renderStatus();
        } finally {
          btn.disabled = false;
        }
      });
    });

    listEl.querySelectorAll(".auto-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api.deleteAutomationSchedule(btn.dataset.id);
          await loadAutomationSchedules();
        } catch (err) {
          state.error = `Delete schedule failed: ${err.message}`;
          renderStatus();
        }
      });
    });
  } catch (err) {
    listEl.innerHTML = `<span style="color:var(--error)">Could not load schedules: ${err.message}</span>`;
  }
}

async function handleAddSchedule() {
  const name = (el("auto-name")?.value || "").trim();
  const jobType = el("auto-job-type")?.value || "batch_forecast_refresh";
  const cronExpr = (el("auto-cron")?.value || "0 6 * * *").trim();
  if (!name) {
    state.error = "Schedule name is required.";
    renderStatus();
    return;
  }
  state.error = "";
  try {
    await api.createAutomationSchedule({ name, job_type: jobType, cron_expr: cronExpr });
    if (el("auto-name")) el("auto-name").value = "";
    await loadAutomationSchedules();
  } catch (err) {
    state.error = `Failed to create schedule: ${err.message}`;
    renderStatus();
  }
}

async function handleRunWhatIf() {
  const sid = el("wi-series-select")?.value;
  if (!sid) return;
  const out = el("wi-result");
  const chartEl = el("wi-chart");
  const onHandRaw = el("wi-on-hand")?.value;
  const payload = {
    series_id: sid,
    demand_multiplier: Number(el("wi-demand-mult")?.value || 1.0),
    lead_time_delta_days: Number(el("wi-lt-delta")?.value || 0.0),
    service_level: Number(el("wi-svc")?.value || 0.95),
    review_period: Number(el("wi-r")?.value || 7),
    on_hand_override: onHandRaw !== "" && onHandRaw != null ? Number(onHandRaw) : null,
  };

  state.error = "";
  try {
    const res = await api.runWhatIf(payload);
    const b = res.baseline;
    const s = res.scenario;
    const d = res.delta;
    const fmtDelta = (v, unit = "u") => (v == null ? "-" : `${v >= 0 ? "+" : ""}${v}${unit}`);
    if (out) {
      out.hidden = false;
      out.innerHTML = `
        <span><strong>Baseline Status:</strong> <span class="inv-badge inv-badge-${b.status.toLowerCase()}">${b.status}</span> &rarr; <strong>Scenario:</strong> <span class="inv-badge inv-badge-${s.status.toLowerCase()}">${s.status}</span></span>
        <span><strong>Safety Stock:</strong> ${b.safety_stock} &rarr; <strong>${s.safety_stock}</strong> (${fmtDelta(d.safety_stock)})</span>
        <span><strong>ROP:</strong> ${b.rop} &rarr; <strong>${s.rop}</strong> (${fmtDelta(d.rop)})</span>
        <span><strong>Order-up-to S:</strong> ${b.order_up_to_S} &rarr; <strong>${s.order_up_to_S}</strong> (${fmtDelta(d.order_up_to_S)})</span>
        <span><strong>Order Qty:</strong> ${b.order_qty} &rarr; <strong>${s.order_qty}</strong> (${fmtDelta(d.order_qty)})</span>
        <span><strong>Runway ETA:</strong> ${b.eta_expected_days ?? "∞"}d &rarr; <strong>${s.eta_expected_days ?? "∞"}d</strong> (${fmtDelta(d.eta_expected_days, "d")})</span>
      `;
    }
    if (chartEl && typeof Plotly !== "undefined") {
      chartEl.hidden = false;
      Plotly.react(
        chartEl,
        [
          {
            x: res.dates,
            y: res.baseline_daily_expected,
            type: "scatter",
            mode: "lines",
            name: "Baseline Expected",
            line: { color: "#1F4E79", width: 2 },
          },
          {
            x: res.dates,
            y: res.scenario_daily_expected,
            type: "scatter",
            mode: "lines",
            name: `Scenario (${payload.demand_multiplier.toFixed(2)}x)`,
            line: { color: "#C2571A", width: 2.2, dash: "dash" },
          },
        ],
        {
          margin: { l: 45, r: 20, t: 25, b: 35 },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          title: { text: `${sid} — Baseline vs. Scenario Daily Demand`, font: { size: 13 } },
          yaxis: { title: "Units / day" },
        },
        { responsive: true, displaylogo: false }
      );
    }
  } catch (err) {
    state.error = `What-If failed: ${err.message}`;
    renderStatus();
  }
}

async function handleAddPromotion() {
  const name = (el("promo-name")?.value || "").trim();
  const start = el("promo-start")?.value || "";
  const end = el("promo-end")?.value || "";
  const scope = el("promo-scope")?.value || "CURRENT";
  const uplift = Number(el("promo-uplift")?.value || 0);
  const notes = (el("promo-notes")?.value || "").trim();

  if (!name || !start || !end) {
    state.error = "Promotion name, start date, and end date are required.";
    renderStatus();
    return;
  }
  state.error = "";
  try {
    await api.createPromotion({
      name,
      start_date: start,
      end_date: end,
      series_id: scope === "ALL" ? null : currentSeriesId(),
      uplift_pct: Number.isFinite(uplift) ? uplift : 0,
      notes,
    });
    state.promotions = await api.getPromotions();
    if (el("promo-name")) el("promo-name").value = "";
    renderEventsAndPromos();
    renderChart(false);
  } catch (err) {
    state.error = `Failed to add promotion: ${err.message}`;
    renderStatus();
  }
}

async function init() {
  setupEvents();
  moveHorizonHighlight(true);
  await loadInitialForecastingData();
}

document.addEventListener("DOMContentLoaded", init);
