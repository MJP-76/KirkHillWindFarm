/**
 * Kirk Hill Wind Farm SCADA card.
 *
 * Renders a single-line SCADA-style diagram: 8 turbines feeding a site
 * collection bus, through a step-up transformer, into the national grid.
 * Each turbine shows live power, colour-coded status, last-status time,
 * today's generation and rotor speed. Flow dots animate at a speed
 * proportional to the power being transferred.
 *
 * Card type: custom:kirkhill-wind-scada
 *
 * Replace "@VERSION@" with the current release version before shipping; this
 * is done automatically by scripts/version_sync.py.
 */
const KIRKHILL_WIND_SCADA_VERSION = "4.9.0";
class KirkHillWindScada extends HTMLElement {
  static get VIEWBOX() {
    return { w: 1240, h: 1620, wMin: 900, wMax: 1800, hMin: 1620, hMax: 1620 };
  }

  static get DESIGN_W() {
    return 1240;
  }

  static get MAX_ZOOM() {
    return 6;
  }

  static get MIN_ZOOM() {
    return 0.5;
  }

  static get TAP_MOVE_PX() {
    return 8;
  }

  static get DOUBLE_TAP_MS() {
    return 300;
  }

  static get STATUS() {
    return {
      running: { label: "RUNNING", class: "status-running", color: "var(--khscada-success-color)" },
      ready: { label: "READY", class: "status-ready", color: "var(--khscada-accent-color)" },
      starting: { label: "STARTING", class: "status-starting", color: "var(--khscada-warn-color)" },
      curtailed: { label: "CURTAILED", class: "status-curtailed", color: "var(--khscada-warn-color)" },
      no_wind: { label: "NO WIND", class: "status-no-wind", color: "var(--khscada-accent-color)" },
      stopped: { label: "STOPPED", class: "status-stopped", color: "var(--khscada-disabled-color)" },
      fault_thermal: { label: "THERMAL FAULT", class: "status-fault", color: "var(--khscada-error-color)" },
      fault_electrical: { label: "ELEC FAULT", class: "status-fault", color: "var(--khscada-error-color)" },
      maintenance: { label: "MAINTENANCE", class: "status-maintenance", color: "var(--khscada-accent-color)" },
      unavailable: { label: "UNAVAILABLE", class: "status-unavailable", color: "var(--khscada-disabled-color)" },
      unknown: { label: "UNKNOWN", class: "status-unknown", color: "var(--khscada-disabled-color)" },
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._values = new Map();
    this._vbW = KirkHillWindScada.VIEWBOX.w;
    this._vbH = KirkHillWindScada.VIEWBOX.h;
    this._turbineEntities = new Map();
    this._zoom = { k: 1, tx: 0, ty: 0 };
    this._fitRaf = null;
    this._updateRaf = null;
  }

  connectedCallback() {
    if (this.config && !this.shadowRoot.innerHTML.trim()) this._render();
    if (!this._ro) {
      this._ro = new ResizeObserver(() => this._fit());
      this._ro.observe(this);
    }
  }

  disconnectedCallback() {
    if (this._ro) {
      this._ro.disconnect();
      this._ro = null;
    }
    if (this._fitRaf) { cancelAnimationFrame(this._fitRaf); this._fitRaf = null; }
    if (this._updateRaf) { cancelAnimationFrame(this._updateRaf); this._updateRaf = null; }
    if (this._mousePan) this._mousePan = null;
    document.removeEventListener("mousemove", this._onMouseMove);
    document.removeEventListener("mouseup", this._onMouseUp);
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.turbines) || config.turbines.length === 0) {
      throw new Error("turbines must be a non-empty array");
    }
    this.config = { title: "", ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.config && !this._updateRaf) {
      this._updateRaf = requestAnimationFrame(() => {
        this._updateRaf = null;
        this._update();
      });
    }
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, rows: 12, min_rows: 8, max_rows: 16 };
  }

  // ---- global timeframe control -----------------------------------------

  _TIME_RANGES() {
    return [
      { key: "6h", label: "6H", ms: 6 * 3600 * 1000 },
      { key: "12h", label: "12H", ms: 12 * 3600 * 1000 },
      { key: "1d", label: "24H", ms: 24 * 3600 * 1000 },
      { key: "1w", label: "1W", ms: 7 * 24 * 3600 * 1000 },
      { key: "1m", label: "1M", ms: 30 * 24 * 3600 * 1000 },
      { key: "6m", label: "6M", ms: 180 * 24 * 3600 * 1000 },
      { key: "1y", label: "1Y", ms: 365 * 24 * 3600 * 1000 },
    ];
  }

  _modalTime(key) {
    if (!this._modalTimeRanges) this._modalTimeRanges = {};
    if (!this._modalTimeRanges[key]) this._modalTimeRanges[key] = "1d";
    return this._modalTimeRanges[key];
  }

  _timeRangeWindow(key) {
    const rk = this._modalTime(key);
    const found = this._TIME_RANGES().find(r => r.key === rk);
    return found ? found : this._TIME_RANGES()[2];
  }

  _turbineModalKey(tid) {
    return `turbine__${tid}`;
  }

  _setModalTimeRange(key, rangeKey) {
    if (!this._modalTimeRanges) this._modalTimeRanges = {};
    this._modalTimeRanges[key] = rangeKey;
    this.shadowRoot.querySelectorAll(`.time-range-bar[data-key="${key}"]`).forEach(bar => {
      bar.querySelectorAll("[data-range]").forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-range") === rangeKey);
      });
    });
  }

  _modalTimeRangeHTML(key) {
    const active = this._modalTime(key);
    return `
      <div class="time-range-bar modal-time-range" data-key="${key}">
        <span class="time-range-label">Chart timeframe</span>
        ${this._TIME_RANGES().map(r =>
          `<button class="time-range-btn${r.key === active ? " active" : ""}" data-range="${r.key}">${r.label}</button>`
        ).join("")}
      </div>`;
  }

  _bindModalTimeRange(key, refresh) {
    this.shadowRoot.querySelectorAll(`.time-range-bar[data-key="${key}"] button[data-range]`).forEach(btn => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const rk = btn.getAttribute("data-range");
        if (rk === this._modalTime(key)) return;
        this._setModalTimeRange(key, rk);
        this._updateModalChartLabel(key);
        if (refresh) refresh();
      });
    });
  }

  _updateModalChartLabel(key) {
    const range = this._timeRangeWindow(key);
    this.shadowRoot.querySelectorAll(`.time-range-bar[data-key="${key}"] .time-range-label`).forEach(l => {
      l.textContent = `Chart timeframe`;
    });
    const titles = this.shadowRoot.querySelectorAll(`.td-charts[data-key="${key}"] > h3`);
    titles.forEach(t => { t.textContent = `Historical Data (${range.label})`; });
  }

  // ---- value helpers ----------------------------------------------------

  _num(entityId) {
    const s = this._hass?.states?.[entityId]?.state;
    if (s === undefined || s === null || s === "" || s === "unavailable") return null;
    const n = parseFloat(String(s).replace(",", ""));
    return Number.isFinite(n) ? n : null;
  }

  _str(entityId) {
    return this._hass?.states?.[entityId]?.state ?? "";
  }

  _attr(entityId, key) {
    return this._hass?.states?.[entityId]?.attributes?.[key];
  }

  _isStale(entityId) {
    return this._attr(entityId, "data_stale") === true;
  }

  _setChipStale(el, entityId) {
    // Last-known data shown in red instead of being hidden, so a stale value
    // is obvious but the number stays visible.
    if (!el) return;
    const stale = this._isStale(entityId);
    el.style.fill = stale ? "var(--khscada-error-color)" : "";
    el.style.opacity = stale ? "1" : this._attr(entityId, "generation_source") === "restored" ? "0.5" : "1";
  }

  _fmt(n, decimals = 1) {
    if (n === null || n === undefined || !Number.isFinite(n)) return "—";
    const s = n.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    // Strip trailing zeros after decimal point (e.g. "617.0" → "617")
    return decimals > 0 ? s.replace(/\.?0+$/, "") : s;
  }

  _scaleKwh(kwh) {
    if (kwh === null || kwh === undefined || !Number.isFinite(kwh)) {
      return { value: "—", unit: "kWh" };
    }
    if (Math.abs(kwh) >= 1e6) return { value: this._fmt(kwh / 1e6), unit: "GWh" };
    if (Math.abs(kwh) >= 1e3) return { value: this._fmt(kwh / 1e3), unit: "MWh" };
    return { value: this._fmt(kwh, 0), unit: "kWh" };
  }

  _powerText(kw) {
    if (kw === null || kw === undefined || !Number.isFinite(kw)) {
      return { value: "—", unit: "" };
    }
    // The owner's export is tiny (sub-kW), so fall back to watts below 1 kW.
    if (Math.abs(kw) < 1) return { value: this._fmt(kw * 1000, 0), unit: "W" };
    return { value: this._fmt(kw, 1), unit: "kW" };
  }

  _fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  _statusFor(stateText, category) {
    const key = (category && KirkHillWindScada.STATUS[category]) ? category : this._guessStatus(stateText);
    return { key, ...(KirkHillWindScada.STATUS[key] || KirkHillWindScada.STATUS.unknown) };
  }

  _guessStatus(stateText) {
    const s = stateText || "";
    if (s === "unavailable") return "unavailable";
    if (s.includes("operation")) return "running";
    if (s.includes("operational")) return "ready";
    if (s.includes("starting")) return "starting";
    if (s.includes("bird and bat")) return "curtailed";
    if (s.includes("Lack of wind")) return "no_wind";
    if (s.includes("temperature")) return "fault_thermal";
    if (s.includes("switched off") || s.includes("event management")) return "stopped";
    if (s.includes("Pulse inhibit")) return "fault_electrical";
    if (s.includes("Calibration")) return "maintenance";
    if (s.toLowerCase().includes("fault")) return "fault_electrical";
    return "unknown";
  }

  _dotDur(powerKw, lineLength) {
    const p = powerKw ?? 0;
    if (p < 1) return null; // no flow
    // Use a square-root curve so low power gets more visual spread:
    // 0 kW → 26s, ~500 kW → ~15s, 2400 kW → 2.5s.
    const ratio = Math.min(p / 2400, 1);
    const base = 2.5 + (1 - Math.sqrt(ratio)) * 23.5;
    const len = lineLength > 0 ? lineLength : 250;
    const t = Math.max(1.5, Math.min(60, base * (len / 250)));
    return `${t.toFixed(2)}s`;
  }

  _escape(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---- render -----------------------------------------------------------

  _render() {
    if (!this.config || !this.shadowRoot) return;
    const vb = KirkHillWindScada.VIEWBOX;
    const layout = this._layout();
    const header = this.config.title ? ` header="${this._escape(this.config.title)}"` : "";
    const { turbinesHtml, linesHtml, dotsHtml } = this._buildStatic(layout);
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card${header}>
        <div class="shell">
          <svg viewBox="0 0 ${layout.W} ${layout.H}" style="--khscada-fs: ${Math.min(1, layout.scaleX).toFixed(3)}" role="img" aria-label="Wind farm SCADA diagram">
            <defs>
              <pattern id="khscada-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(100,116,139,0.25)" stroke-width="1"/>
              </pattern>
              <marker id="khscada-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                      markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--khscada-accent-color)"/>
              </marker>
            </defs>
            <rect class="bg" x="0" y="0" width="${layout.W}" height="${layout.H}" fill="url(#khscada-grid)"/>
            <g data-zoom="wrap" transform="translate(0 0) scale(1)">
              ${linesHtml}
              ${dotsHtml}
              ${turbinesHtml}
              ${this._buildBus(layout)}
              ${this._buildTransformer(layout)}
              ${this._buildGrid(layout)}
              ${this._buildHeaderChips(layout)}
            </g>
          </svg>
        </div>
      </ha-card>
    `;
    this._bindClicks();
    this._bindZoom();
    this._update();
  }

  _bindClicks() {
    const svg = this.shadowRoot.querySelector("svg");
    if (!svg) return;
    if (this._boundClick) svg.removeEventListener("click", this._boundClick);
    this._boundClick = (ev) => {
      const resetBtn = ev.target.closest('[data-zoom-reset="btn"]');
      if (resetBtn) {
        this._zoomReset();
        return;
      }
      const site = ev.target.closest("[data-site-gen='panel']");
      if (site) { this._openSiteDetail(); return; }
      const owner = ev.target.closest("[data-user-gen='panel']");
      if (owner) { this._openOwnerDetail(); return; }
      const windPanel = ev.target.closest("[data-wind='panel']");
      if (windPanel) { this._openWindDetail(); return; }
      const apiPill = ev.target.closest("[data-api='indicator']");
      if (apiPill) { this._openApiDetail(); return; }
      const alarmPill = ev.target.closest("[data-alarm='indicator']");
      if (alarmPill) { this._openTurbineStatus(); return; }
      const g = ev.target.closest("g.turbine");
      if (!g) return;
      this._openTurbine(g);
    };
    svg.addEventListener("click", this._boundClick);
  }

  _openTurbine(g) {
    const key = g.getAttribute("data-turbine");
    const turbine = this.config.turbines.find(t => (t.id || `T${this.config.turbines.indexOf(t) + 1}`) === key);
    if (!turbine) return;

    // Open custom detailed modal with historical charts
    this._showTurbineDetailModal(turbine);
  }

  _showTurbineDetailModal(turbine) {
    const hass = this._hass;
    const tid = turbine.id;
    const stateText = this._str(turbine.state_entity);
    const status = this._statusFor(stateText, this._attr(turbine.state_entity, "status_category"));

    const power = this._num(turbine.power_entity);
    const cf = this._num(turbine.capacity_entity);
    const wind = this._num(turbine.wind_speed_entity);
    const rotor = this._num(turbine.rotor_entity);
    const genToday = this._num(turbine.generation_today_entity);
    const genScaled = this._scaleKwh(genToday);
    const powerText = this._powerText(power);

    const statusStarted = this._attr(turbine.state_entity, "status_started_at");
    const stateStarted = this._attr(turbine.state_entity, "state_started_at");
    const lat = this._attr(turbine.state_entity, "latitude");
    const lon = this._attr(turbine.state_entity, "longitude");
    const coords = (lat != null && lon != null) ? `${lat}, ${lon}` : null;

    const modal = document.createElement("div");
    modal.className = "turbine-detail-modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close="backdrop"></div>
      <div class="modal-content">
        <div class="modal-header">
          <h2>${this._escape(tid)} \u2014 Turbine Detail</h2>
          <button class="modal-close" data-close="close" aria-label="Close">\u2715</button>
        </div>
        <div class="modal-body">
          <div class="td-section td-live">
            <div class="td-status-badge" style="--badge-color: ${status.color}">
              <span class="td-status-dot"></span>${status.label}
            </div>
            <div class="td-kpi-grid">
              <div class="td-kpi"><span class="td-kpi-label">Power</span><span class="td-kpi-value">${powerText.value}</span><span class="td-kpi-unit">${powerText.unit}</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Capacity</span><span class="td-kpi-value">${cf !== null ? this._fmt(cf) : "\u2014"}</span><span class="td-kpi-unit">%</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Wind</span><span class="td-kpi-value">${wind !== null ? this._fmt(wind) : "\u2014"}</span><span class="td-kpi-unit">m/s</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Rotor</span><span class="td-kpi-value">${rotor !== null ? this._fmt(rotor) : "\u2014"}</span><span class="td-kpi-unit">rpm</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Gen Today</span><span class="td-kpi-value">${genScaled.value}</span><span class="td-kpi-unit">${genScaled.unit}</span></div>
            </div>
            <div class="td-state-line">${this._escape(stateText) || "\u2014"}</div>
          </div>

          <div class="td-section td-specs">
            <h3>Specifications</h3>
            <div class="td-spec-grid">
              <div class="td-spec"><span class="td-spec-label">Model</span><span class="td-spec-value">Enercon E92/2350</span></div>
              <div class="td-spec"><span class="td-spec-label">Rated Power</span><span class="td-spec-value">2.35 MW</span></div>
              <div class="td-spec"><span class="td-spec-label">Design</span><span class="td-spec-value">Direct drive (gearbox-free)</span></div>
              <div class="td-spec"><span class="td-spec-label">Peak Wind</span><span class="td-spec-value">\u2265 14 m/s (27.2 kn)</span></div>
              <div class="td-spec"><span class="td-spec-label">Coordinates</span><span class="td-spec-value">${coords ? '<a class="td-coords-link" href="https://www.google.com/maps?q=' + encodeURIComponent(coords) + '" target="_blank" rel="noopener">' + this._escape(coords) + '</a>' : "\u2014"}</span></div>
              <div class="td-spec"><span class="td-spec-label">Status since</span><span class="td-spec-value">${this._fmtTime(statusStarted)}</span></div>
              <div class="td-spec"><span class="td-spec-label">State since</span><span class="td-spec-value">${this._fmtTime(stateStarted)}</span></div>
            </div>
          </div>

          <div class="td-section td-charts" data-key="${this._turbineModalKey(tid)}">
            ${this._modalTimeRangeHTML(this._turbineModalKey(tid))}
            <h3>Historical Data (${this._timeRangeWindow(this._turbineModalKey(tid)).label})</h3>
            <div class="chart-grid">
              <div class="chart-item large">
                <h3>Power</h3>
                <div id="chart-power" class="apex-chart"></div>
              </div>
              <div class="chart-item large">
                <h3>Wind vs Power</h3>
                <div id="chart-wind-power" class="apex-chart"></div>
              </div>
              <div class="chart-item">
                <h3>Capacity Factor</h3>
                <div id="chart-capacity" class="apex-chart"></div>
              </div>
              <div class="chart-item">
                <h3>Rotor Speed</h3>
                <div id="chart-rotor" class="apex-chart"></div>
              </div>
              <div class="chart-item">
                <h3>Wind Speed</h3>
                <div id="chart-wind" class="apex-chart"></div>
              </div>
              <div class="chart-item">
                <h3>Generation Today</h3>
                <div id="chart-generation" class="apex-chart"></div>
              </div>
              <div class="chart-item large">
                <h3>Turbine Activity</h3>
                <div id="chart-activity" class="apex-chart"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    this.shadowRoot.appendChild(modal);
    this._turbineDetailTurbine = turbine;
    this._turbineDetailModal = modal;
    modal.querySelectorAll("[data-close]").forEach(el => {
      el.addEventListener("click", () => this._closeTurbineDetailModal());
    });

    this._boundKeydown = (e) => { if (e.key === "Escape") this._closeTurbineDetailModal(); };
    window.addEventListener("keydown", this._boundKeydown);

    this._bindModalTimeRange(this._turbineModalKey(turbine.id), () => this._initTurbineCharts(turbine));

    requestAnimationFrame(() => this._initTurbineCharts(turbine));
  }

  _closeTurbineDetailModal() {
    if (this._turbineDetailModal) {
      this._turbineDetailModal.remove();
      this._turbineDetailModal = null;
    }
    if (this._turbineDetailCharts) {
      Object.values(this._turbineDetailCharts).forEach(c => c.destroy && c.destroy());
      this._turbineDetailCharts = null;
    }
    if (this._turbineDetailTurbine) {
      // Reset to 24h so a heavy 6M/1Y window is not re-fetched on every reopen.
      const key = this._turbineModalKey(this._turbineDetailTurbine.id);
      if (this._modalTimeRanges) this._modalTimeRanges[key] = "1d";
    }
    this._turbineDetailTurbine = null;
    if (this._boundKeydown) {
      window.removeEventListener("keydown", this._boundKeydown);
      this._boundKeydown = null;
    }
  }

  // ---- Site / Owner detail modal --------------------------------------

  _openSiteDetail() { this._showSiteDetailModal(); }
  _openOwnerDetail() { this._showOwnerDetailModal(); }
  _openWindDetail() { this._showWindDetailModal(); }

  // ---- Site detail modal ------------------------------------------------

  _showSiteDetailModal() {
    const config = this.config;
    const sitePowerMw = this._num(config.farm_power_entity);
    const siteCap = this._num(config.capacity_entity);
    const siteGenToday = this._num(config.grid_energy_entity);
    const sitePowerText =
      sitePowerMw === null ? { value: "—", unit: "MW" } : { value: this._fmt(sitePowerMw, 2), unit: "MW" };
    const siteGenScaled = this._scaleKwh(siteGenToday);

    const modal = document.createElement("div");
    modal.className = "turbine-detail-modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close="backdrop"></div>
      <div class="modal-content">
        <div class="modal-header">
          <h2>Site Generation &amp; Capacity</h2>
          <button class="modal-close" data-close="close" aria-label="Close">&#10005;</button>
        </div>
        <div class="modal-body">
          <div class="td-section td-live">
            <div class="td-kpi-grid">
              <div class="td-kpi"><span class="td-kpi-label">Site Power</span><span class="td-kpi-value">${sitePowerText.value}</span><span class="td-kpi-unit">${sitePowerText.unit}</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Site Capacity</span><span class="td-kpi-value">${siteCap !== null ? this._fmt(siteCap, 1) : "—"}</span><span class="td-kpi-unit">%</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Gen Today</span><span class="td-kpi-value">${siteGenScaled.value}</span><span class="td-kpi-unit">${siteGenScaled.unit}</span></div>
            </div>
          </div>
          <div class="td-section td-charts" data-key="site">
            ${this._modalTimeRangeHTML("site")}
            <h3>Historical Data (${this._timeRangeWindow("site").label})</h3>
            <div class="chart-grid">
              <div class="chart-item large">
                <h3>Site Power (MW)</h3>
                <div id="site-chart-power" class="apex-chart"></div>
              </div>
              <div class="chart-item">
                <h3>Site Capacity Factor</h3>
                <div id="site-chart-capacity" class="apex-chart"></div>
              </div>
              <div class="chart-item large">
                <h3>Site Generation Today (kWh)</h3>
                <div id="site-chart-gen" class="apex-chart"></div>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    this.shadowRoot.appendChild(modal);
    this._siteDetailModal = modal;
    modal.querySelectorAll("[data-close]").forEach(el =>
      el.addEventListener("click", () => this._closeSiteDetailModal()));
    this._siteBoundKeydown = (e) => { if (e.key === "Escape") this._closeSiteDetailModal(); };
    window.addEventListener("keydown", this._siteBoundKeydown);
    this._bindModalTimeRange("site", () => this._initSiteCharts());
    requestAnimationFrame(() => this._initSiteCharts());
  }

  _closeSiteDetailModal() {
    if (this._siteDetailModal) { this._siteDetailModal.remove(); this._siteDetailModal = null; }
    if (this._siteDetailCharts) { Object.values(this._siteDetailCharts).forEach(c => c.destroy?.()); this._siteDetailCharts = null; }
    if (this._siteBoundKeydown) { window.removeEventListener("keydown", this._siteBoundKeydown); this._siteBoundKeydown = null; }
  }

  async _initSiteCharts() {
    if (this._siteDetailCharts) { Object.values(this._siteDetailCharts).forEach(c => c.destroy?.()); this._siteDetailCharts = null; }
    const config = this.config;
    const now = new Date();
    const startISO = new Date(now.getTime() - this._timeRangeWindow("site").ms).toISOString();
    const entities = {
      sitePower: config.farm_power_entity,
      capacity: config.capacity_entity,
      genSite: config.grid_energy_entity,
    };
    this._setChartLoading();
    try {
      await this._ensureApexCharts();
      const history = await this._fetchHistory(entities, startISO, now.toISOString());
      if (window.ApexCharts) { this._renderSiteCharts(history); this._clearChartPlaceholders(); }
      else this._showChartError("Charts unavailable — ApexCharts failed to load");
    } catch (err) {
      console.error("Failed to load site history:", err);
      this._showChartError(`Charts unavailable — ${err.message || "unknown error"}`);
    }
  }

  _renderSiteCharts(history) {
    if (!window.ApexCharts) return;
    const charts = {};
    const ts = (id) => this.shadowRoot.querySelector(id);
    const toSeries = (arr) => (arr || []).map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)]).filter(d => d[1] !== null);

    const sitePowerData = toSeries(history.sitePower);
    if (sitePowerData.length) {
      charts.power = new ApexCharts(ts("#site-chart-power"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Site Power (MW)", data: sitePowerData }],
        xaxis: { type: "datetime" }, yaxis: { title: { text: "MW" } },
        stroke: { curve: "smooth", width: 2 }, markers: { size: 0 }, colors: ["#0284c7"],
        tooltip: { x: { format: "HH:mm" } },
      }));
      charts.power.render();
    }

    const capData = toSeries(history.capacity);
    if (capData.length) {
      charts.capacity = new ApexCharts(ts("#site-chart-capacity"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Capacity %", data: capData }],
        xaxis: { type: "datetime" }, yaxis: { title: { text: "%" }, max: 100 },
        stroke: { curve: "smooth", width: 2 }, colors: ["#22c55e"],
        tooltip: { x: { format: "HH:mm" } },
      }));
      charts.capacity.render();
    }

    const genData = toSeries(history.genSite);
    if (genData.length) {
      charts.gen = new ApexCharts(ts("#site-chart-gen"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Gen (kWh)", data: genData }],
        xaxis: { type: "datetime" }, yaxis: { title: { text: "kWh" } },
        stroke: { curve: "stepline", width: 2 }, colors: ["#059669"],
        tooltip: { x: { format: "HH:mm" } },
      }));
      charts.gen.render();
    }

    this._siteDetailCharts = charts;
  }

  // ---- Owner detail modal -----------------------------------------------

  _showOwnerDetailModal() {
    const config = this.config;
    const ownerPowerKw = this._num(config.owner_power_entity);
    const ownerGenToday = this._num(config.owner_generation_today_entity);
    const ownerPowerText = this._powerText(ownerPowerKw);
    const ownerGenScaled = this._scaleKwh(ownerGenToday);

    const modal = document.createElement("div");
    modal.className = "turbine-detail-modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close="backdrop"></div>
      <div class="modal-content">
        <div class="modal-header">
          <h2>Owner Generation &amp; Capacity</h2>
          <button class="modal-close" data-close="close" aria-label="Close">&#10005;</button>
        </div>
        <div class="modal-body">
          <div class="td-section td-live">
            <div class="td-kpi-grid">
              <div class="td-kpi"><span class="td-kpi-label">Owner Power</span><span class="td-kpi-value">${ownerPowerText.value}</span><span class="td-kpi-unit">${ownerPowerText.unit}</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Gen Today</span><span class="td-kpi-value">${ownerGenScaled.value}</span><span class="td-kpi-unit">${ownerGenScaled.unit}</span></div>
            </div>
          </div>
          <div class="td-section td-charts" data-key="owner">
            ${this._modalTimeRangeHTML("owner")}
            <h3>Historical Data (${this._timeRangeWindow("owner").label})</h3>
            <div class="chart-grid">
              <div class="chart-item large">
                <h3>Owner Power (kW)</h3>
                <div id="owner-chart-power" class="apex-chart"></div>
              </div>
              <div class="chart-item large">
                <h3>Owner Generation Today (kWh)</h3>
                <div id="owner-chart-gen" class="apex-chart"></div>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    this.shadowRoot.appendChild(modal);
    this._ownerDetailModal = modal;
    modal.querySelectorAll("[data-close]").forEach(el =>
      el.addEventListener("click", () => this._closeOwnerDetailModal()));
    this._ownerBoundKeydown = (e) => { if (e.key === "Escape") this._closeOwnerDetailModal(); };
    window.addEventListener("keydown", this._ownerBoundKeydown);
    this._bindModalTimeRange("owner", () => this._initOwnerCharts());
    requestAnimationFrame(() => this._initOwnerCharts());
  }

  _closeOwnerDetailModal() {
    if (this._ownerDetailModal) { this._ownerDetailModal.remove(); this._ownerDetailModal = null; }
    if (this._ownerDetailCharts) { Object.values(this._ownerDetailCharts).forEach(c => c.destroy?.()); this._ownerDetailCharts = null; }
    if (this._ownerBoundKeydown) { window.removeEventListener("keydown", this._ownerBoundKeydown); this._ownerBoundKeydown = null; }
  }

  // ---- Wind detail modal ------------------------------------------------

  _showWindDetailModal() {
    const config = this.config;
    const wind = this._num(config.wind_speed_entity);
    const forecast = this._num(config.wind_forecast_entity);
    const diff = (wind !== null && forecast !== null) ? wind - forecast : null;

    const modal = document.createElement("div");
    modal.className = "turbine-detail-modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close="backdrop"></div>
      <div class="modal-content">
        <div class="modal-header">
          <h2>Wind Speed</h2>
          <button class="modal-close" data-close="close" aria-label="Close">&#10005;</button>
        </div>
        <div class="modal-body">
          <div class="td-section td-live">
            <div class="td-kpi-grid">
              <div class="td-kpi"><span class="td-kpi-label">Current Speed</span><span class="td-kpi-value">${wind !== null ? this._fmt(wind) : "—"}</span><span class="td-kpi-unit">m/s</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Forecast (1h)</span><span class="td-kpi-value">${forecast !== null ? this._fmt(forecast) : "—"}</span><span class="td-kpi-unit">m/s</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Difference</span><span class="td-kpi-value">${diff !== null ? (diff >= 0 ? "+" : "") + this._fmt(diff) : "—"}</span><span class="td-kpi-unit">m/s</span></div>
            </div>
          </div>
        </div>
      </div>`;
    this.shadowRoot.appendChild(modal);
    this._windDetailModal = modal;
    modal.querySelectorAll("[data-close]").forEach(el =>
      el.addEventListener("click", () => this._closeWindDetailModal()));
    this._windBoundKeydown = (e) => { if (e.key === "Escape") this._closeWindDetailModal(); };
    window.addEventListener("keydown", this._windBoundKeydown);
  }

  _closeWindDetailModal() {
    if (this._windDetailModal) { this._windDetailModal.remove(); this._windDetailModal = null; }
    if (this._windBoundKeydown) { window.removeEventListener("keydown", this._windBoundKeydown); this._windBoundKeydown = null; }
  }

  _openApiDetail() { this._showApiDetailModal(); }

  _showApiDetailModal() {
    const config = this.config;
    const hass = this._hass;
    const entity = config.api_status_entity;
    const state = entity ? this._str(entity) : "";
    const isUp = state === "on";
    const lastChanged = entity ? hass?.states?.[entity]?.last_changed : null;
    const since = lastChanged ? new Date(lastChanged) : null;
    const sinceStr = since ? `${String(since.getHours()).padStart(2,"0")}:${String(since.getMinutes()).padStart(2,"0")} on ${since.toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"})}` : "\u2014";
    const rateLimited = isUp && this._attr(entity, "rate_limited") === true;
    const statusLabel = isUp ? (rateLimited ? "LIMITED" : "OK") : state === "unavailable" || state === "unknown" ? "UNKNOWN" : "DOWN";
    const statusColor = isUp ? (rateLimited ? "var(--khscada-warn-color, #ffb300)" : "var(--khscada-success-color)") : "var(--khscada-error-color)";

    const modal = document.createElement("div");
    modal.className = "turbine-detail-modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close="backdrop"></div>
      <div class="modal-content">
        <div class="modal-header">
          <h2>API Status</h2>
          <button class="modal-close" data-close="close" aria-label="Close">&#10005;</button>
        </div>
        <div class="modal-body">
          <div class="td-section td-live">
            <div class="td-status-badge" style="--badge-color: ${statusColor}">
              <span class="td-status-dot"></span>${statusLabel}
            </div>
            <div class="td-kpi-grid">
              <div class="td-kpi"><span class="td-kpi-label">Status</span><span class="td-kpi-value">${statusLabel}</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Since</span><span class="td-kpi-value">${sinceStr}</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Entity</span><span class="td-kpi-value" style="font-size:0.8em;word-break:break-all">${entity || "\u2014"}</span></div>
            </div>
          </div>
          <div class="td-section">
            <h3>Recent History</h3>
            <div id="api-history-content"><span class="ts-hist-empty">Loading...</span></div>
          </div>
        </div>
      </div>`;
    this.shadowRoot.appendChild(modal);
    this._apiDetailModal = modal;
    modal.querySelectorAll("[data-close]").forEach(el =>
      el.addEventListener("click", () => this._closeApiDetailModal()));
    this._apiBoundKeydown = (e) => { if (e.key === "Escape") this._closeApiDetailModal(); };
    window.addEventListener("keydown", this._apiBoundKeydown);

    // Load history asynchronously
    this._loadApiHistory(entity);
  }

  async _loadApiHistory(entityId) {
    const container = this.shadowRoot.getElementById("api-history-content");
    if (!container || !entityId) return;
    const now = new Date();
    const startISO = new Date(now.getTime() - 24 * 3600 * 1000).toISOString();
    const endISO = now.toISOString();
    try {
      const path = `history/period/${startISO}?end_time=${endISO}&filter_entity_id=${encodeURIComponent(entityId)}&minimal_response&significant_changes_only`;
      const data = await this._hass.callApi("GET", path);
      const raw = Array.isArray(data) ? data[0] || [] : [];
      if (raw.length === 0) { container.innerHTML = '<span class="ts-hist-empty">No history available</span>'; return; }
      // Find status changes
      const changes = [];
      for (let i = 0; i < raw.length; i++) {
        const st = raw[i].state;
        let label, color;
        if (st === "on") { label = "OK"; color = "var(--khscada-success-color)"; }
        else if (st === "unavailable" || st === "unknown") { label = "UNKNOWN"; color = "var(--khscada-secondary-color)"; }
        else { label = "DOWN"; color = "var(--khscada-error-color)"; }
        if (i === 0 || label !== changes[changes.length - 1]?.label) {
          changes.push({ label, color, time: new Date(raw[i].last_changed), state: st });
        }
      }
      // Show last 10 changes, most recent first
      const recent = changes.slice(-10).reverse();
      let html = '<table class="ts-hist-table">';
      html += '<tr><th>Status</th><th>Time</th><th>Duration</th></tr>';
      for (let i = 0; i < recent.length; i++) {
        const c = recent[i];
        const hh = String(c.time.getHours()).padStart(2, "0");
        const mm = String(c.time.getMinutes()).padStart(2, "0");
        const dd = c.time.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
        // Duration: time until next change (or now)
        const nextTime = i > 0 ? recent[i - 1].time : now;
        const durMs = nextTime.getTime() - c.time.getTime();
        const durMin = Math.round(durMs / 60000);
        const durStr = durMin < 1 ? "<1m" : durMin < 60 ? `${durMin}m` : `${Math.floor(durMin/60)}h${durMin%60 > 0 ? (durMin%60)+"m" : ""}`;
        html += `<tr><td><span class="ts-dot" style="background:${c.color}"></span>${c.label}</td><td class="ts-since">${dd} ${hh}:${mm}</td><td class="ts-hist-detail">${durStr}</td></tr>`;
      }
      html += '</table>';
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<span class="ts-hist-empty">Failed to load: ${err.message || "unknown"}</span>`;
    }
  }

  _closeApiDetailModal() {
    if (this._apiDetailModal) { this._apiDetailModal.remove(); this._apiDetailModal = null; }
    if (this._apiBoundKeydown) { window.removeEventListener("keydown", this._apiBoundKeydown); this._apiBoundKeydown = null; }
  }

  _openTurbineStatus() { this._showTurbineStatusModal(); }

  _showTurbineStatusModal() {
    const config = this.config;
    const hass = this._hass;
    const active = this._num(config.active_entity);
    const total = config.turbines.length;
    const offline = active === null ? total : total - active;
    let summaryColor;
    if (offline === 0) { summaryColor = "var(--khscada-success-color)"; }
    else if (offline >= total) { summaryColor = "var(--khscada-error-color)"; }
    else { summaryColor = "var(--khscada-warn-color, #ffb300)"; }

    let rows = "";
    for (const t of config.turbines) {
      const tid = t.id || `T${config.turbines.indexOf(t) + 1}`;
      const stateText = this._str(t.state_entity);
      const category = this._attr(t.state_entity, "status_category");
      const status = this._statusFor(stateText, category);
      const lastChanged = hass?.states?.[t.state_entity]?.last_changed;
      const since = lastChanged ? new Date(lastChanged) : null;
      const sinceStr = since ? `${String(since.getHours()).padStart(2,"0")}:${String(since.getMinutes()).padStart(2,"0")}` : "\u2014";
      rows += `<tr class="ts-row" data-tid="${this._escape(tid)}" data-entity="${this._escape(t.state_entity)}" style="cursor:pointer"><td class="ts-tid">${this._escape(tid)}</td><td><span class="ts-dot" style="background:${status.color}"></span>${status.label}</td><td class="ts-since">${sinceStr}</td><td class="ts-state">${this._escape(stateText) || "\u2014"}</td></tr>`;
      rows += `<tr class="ts-history" data-history="${this._escape(tid)}" style="display:none"><td colspan="4"><div class="ts-history-content" id="ts-hist-${this._escape(tid)}">Loading...</div></td></tr>`;
    }

    const modal = document.createElement("div");
    modal.className = "turbine-detail-modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close="backdrop"></div>
      <div class="modal-content" style="max-width:680px">
        <div class="modal-header">
          <h2>Turbine Status</h2>
          <button class="modal-close" data-close="close" aria-label="Close">&#10005;</button>
        </div>
        <div class="modal-body">
          <div class="td-section td-live">
            <div class="td-status-badge" style="--badge-color: ${summaryColor}">
              <span class="td-status-dot"></span>${active !== null ? active : "\u2014"} of ${total} Active
            </div>
            <div class="td-kpi-grid">
              <div class="td-kpi"><span class="td-kpi-label">Active</span><span class="td-kpi-value">${active !== null ? active : "\u2014"}</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Offline</span><span class="td-kpi-value">${offline}</span></div>
              <div class="td-kpi"><span class="td-kpi-label">Total</span><span class="td-kpi-value">${total}</span></div>
            </div>
          </div>
          <div class="td-section">
            <h3>Per-Turbine <span style="font-weight:400;font-size:0.8em;color:var(--khscada-secondary-color)">\u2014 click a row for history</span></h3>
            <table class="ts-table"><thead><tr><th>ID</th><th>Status</th><th>Since</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table>
          </div>
        </div>
      </div>`;
    this.shadowRoot.appendChild(modal);
    this._turbineStatusModal = modal;
    modal.querySelectorAll("[data-close]").forEach(el =>
      el.addEventListener("click", () => this._closeTurbineStatusModal()));
    this._tsBoundKeydown = (e) => { if (e.key === "Escape") this._closeTurbineStatusModal(); };
    window.addEventListener("keydown", this._tsBoundKeydown);

    // Bind row clicks to expand/collapse history
    modal.querySelectorAll(".ts-row").forEach(row => {
      row.addEventListener("click", () => {
        const tid = row.getAttribute("data-tid");
        const histRow = modal.querySelector(`tr[data-history="${tid}"]`);
        if (!histRow) return;
        const isOpen = histRow.style.display !== "none";
        histRow.style.display = isOpen ? "none" : "";
        if (!isOpen && histRow.querySelector(".ts-history-content")?.textContent === "Loading...") {
          this._loadTurbineHistory(row.getAttribute("data-entity"), `ts-hist-${tid}`);
        }
      });
    });

    // Preload history for all turbines
    this._preloadAllTurbineHistory(config.turbines, modal);
  }

  async _preloadAllTurbineHistory(turbines, modal) {
    const now = new Date();
    const start = new Date(now.getTime() - 24 * 3600 * 1000);
    const startISO = start.toISOString();
    const endISO = now.toISOString();
    for (const t of turbines) {
      const tid = t.id || `T${turbines.indexOf(t) + 1}`;
      try {
        await this._loadTurbineHistory(t.state_entity, `ts-hist-${tid}`, startISO, endISO);
      } catch { /* ignore per-turbine failures */ }
    }
  }

  async _loadTurbineHistory(entityId, containerId, startISO, endISO) {
    const container = this.shadowRoot.getElementById(containerId);
    if (!container) return;
    if (!startISO) {
      const now = new Date();
      startISO = new Date(now.getTime() - 24 * 3600 * 1000).toISOString();
      endISO = now.toISOString();
    }
    try {
      const path = `history/period/${startISO}?end_time=${endISO}&filter_entity_id=${encodeURIComponent(entityId)}&minimal_response&significant_changes_only`;
      const data = await this._hass.callApi("GET", path);
      const raw = Array.isArray(data) ? data[0] || [] : [];
      if (raw.length === 0) { container.innerHTML = '<span class="ts-hist-empty">No history available</span>'; return; }
      // Find status changes: consecutive entries with different state values
      const changes = [];
      for (let i = 0; i < raw.length; i++) {
        const st = raw[i].state;
        const cat = raw[i].attributes?.status_category;
        const label = this._statusFor(st, cat).label;
        if (i === 0 || label !== changes[changes.length - 1]?.label) {
          changes.push({ label, color: this._statusFor(st, cat).color, time: new Date(raw[i].last_changed), detail: st });
        }
      }
      // Show last 8 changes, most recent first
      const recent = changes.slice(-8).reverse();
      let html = '<table class="ts-hist-table">';
      html += '<tr><th>Status</th><th>Time</th><th>Detail</th></tr>';
      for (const c of recent) {
        const hh = String(c.time.getHours()).padStart(2, "0");
        const mm = String(c.time.getMinutes()).padStart(2, "0");
        const dd = c.time.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
        html += `<tr><td><span class="ts-dot" style="background:${c.color}"></span>${c.label}</td><td class="ts-since">${dd} ${hh}:${mm}</td><td class="ts-hist-detail">${this._escape(c.detail) || "\u2014"}</td></tr>`;
      }
      html += '</table>';
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<span class="ts-hist-empty">Failed to load: ${err.message || "unknown"}</span>`;
    }
  }

  _closeTurbineStatusModal() {
    if (this._turbineStatusModal) { this._turbineStatusModal.remove(); this._turbineStatusModal = null; }
    if (this._tsBoundKeydown) { window.removeEventListener("keydown", this._tsBoundKeydown); this._tsBoundKeydown = null; }
  }

  async _initOwnerCharts() {
    if (this._ownerDetailCharts) { Object.values(this._ownerDetailCharts).forEach(c => c.destroy?.()); this._ownerDetailCharts = null; }
    const config = this.config;
    const now = new Date();
    const startISO = new Date(now.getTime() - this._timeRangeWindow("owner").ms).toISOString();
    const entities = {
      ownerPower: config.owner_power_entity,
      genOwner: config.owner_generation_today_entity,
    };
    this._setChartLoading();
    try {
      await this._ensureApexCharts();
      const history = await this._fetchHistory(entities, startISO, now.toISOString());
      if (window.ApexCharts) { this._renderOwnerCharts(history); this._clearChartPlaceholders(); }
      else this._showChartError("Charts unavailable — ApexCharts failed to load");
    } catch (err) {
      console.error("Failed to load owner history:", err);
      this._showChartError(`Charts unavailable — ${err.message || "unknown error"}`);
    }
  }

  _renderOwnerCharts(history) {
    if (!window.ApexCharts) return;
    const charts = {};
    const ts = (id) => this.shadowRoot.querySelector(id);
    const toSeries = (arr) => (arr || []).map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)]).filter(d => d[1] !== null);

    const ownerPowerData = toSeries(history.ownerPower);
    if (ownerPowerData.length) {
      charts.power = new ApexCharts(ts("#owner-chart-power"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Owner Power (kW)", data: ownerPowerData }],
        xaxis: { type: "datetime" }, yaxis: { title: { text: "kW" } },
        stroke: { curve: "smooth", width: 2 }, markers: { size: 0 }, colors: ["#10b981"],
        tooltip: { x: { format: "HH:mm" } },
      }));
      charts.power.render();
    }

    const genData = toSeries(history.genOwner);
    if (genData.length) {
      charts.gen = new ApexCharts(ts("#owner-chart-gen"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Gen (kWh)", data: genData }],
        xaxis: { type: "datetime" }, yaxis: { title: { text: "kWh" } },
        stroke: { curve: "stepline", width: 2 }, colors: ["#059669"],
        tooltip: { x: { format: "HH:mm" } },
      }));
      charts.gen.render();
    }

    this._ownerDetailCharts = charts;
  }

  async _initTurbineCharts(turbine) {
    // Destroy any lingering charts from a previous open
    if (this._turbineDetailCharts) {
      Object.values(this._turbineDetailCharts).forEach(c => c.destroy && c.destroy());
      this._turbineDetailCharts = null;
    }

    const now = new Date();
    const start = new Date(now.getTime() - this._timeRangeWindow(this._turbineModalKey(turbine.id)).ms);
    const startISO = start.toISOString();
    const endISO = now.toISOString();

    const entities = {
      power: turbine.power_entity,
      wind: turbine.wind_speed_entity,
      capacity: turbine.capacity_entity,
      rotor: turbine.rotor_entity,
      generation: turbine.generation_today_entity,
      state: turbine.state_entity,
    };

    this._setChartLoading();
    try {
      await this._ensureApexCharts();
      const history = await this._fetchHistory(entities, startISO, endISO);
      if (window.ApexCharts) {
        this._renderCharts(turbine.id, history, start.getTime(), now.getTime());
        this._clearChartPlaceholders();
      } else {
        this._showChartError("Charts unavailable — ApexCharts failed to load");
      }
    } catch (err) {
      console.error("Failed to load turbine history:", err);
      this._showChartError(`Charts unavailable — ${err.message || "unknown error"}`);
    }
  }

  _ensureApexCharts() {
    if (window.ApexCharts) return Promise.resolve();
    if (this._apexLoadPromise) return this._apexLoadPromise;
    const src = `${this._hass.auth.data.hassUrl}/kirkhill_wind/apexcharts.js`;
    this._apexLoadPromise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._apexLoadPromise = null;
        reject(new Error("ApexCharts load timed out"));
      }, 15000);
      const script = document.createElement("script");
      script.src = src;
      script.onload = () => { clearTimeout(timer); resolve(); };
      script.onerror = () => { clearTimeout(timer); this._apexLoadPromise = null; reject(new Error("ApexCharts script failed to load")); };
      document.head.appendChild(script);
    });
    return this._apexLoadPromise;
  }

  async _fetchHistory(entities, start, end) {
    const hass = this._hass;
    const windowMs = new Date(end).getTime() - new Date(start).getTime();
    const long = windowMs > 7 * 24 * 3600 * 1000;
    const maxPts = long ? 500 : 800;

    const results = await Promise.all(Object.entries(entities).map(async ([key, entityId]) => {
      if (!entityId) return [key, []];
      if (long && key !== "state") {
        const stats = await this._fetchStatistics(entityId, start, end);
        if (stats && stats.length) return [key, this._downsample(stats, maxPts)];
      }
      try {
        const path = `history/period/${start}?end_time=${end}&filter_entity_id=${encodeURIComponent(entityId)}&minimal_response&significant_changes_only`;
        const data = await hass.callApi("GET", path);
        const raw = Array.isArray(data) ? data[0] || [] : [];
        return [key, key === "state" ? raw : this._downsample(raw, maxPts)];
      } catch {
        return [key, []];
      }
    }));

    return Object.fromEntries(results);
  }

  async _fetchStatistics(entityId, start, end) {
    const conn = this._hass?.connection;
    if (!conn?.sendMessagePromise) return null;
    try {
      const stats = await conn.sendMessagePromise({
        type: "recorder/statistics_during_period",
        start_time: start,
        end_time: end,
        statistic_ids: [entityId],
        period: "hour",
        types: ["mean", "state"],
      });
      const rows = stats?.[entityId];
      if (!Array.isArray(rows) || !rows.length) return null;
      return rows
        .map(r => ({ last_changed: r.start, state: r.mean ?? r.state }))
        .filter(p => p.state != null && p.state !== "");
    } catch {
      return null;
    }
  }

  _renderCharts(turbineId, history, startEpoch, endEpoch) {
    if (!window.ApexCharts) return;

    const charts = {};

    // Pre-compute wind lookup once for the scatter chart
    const windMap = new Map();
    if (history.wind?.length) {
      for (const w of history.wind) {
        const t = new Date(w.last_changed).getTime();
        const v = this._numVal(w.state);
        if (v !== null) windMap.set(t, v);
      }
    }

    // Power chart
    const powerData = (history.power || [])
      .map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)])
      .filter(d => d[1] !== null);
    if (powerData.length) {
      charts.power = new ApexCharts(this.shadowRoot.querySelector("#chart-power"), this._apexOpts({
        type: "line", height: 300,
        series: [{ name: "Power (kW)", data: powerData }],
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "kW" } },
        stroke: { curve: "smooth", width: 2 },
        markers: { size: 0 },
        colors: ["#0284c7"],
        tooltip: { x: { format: "HH:mm" } },
      }));
      charts.power.render();
    }

    // Wind vs Power scatter
    if (windMap.size && powerData.length) {
      const scatterData = this._downsample(history.power
        .map(p => {
          const t = new Date(p.last_changed).getTime();
          const pv = this._numVal(p.state);
          if (pv === null) return null;
          const wv = windMap.get(t) ?? this._interpolateWind(history.wind, t);
          return wv !== null ? { x: pv, y: wv } : null;
        })
        .filter(d => d !== null), 400);
      if (scatterData.length) {
        charts.windPower = new ApexCharts(this.shadowRoot.querySelector("#chart-wind-power"), this._apexOpts({
          type: "scatter", height: 300,
          series: [{ name: "Wind vs Power", data: scatterData }],
          xaxis: { title: { text: "Power (kW)" }, labels: { formatter: (v) => this._fmt(v, 2) } },
          yaxis: { title: { text: "Wind (m/s)" }, labels: { formatter: (v) => this._fmt(v, 2) } },
          colors: ["#f59e0b"],
          markers: { size: 4 },
        }));
        charts.windPower.render();
      }
    }

    // Capacity factor
    const capData = (history.capacity || [])
      .map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)])
      .filter(d => d[1] !== null);
    if (capData.length) {
      charts.capacity = new ApexCharts(this.shadowRoot.querySelector("#chart-capacity"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Capacity %", data: capData }],
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "%" }, max: 100 },
        stroke: { curve: "smooth", width: 2 },
        colors: ["#22c55e"],
      }));
      charts.capacity.render();
    }

    // Rotor speed
    const rotorData = (history.rotor || [])
      .map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)])
      .filter(d => d[1] !== null);
    if (rotorData.length) {
      charts.rotor = new ApexCharts(this.shadowRoot.querySelector("#chart-rotor"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "RPM", data: rotorData }],
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "RPM" } },
        stroke: { curve: "smooth", width: 2 },
        colors: ["#8b5cf6"],
      }));
      charts.rotor.render();
    }

    // Wind speed
    const windData = (history.wind || [])
      .map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)])
      .filter(d => d[1] !== null);
    if (windData.length) {
      charts.wind = new ApexCharts(this.shadowRoot.querySelector("#chart-wind"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Wind (m/s)", data: windData }],
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "m/s" } },
        stroke: { curve: "smooth", width: 2 },
        markers: { size: 0 },
        colors: ["#f59e0b"],
      }));
      charts.wind.render();
    }

    // Generation today (step line)
    const genData = (history.generation || [])
      .map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)])
      .filter(d => d[1] !== null);
    if (genData.length) {
      charts.generation = new ApexCharts(this.shadowRoot.querySelector("#chart-generation"), this._apexOpts({
        type: "line", height: 250,
        series: [{ name: "Generation (kWh)", data: genData }],
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "kWh" } },
        stroke: { curve: "stepline", width: 2 },
        colors: ["#059669"],
      }));
      charts.generation.render();
    }

    // Turbine activity: a swimlane state timeline. One labelled row per status
    // the turbine was in during the window, with a coloured block for each
    // continuous stretch, so state changes and their durations read at a glance.
    const activity = this._buildActivityHistory(history.state || [], startEpoch, endEpoch);
    if (activity.segments.length) {
      const bg = this._cssVar("var(--khscada-card-bg)") || this._cssVar("var(--card-background-color)") || "#1c1c1c";
      const fg = this._cssVar("var(--khscada-primary-color)") || this._cssVar("var(--primary-text-color)") || "#e1e1e1";
      // ApexCharts rangeBar expects { x: <category>, y: [start, end] } for a
      // datetime timeline; per-segment colour must be fillColor (a plain
      // `color` key is ignored and every bar falls back to the default).
      const activityData = activity.segments.map(s => ({
        x: s.label,
        y: s.x,
        fillColor: s.color,
        key: s.key,
      }));
      const laneH = 30;
      charts.activity = new ApexCharts(this.shadowRoot.querySelector("#chart-activity"), this._apexOpts({
        type: "rangeBar",
        height: Math.max(120, activity.lanes.length * laneH + 40),
        series: [{ name: "Turbine Activity", data: activityData }],
        plotOptions: { bar: { horizontal: true, barHeight: "55%", rangeBarGroupRows: false } },
        xaxis: { type: "datetime", min: startEpoch, max: endEpoch },
        dataLabels: { enabled: false },
        tooltip: {
          custom: ({ seriesIndex, dataPointIndex, w }) => {
            const d = w.config.series[seriesIndex].data[dataPointIndex];
            if (!d) return "";
            const st = KirkHillWindScada.STATUS[d.key] || KirkHillWindScada.STATUS.unknown;
            return `<div style="padding:6px 10px;font-family:inherit;font-size:13px;background:${bg};color:${fg};border-radius:4px">
              <div style="font-weight:600;color:${this._cssVar(st.color)}">${st.label}</div>
              <div>${this._fmtTime(new Date(d.y[0]).toISOString())} \u2192 ${this._fmtTime(new Date(d.y[1]).toISOString())}</div>
              <div>Duration ${this._fmtDuration(d.y[1] - d.y[0])}</div>
            </div>`;
          },
        },
      }));
      charts.activity.render();
    }

    this._turbineDetailCharts = charts;
  }

  // Collapse consecutive history samples with the same status key into one
  // horizontal range segment, using the fixed window start/end as the
  // boundaries. Returns the segments plus the ordered lanes (one per status
  // that occurred) for the swimlane y-axis.
  _buildActivityHistory(stateHistory, startEpoch, endEpoch) {
    const empty = { segments: [], lanes: [] };
    if (!stateHistory || !stateHistory.length) return empty;
    const items = stateHistory
      .map(p => {
        const t = new Date(p.last_changed).getTime();
        if (!Number.isFinite(t)) return null;
        const st = this._statusFor(String(p.state ?? ""), null);
        return { t, key: st.key, label: st.label, color: st.color };
      })
      .filter(Boolean)
      .sort((a, b) => a.t - b.t);
    if (!items.length) return empty;

    // Expand the first and last samples to the window edges so the bands span
    // the full selected timeframe.
    const segs = [];
    let prev = null;
    for (const it of items) {
      if (prev === null) {
        prev = it;
        continue;
      }
      if (it.key === prev.key) {
        prev.t = it.t;
        continue;
      }
      segs.push({ key: prev.key, label: prev.label, color: prev.color, x: [prev.t, it.t] });
      prev = it;
    }
    if (prev) {
      segs.push({ key: prev.key, label: prev.label, color: prev.color, x: [prev.t, endEpoch] });
    }
    if (segs.length && segs[0].x[0] !== startEpoch) {
      segs[0].x[0] = startEpoch;
    }

    // One lane per status that occurred; the set is sorted into the STATUS
    // definition order so it is deterministic. Only `lanes.length` is used by
    // the caller (to size the chart) - ApexCharts orders the visible rows by
    // first occurrence in the window, so the top lane is the earliest state.
    const defined = Object.keys(KirkHillWindScada.STATUS);
    const present = [...new Set(segs.map(s => s.key))];
    present.sort((a, b) => defined.indexOf(a) - defined.indexOf(b));
    const lanes = present.map(key => {
      const st = KirkHillWindScada.STATUS[key] || KirkHillWindScada.STATUS.unknown;
      return { key, label: st.label, color: st.color };
    });
    return { segments: segs, lanes };
  }

  _fmtDuration(ms) {
    if (!Number.isFinite(ms) || ms < 0) return "\u2014";
    const mins = Math.round(ms / 60000);
    if (mins < 1) return "<1m";
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h >= 24) {
      const d = Math.floor(h / 24);
      return `${d}d ${h % 24}h`;
    }
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  _cssVar(value) {
    const m = /^var\((--[\w-]+)(?:,\s*([^)]+))?\)$/.exec(value || "");
    if (!m) return value || "";
    const resolved = getComputedStyle(this).getPropertyValue(m[1]).trim() || (m[2] || "").trim();
    return resolved || value;
  }

  _isDark() {
    if (this._hass?.themes?.darkMode === true) return true;
    if (this._hass?.themes?.darkMode === false) return false;
    const bg = this._cssVar("var(--card-background-color, #ffffff)").trim();
    const hex = bg.match(/#([0-9a-f]{6})/i);
    if (hex) {
      const n = parseInt(hex[1], 16);
      const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
      return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 140;
    }
    const rgb = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (rgb) {
      return (0.2126 * +rgb[1] + 0.7152 * +rgb[2] + 0.0722 * +rgb[3]) < 140;
    }
    return true;
  }

  _apexOpts({ type, height, series, colors, stroke, markers, xaxis, yaxis, tooltip, plotOptions, dataLabels, chartExtra }) {
    const dark = this._isDark();
    const text = this._cssVar("var(--khscada-primary-color)") || this._cssVar("var(--primary-text-color)") || "#e1e1e1";
    const muted = this._cssVar("var(--khscada-secondary-color)") || this._cssVar("var(--secondary-text-color)") || "#9b9b9b";
    const divider = this._cssVar("var(--khscada-divider)") || this._cssVar("var(--divider-color)") || "#444";
    return {
      series,
      colors,
      ...(stroke ? { stroke } : {}),
      ...(markers ? { markers } : {}),
      ...(plotOptions ? { plotOptions } : {}),
      ...(dataLabels ? { dataLabels } : {}),
      chart: {
        type,
        height,
        toolbar: { show: false },
        background: "transparent",
        foreColor: text,
        legend: { show: false },
        ...(chartExtra || {}),
      },
      theme: { mode: dark ? "dark" : "light" },
      grid: { borderColor: divider, strokeDashArray: 3 },
      tooltip: {
        theme: dark ? "dark" : "light",
        style: { fontSize: "12px" },
        ...(tooltip || {}),
      },
      xaxis: {
        axisBorder: { color: divider },
        axisTicks: { color: divider },
        ...(xaxis || {}),
        labels: { style: { colors: muted }, ...((xaxis && xaxis.labels) || {}) },
      },
      yaxis: {
        ...(yaxis || {}),
        labels: { style: { colors: muted }, ...((yaxis && yaxis.labels) || {}) },
      },
    };
  }

  _downsample(arr, maxPoints) {
    if (!arr || arr.length <= maxPoints) return arr || [];
    const step = (arr.length - 1) / (maxPoints - 1);
    const out = [];
    for (let i = 0; i < maxPoints; i++) out.push(arr[Math.round(i * step)]);
    return out;
  }

  _interpolateWind(windHistory, targetTime) {
    if (!windHistory.length) return null;
    let before = null, after = null;
    for (const w of windHistory) {
      const t = new Date(w.last_changed).getTime();
      if (t <= targetTime) before = this._numVal(w.state);
      else { after = this._numVal(w.state); break; }
    }
    if (before !== null && after !== null) return (before + after) / 2;
    return before ?? after ?? null;
  }

  _numVal(state) {
    const n = parseFloat(String(state ?? "").replace(",", ""));
    return Number.isFinite(n) ? n : null;
  }

  _showChartError(msg) {
    if (!this.shadowRoot) return;
    this._renderChartPlaceholders(msg);
  }

  _setChartLoading() {
    if (!this.shadowRoot) return;
    this._renderChartPlaceholders("Waiting for data\u2026");
  }

  _renderChartPlaceholders(msg) {
    this.shadowRoot.querySelectorAll(".apex-chart").forEach(el => {
      let overlay = el.querySelector(":scope > .chart-placeholder");
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.className = "chart-placeholder";
        el.appendChild(overlay);
      }
      overlay.textContent = msg;
    });
  }

  _clearChartPlaceholders() {
    if (!this.shadowRoot) return;
    this.shadowRoot.querySelectorAll(".chart-placeholder").forEach(el => el.remove());
  }

  // ---- mobile pan / pinch-zoom ----------------------------------------

  _bindZoom() {
    const svg = this.shadowRoot.querySelector("svg");
    if (!svg) return;
    this._zoomReset();
    svg.addEventListener("touchstart", this._touchStart = this._touchStart.bind(this), { passive: false });
    svg.addEventListener("touchmove", this._touchMove = this._touchMove.bind(this), { passive: false });
    svg.addEventListener("touchend", this._touchEnd = this._touchEnd.bind(this), { passive: false });
    svg.addEventListener("touchcancel", this._touchEnd = this._touchEnd.bind(this), { passive: false });
    svg.addEventListener("wheel", this._onWheel = this._onWheel.bind(this), { passive: false });
    svg.addEventListener("mousedown", this._onMouseDown = this._onMouseDown.bind(this), { passive: false });
    svg.addEventListener("dblclick", this._onDoubleClick = this._onDoubleClick.bind(this), { passive: false });
    svg.addEventListener("mouseleave", this._onMouseLeave = this._onMouseLeave.bind(this), { passive: false });
    document.addEventListener("mousemove", this._onMouseMove = this._onMouseMove.bind(this), { passive: false });
    document.addEventListener("mouseup", this._onMouseUp = this._onMouseUp.bind(this), { passive: false });
    svg.style.cursor = "grab";
  }

  _zoomReset() {
    this._zoom = { k: 1, tx: 0, ty: 0 };
    this._pan = null;
    this._pinch = null;
    this._lastTap = null;
    this._applyZoom();
  }

  _applyZoom() {
    const g = this.shadowRoot?.querySelector('[data-zoom="wrap"]');
    if (!g) return;
    g.setAttribute(
      "transform",
      `translate(${this._zoom.tx} ${this._zoom.ty}) scale(${this._zoom.k})`
    );
  }

  _svgMetrics() {
    const svg = this.shadowRoot.querySelector("svg");
    if (!svg) return null;
    const r = svg.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return { r, w: KirkHillWindScada.VIEWBOX.w, h: this._vbH };
  }

  _touchStart(ev) {
    ev.preventDefault();
    const t = ev.touches;
    if (t.length === 1) {
      this._pinch = null;
      this._pan = {
        id: t[0].identifier,
        lastX: t[0].clientX,
        lastY: t[0].clientY,
        startX: t[0].clientX,
        startY: t[0].clientY,
        moved: false,
      };
    } else if (t.length >= 2) {
      this._pan = null;
      const d = Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
      this._pinch = { dist: d, k0: this._zoom.k };
    }
  }

  _touchMove(ev) {
    ev.preventDefault();
    const m = this._svgMetrics();
    if (!m) return;
    const t = ev.touches;

    if (this._pinch && t.length >= 2) {
      const d = Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
      if (!d) return;
      const midX = (t[0].clientX + t[1].clientX) / 2;
      const midY = (t[0].clientY + t[1].clientY) / 2;
      const vx = ((midX - m.r.left) * m.w) / m.r.width;
      const vy = ((midY - m.r.top) * m.h) / m.r.height;
      const z = this._zoom;
      const k2 = Math.min(
        KirkHillWindScada.MAX_ZOOM,
        Math.max(1, this._pinch.k0 * (d / this._pinch.dist))
      );
      const wx = (vx - z.tx) / z.k;
      const wy = (vy - z.ty) / z.k;
      z.k = k2;
      z.tx = vx - wx * k2;
      z.ty = vy - wy * k2;
      this._applyZoom();
    } else if (this._pan && t.length === 1 && t[0].identifier === this._pan.id) {
      const dx = t[0].clientX - this._pan.lastX;
      const dy = t[0].clientY - this._pan.lastY;
      this._pan.lastX = t[0].clientX;
      this._pan.lastY = t[0].clientY;
      if (
        Math.abs(t[0].clientX - this._pan.startX) > KirkHillWindScada.TAP_MOVE_PX ||
        Math.abs(t[0].clientY - this._pan.startY) > KirkHillWindScada.TAP_MOVE_PX
      ) {
        this._pan.moved = true;
      }
      this._zoom.tx += (dx * m.w) / m.r.width;
      this._zoom.ty += (dy * m.h) / m.r.height;
      this._applyZoom();
    }
  }

  _touchEnd(ev) {
    const t = ev.touches;

    if (this._pan && t.length === 0 && !this._pan.moved) {
      const c = ev.changedTouches[0];
      const now = Date.now();
      const dt = this._lastTap ? now - this._lastTap.at : Infinity;
      const dist = this._lastTap
        ? Math.hypot(c.clientX - this._lastTap.x, c.clientY - this._lastTap.y)
        : Infinity;
      this._lastTap = { x: c.clientX, y: c.clientY, at: now };
      if (dt < KirkHillWindScada.DOUBLE_TAP_MS && dist < 40) {
        this._zoomReset();
        this._pan = null;
        return;
      }
      const el = this.shadowRoot.elementFromPoint(c.clientX, c.clientY);
      if (el && el.closest && el.closest("[data-site-gen='panel']")) {
        this._openSiteDetail();
      } else if (el && el.closest && el.closest("[data-user-gen='panel']")) {
        this._openOwnerDetail();
      } else {
        const g = el && el.closest ? el.closest("g.turbine") : null;
        if (g) this._openTurbine(g);
      }
      this._pan = null;
      return;
    }

    if (t.length === 1) {
      const f = t[0];
      this._pinch = null;
      this._pan = {
        id: f.identifier,
        lastX: f.clientX,
        lastY: f.clientY,
        startX: f.clientX,
        startY: f.clientY,
        moved: false,
      };
    } else if (t.length === 0) {
      this._pan = null;
      this._pinch = null;
    }
  }

  // ---- mouse wheel zoom / drag pan (browser displays) ----

  _onWheel(ev) {
    ev.preventDefault();
    const m = this._svgMetrics();
    if (!m) return;
    const delta = -ev.deltaY * 0.003;
    const factor = Math.exp(delta);
    const z = this._zoom;
    const k2 = Math.min(KirkHillWindScada.MAX_ZOOM, Math.max(KirkHillWindScada.MIN_ZOOM, z.k * factor));
    const vx = ((ev.clientX - m.r.left) * m.w) / m.r.width;
    const vy = ((ev.clientY - m.r.top) * m.h) / m.r.height;
    const wx = (vx - z.tx) / z.k;
    const wy = (vy - z.ty) / z.k;
    z.k = k2;
    z.tx = vx - wx * k2;
    z.ty = vy - wy * k2;
    this._applyZoom();
    this._updateZoomCursor();
  }

  _onMouseDown(ev) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    const svg = this.shadowRoot.querySelector("svg");
    if (!svg) return;
    svg.style.cursor = "grabbing";
    this._mousePan = {
      lastX: ev.clientX,
      lastY: ev.clientY,
      moved: false,
    };
  }

  _onMouseMove(ev) {
    if (!this._mousePan) return;
    const m = this._svgMetrics();
    if (!m) return;
    const dx = (ev.clientX - this._mousePan.lastX) * m.w / m.r.width;
    const dy = (ev.clientY - this._mousePan.lastY) * m.h / m.r.height;
    this._mousePan.lastX = ev.clientX;
    this._mousePan.lastY = ev.clientY;
    if (Math.abs(dx) > 0 || Math.abs(dy) > 0) this._mousePan.moved = true;
    this._zoom.tx += dx;
    this._zoom.ty += dy;
    this._applyZoom();
  }

  _onMouseUp() {
    if (!this._mousePan) return;
    const svg = this.shadowRoot.querySelector("svg");
    if (svg) svg.style.cursor = "grab";
    if (!this._mousePan.moved) this._onDoubleClick();
    this._mousePan = null;
  }

  _onMouseLeave() {
    if (this._mousePan) {
      const svg = this.shadowRoot.querySelector("svg");
      if (svg) svg.style.cursor = "grab";
      this._mousePan = null;
    }
  }

  _onDoubleClick() {
    this._zoomReset();
    this._updateZoomCursor();
  }

  _updateZoomCursor() {
    const svg = this.shadowRoot.querySelector("svg");
    if (!svg) return;
    if (this._zoom.k > 1) {
      svg.style.cursor = "grab";
    } else {
      svg.style.cursor = "zoom-in";
    }
  }

  _zoomReset() {
    this._zoom = { k: 1, tx: 0, ty: 0 };
    this._pan = null;
    this._pinch = null;
    this._lastTap = null;
    this._mousePan = null;
    this._applyZoom();
    const svg = this.shadowRoot.querySelector("svg");
    if (svg) svg.style.cursor = "zoom-in";
  }

  _layout() {
    const H = this._vbH;
    const W = this._vbW;
    const scaleX = W / KirkHillWindScada.DESIGN_W;
    const tCount = this.config.turbines.length;
    const legendY = H - 150;

    // Staircase turbine layout: T1 left, T2 right with its top level with T1's
    // bottom, T3 left level with T2's bottom, and so on. Every turbine's feed
    // line runs straight to the bus unobstructed, and the block is spread to
    // roughly match the bus bar height. Boxes are sized to leave room for more
    // per-turbine detail lines later.
    const tTop = 64;
    const collapse = Math.max(
      0,
      Math.min(
        1,
        (KirkHillWindScada.DESIGN_W - W) /
          (KirkHillWindScada.DESIGN_W - KirkHillWindScada.VIEWBOX.wMin)
      )
    );
    const gapV = 10 * collapse;
    const bh = Math.max(
      110,
      Math.min(130, Math.floor((H - 190 - tTop - 30 - (tCount - 1) * gapV) / Math.max(1, tCount)))
    );
    const pitch = bh + gapV;
    const tBottom = tTop + tCount * pitch;

    // Grid box sits at the bottom of the turbines section, not at the card bottom.
    const gridY = tBottom;

    // Scale horizontal positions from design width (1240) to current viewBox width.
    // The two columns start with a small gap (40) that shrinks to nothing, then the
    // right column keeps sliding left until it sits directly under the left column,
    // merging the staircase into a single column at narrow widths. The vertical
    // pitch gains a small gap as the columns merge so stacked boxes never touch.
    const busX = 700 * scaleX;
    const leftColX = 30 * scaleX;
    const rightColX = (30 + (190 + 40) * (1 - collapse)) * scaleX;
    const boxW = 190 * scaleX;
    const feedEndX = busX;
    const gridRectX = 930 * scaleX;
    const transformerLineEndX = gridRectX;
    const transformerLineEndY = gridY - 135;
    const gridRectW = 270 * scaleX;
    const gridRightX = gridRectX + gridRectW;
    const ownerCx = 1015 * scaleX;
    const siteCx = 1205 * scaleX;
    const gridTitleX = (gridRectX + gridRightX) / 2;
    const gridDividerX1 = gridRectX + 10 * scaleX;
    const gridDividerX2 = gridRightX - 10 * scaleX;
    const chipLeftColX = 30 * scaleX;
    const chipRightColX = 152 * scaleX;
    const chipWindX = 500 * scaleX;
    const chipWindW = busX - chipWindX - 8;
    const chipWindTitleX = 512 * scaleX;
    const chipWindValueX = chipWindX + chipWindW - 12;
    const chipUserGenX = 930 * scaleX;
    const chipUserGenW = gridRightX - chipUserGenX;
    // Three-column table inside the 450-px panel (750→1200):
    // Timeframe labels ≈ 101 px, Generation values ≈ 82 px, Value £ ≈ 118 px.
    // Generation right edge at 1025 (−175), Value right edge at 1184 (−16).
    // Timeframe x so widest label ends 40 px before Generation column's left
    // edge: 1025 − 82 − 40 − 101 = 802.
    const chipUserGenValueX = gridRightX - 95 * scaleX;
    const chipUserGenTitleX = 942 * scaleX;
    const chipUserGenFinX = gridRightX - 16 * scaleX;
    const chipSiteGenX = 930 * scaleX;
    const chipSiteGenW = gridRightX - chipSiteGenX;
    const chipSiteGenValueX = gridRightX - 95 * scaleX;
    const chipSiteGenTitleX = 942 * scaleX;
    const chipSiteGenFinX = gridRightX - 16 * scaleX;
    const resetBtnW = 44 * scaleX;
    const resetBtnH = 48;
    // Bottom chrome row: version number, API status pill and reset button sit
    // together on one line above the legend strip; the button follows the pill.
    const chromeRowY = legendY - 20;
    const resetBtnY = chromeRowY - resetBtnH / 2;
    const versionX = 30 * scaleX;
    const apiPillX = versionX + 82 * scaleX;
    const apiPillW = 78 * scaleX;
    const resetBtnX = apiPillX + apiPillW + 12 * scaleX;
    const legendX = 86 * scaleX;
    const legendW = 500 * scaleX;
    const xfmrTitleX = 730 * scaleX;
    const xfmrRotateX = 730 * scaleX;

    return {
      H,
      W,
      scaleX,
      tTop,
      bh,
      pitch,
      gridY,
      busY2: gridY,
      busSummaryY: legendY - 24,
      legendY,
      busX,
      leftColX,
      rightColX,
      boxW,
      feedEndX,
      transformerLineEndX,
      transformerLineEndY,
      gridRectX,
      gridRectW,
      ownerCx,
      siteCx,
      gridTitleX,
      gridDividerX1,
      gridDividerX2,
      chipLeftColX,
      chipRightColX,
      chromeRowY,
      versionX,
      apiPillX,
      apiPillW,
      chipUserGenX,
      chipUserGenW,
      chipUserGenTitleX,
      chipUserGenValueX,
      chipUserGenFinX,
      chipSiteGenX,
      chipSiteGenW,
      chipSiteGenTitleX,
      chipSiteGenValueX,
      chipSiteGenFinX,
      chipWindX,
      chipWindW,
      chipWindTitleX,
      chipWindValueX,
      resetBtnX,
      resetBtnY,
      legendX,
      legendW,
      xfmrTitleX,
      xfmrRotateX,
      tCount,
      tBottom: tTop + tCount * pitch,
    };
  }

  _fit() {
    if (!this.config || !this.shadowRoot) return;
    if (this._fitRaf) return;
    this._fitRaf = requestAnimationFrame(() => {
      this._fitRaf = null;
      this._fitNow();
    });
  }

  _fitNow() {
    if (!this.config || !this.shadowRoot) return;
    const shell = this.shadowRoot.querySelector(".shell");
    if (!shell) return;
    const r = shell.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const vb = KirkHillWindScada.VIEWBOX;
    const aspect = r.width / r.height;
    let w = Math.round(aspect * this._vbH);
    w = Math.max(vb.wMin, Math.min(vb.wMax, w));
    let h = Math.round(w / aspect);
    h = Math.max(vb.hMin, Math.min(vb.hMax, h));
    w = Math.round(aspect * h);
    if (w === this._vbW && h === this._vbH) return;
    this._vbW = w;
    this._vbH = h;
    this._render();
  }

  _buildStatic(layout) {
    const turbines = this.config.turbines;
    let turbinesHtml = "";
    let linesHtml = "";
    let dotsHtml = "";

    turbines.forEach((t, i) => {
      const x = i % 2 === 0 ? layout.leftColX : layout.rightColX;
      const cx = x + layout.boxW;
      const top = layout.tTop + i * layout.pitch;
      const cy = top + layout.bh / 2;
      const num = this._escape(t.id || `T${i + 1}`);
      const stateEntity = t.state_entity;
      if (stateEntity) this._turbineEntities.set(t.id || `T${i + 1}`, stateEntity);
      turbinesHtml += `
        <g class="turbine" data-turbine="${this._escape(t.id || `T${i + 1}`)}">
          <rect class="node-rect" x="${x}" y="${top}" width="${layout.boxW}" height="${layout.bh}" rx="8"/>
          <text class="t-id" x="${x + 14 * layout.scaleX}" y="${top + 18}">${num}</text>
          <rect class="status-pill" x="${x + 88 * layout.scaleX}" y="${top + 5}" width="${100 * layout.scaleX}" height="20" rx="10"/>
          <text class="t-status" x="${x + 138 * layout.scaleX}" y="${top + 19}"></text>
          <text class="t-label" x="${x + 14 * layout.scaleX}" y="${top + 38}">Generation</text>
          <text class="t-power" x="${x + layout.boxW - 14 * layout.scaleX}" y="${top + 38}" text-anchor="end">—</text>
          <text class="t-label" x="${x + 14 * layout.scaleX}" y="${top + 54}">Capacity</text>
          <text class="t-op" x="${x + layout.boxW - 14 * layout.scaleX}" y="${top + 54}" text-anchor="end">—</text>
          <text class="t-label" x="${x + 14 * layout.scaleX}" y="${top + 70}">Wind</text>
          <text class="t-wind" x="${x + layout.boxW - 14 * layout.scaleX}" y="${top + 70}" text-anchor="end">—</text>
          <text class="t-label" x="${x + 14 * layout.scaleX}" y="${top + 86}">Rotor</text>
          <text class="t-detail" x="${x + layout.boxW - 14 * layout.scaleX}" y="${top + 86}" text-anchor="end">—</text>
          <text class="t-label" x="${x + 14 * layout.scaleX}" y="${top + 102}">Since</text>
          <text class="t-last" x="${x + layout.boxW - 14 * layout.scaleX}" y="${top + 102}" text-anchor="end">—</text>
        </g>
      `;
      linesHtml += `<line class="feed-line" x1="${cx}" y1="${cy}" x2="${layout.feedEndX}" y2="${cy}"/>`;
      dotsHtml += `
        <circle class="flow-dot" data-flow="t${i}" r="5" data-len="${layout.feedEndX - cx}">
          <animateMotion dur="10s" repeatCount="indefinite"
            path="M ${cx} ${cy} L ${layout.feedEndX} ${cy}"/>
        </circle>
      `;
    });

    return { turbinesHtml, linesHtml, dotsHtml };
  }

  _buildBus(layout) {
    return `
      <g class="bus">
        <rect x="${layout.busX}" y="${layout.tTop}" width="${60 * layout.scaleX}" height="${layout.tBottom - layout.tTop}" rx="6"/>
      </g>
    `;
  }

  _buildTransformer(layout) {
    const cy = layout.gridY;
    const busCenterY = (30 + cy) / 2;
    const lineY = layout.transformerLineEndY;
    return `
      <g class="transformer">
        <line class="feed-line" x1="${layout.busX + 60 * layout.scaleX}" y1="${lineY}" x2="${layout.transformerLineEndX}" y2="${lineY}" marker-end="url(#khscada-arrow)"/>
        <text class="xfmr-title" transform="rotate(90 ${layout.xfmrRotateX} ${busCenterY})" x="${layout.xfmrTitleX}" y="${busCenterY}" text-anchor="middle">TRANSFORMER — 33 kV</text>
        <circle class="flow-dot" data-flow="grid" r="5" data-len="${layout.transformerLineEndX - (layout.busX + 60 * layout.scaleX)}">
          <animateMotion dur="10s" repeatCount="indefinite"
            path="M ${layout.busX + 60 * layout.scaleX} ${lineY} L ${layout.transformerLineEndX} ${lineY}"/>
        </circle>
      </g>
    `;
  }

  _buildGrid(layout) {
    const cy = layout.gridY;
    return `
      <g class="grid">
        <rect class="grid-rect" x="${layout.gridRectX}" y="${cy - 270}" width="${layout.gridRectW}" height="270" rx="10"/>
        <text class="grid-title" x="${layout.gridTitleX}" y="${cy - 245}" text-anchor="middle">NATIONAL</text>
        <text class="grid-title" x="${layout.gridTitleX}" y="${cy - 221}" text-anchor="middle">GRID</text>
        <line class="grid-divider" x1="${layout.gridDividerX1}" y1="${cy - 175}" x2="${layout.gridDividerX2}" y2="${cy - 175}"/>
        <text class="grid-label" x="${layout.gridTitleX}" y="${cy - 153}" text-anchor="middle">Export</text>
        <text class="grid-power" data-grid="power" x="${layout.gridTitleX}" y="${cy - 121}" text-anchor="middle">—</text>
        <text class="grid-unit" data-grid="power-unit" x="${layout.gridTitleX}" y="${cy - 103}" text-anchor="middle"></text>
        <line class="grid-divider" x1="${layout.gridDividerX1}" y1="${cy - 87}" x2="${layout.gridDividerX2}" y2="${cy - 87}"/>
        <text class="grid-label" x="${layout.gridTitleX}" y="${cy - 65}" text-anchor="middle">To Grid Today</text>
        <text class="grid-energy" data-grid="energy" x="${layout.gridTitleX}" y="${cy - 39}" text-anchor="middle">—</text>
        <text class="grid-unit" data-grid="energy-unit" x="${layout.gridTitleX}" y="${cy - 21}" text-anchor="middle">kWh</text>
      </g>
    `;
  }

_buildHeaderChips(layout) {
    return `
      <g class="chips">
        <!-- Top chip row: Refresh | Version | API | Alarm | Wind Speed -->
        <g class="zoom-overlay" data-zoom-reset="btn">
          <rect x="${layout.chipLeftColX}" y="24" width="${30 * layout.scaleX}" height="30" rx="8"/>
          <text x="${layout.chipLeftColX + 15 * layout.scaleX}" y="44" text-anchor="middle" style="font-size: calc(18px * var(--khscada-fs, 1))">⟲</text>
        </g>
        <g class="version-pill" data-version="indicator">
          <rect x="${layout.chipLeftColX + 40 * layout.scaleX}" y="24" width="${150 * layout.scaleX}" height="30" rx="15"/>
          <text class="version-text" data-version="text" x="${layout.chipLeftColX + 115 * layout.scaleX}" y="44" text-anchor="middle">v${KIRKHILL_WIND_SCADA_VERSION}</text>
        </g>
        <g class="api-status" data-api="indicator">
          <rect x="${layout.chipLeftColX + 200 * layout.scaleX}" y="24" width="${68 * layout.scaleX}" height="30" rx="15"/>
          <text class="api-status-text" data-api="text" x="${layout.chipLeftColX + 234 * layout.scaleX}" y="44" text-anchor="middle">API</text>
        </g>
        <g class="alarm" data-alarm="indicator">
          <rect x="${layout.chipLeftColX + 278 * layout.scaleX}" y="24" width="${110 * layout.scaleX}" height="30" rx="15"/>
          <text class="alarm-text" data-alarm="text" data-chip="active" x="${layout.chipLeftColX + 333 * layout.scaleX}" y="44" text-anchor="middle">—</text>
        </g>
        <g data-wind="panel">
          <rect x="${layout.chipLeftColX + 398 * layout.scaleX}" y="24" width="${240 * layout.scaleX}" height="30" rx="15"/>
          <text x="${layout.chipLeftColX + 408 * layout.scaleX}" y="44"><tspan class="chip-label">Wind Speed: Current </tspan><tspan class="chip-value" data-chip="wind">—</tspan><tspan class="chip-label"> Forecast: </tspan><tspan class="chip-value" data-chip="forecast">—</tspan></text>
        </g>

        <!-- Right side: Owner Generation & Capacity (far right) -->
        <text class="gen-section-heading" x="${layout.chipUserGenTitleX}" y="64">Generation, Capacity & Earnings</text>
        <g class="user-gen" data-user-gen="panel">
          <rect x="${layout.chipUserGenX}" y="76" width="${layout.chipUserGenW}" height="232" rx="8"/>
          <text class="user-gen-title" x="${layout.chipUserGenTitleX}" y="98">Owner</text>
          <text class="user-gen-colh" x="${layout.chipUserGenTitleX}" y="120">Timeframe</text>
          <text class="user-gen-colh" x="${layout.chipUserGenValueX}" y="120" text-anchor="end">Generation</text>
          <text class="user-gen-colh" x="${layout.chipUserGenFinX}" y="120" text-anchor="end">Value (£)</text>
          <!-- Generation timeframes -->
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="142">Yesterday</text>
          <text class="user-gen-value" data-user-gen="gen-yesterday" x="${layout.chipUserGenValueX}" y="142" text-anchor="end">—</text>
          <text class="user-gen-value user-gen-fin" data-user-gen="fin-yesterday" x="${layout.chipUserGenFinX}" y="142" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="162">Today</text>
          <text class="user-gen-value" data-user-gen="gen-today" x="${layout.chipUserGenValueX}" y="162" text-anchor="end">—</text>
          <text class="user-gen-value user-gen-fin" data-user-gen="fin-today" x="${layout.chipUserGenFinX}" y="162" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="182">Week</text>
          <text class="user-gen-value" data-user-gen="gen-week" x="${layout.chipUserGenValueX}" y="182" text-anchor="end">—</text>
          <text class="user-gen-value user-gen-fin" data-user-gen="fin-week" x="${layout.chipUserGenFinX}" y="182" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="202">Month</text>
          <text class="user-gen-value" data-user-gen="gen-month" x="${layout.chipUserGenValueX}" y="202" text-anchor="end">—</text>
          <text class="user-gen-value user-gen-fin" data-user-gen="fin-month" x="${layout.chipUserGenFinX}" y="202" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="222">YTD</text>
          <text class="user-gen-value" data-user-gen="gen-ytd" x="${layout.chipUserGenValueX}" y="222" text-anchor="end">—</text>
          <text class="user-gen-value user-gen-fin" data-user-gen="fin-ytd" x="${layout.chipUserGenFinX}" y="222" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="242">Year</text>
          <text class="user-gen-value" data-user-gen="gen-year" x="${layout.chipUserGenValueX}" y="242" text-anchor="end">—</text>
          <text class="user-gen-value user-gen-fin" data-user-gen="fin-year" x="${layout.chipUserGenFinX}" y="242" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="262">All time</text>
          <text class="user-gen-value" data-user-gen="gen-alltime" x="${layout.chipUserGenValueX}" y="262" text-anchor="end">—</text>
          <text class="user-gen-value user-gen-fin" data-user-gen="fin-alltime" x="${layout.chipUserGenFinX}" y="262" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="282">Your Share (W)</text>
          <text class="user-gen-value user-gen-share" data-user-gen="share" x="${layout.chipUserGenValueX}" y="282" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="302">Share (‱)</text>
          <text class="user-gen-value" data-user-gen="sharepct" x="${layout.chipUserGenValueX}" y="302" text-anchor="end">—</text>
        </g>

        <!-- Right side: Site Generation & Capacity (below Owner) -->
        <g class="site-gen" data-site-gen="panel">
          <rect x="${layout.chipSiteGenX}" y="332" width="${layout.chipSiteGenW}" height="232" rx="8"/>
          <text class="site-gen-title" x="${layout.chipSiteGenTitleX}" y="354">Site</text>
          <text class="site-gen-colh" x="${layout.chipSiteGenTitleX}" y="376">Timeframe</text>
          <text class="site-gen-colh" x="${layout.chipSiteGenValueX}" y="376" text-anchor="end">Generation</text>
          <text class="site-gen-colh" x="${layout.chipSiteGenFinX}" y="376" text-anchor="end">Value (£)</text>
          <!-- Site timeframes -->
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="398">Yesterday</text>
          <text class="site-gen-value" data-site-gen="gen-yesterday" x="${layout.chipSiteGenValueX}" y="398" text-anchor="end">—</text>
          <text class="site-gen-value site-gen-fin" data-site-gen="fin-yesterday" x="${layout.chipSiteGenFinX}" y="398" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="418">Today</text>
          <text class="site-gen-value" data-site-gen="gen-today" x="${layout.chipSiteGenValueX}" y="418" text-anchor="end">—</text>
          <text class="site-gen-value site-gen-fin" data-site-gen="fin-today" x="${layout.chipSiteGenFinX}" y="418" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="438">Week</text>
          <text class="site-gen-value" data-site-gen="gen-week" x="${layout.chipSiteGenValueX}" y="438" text-anchor="end">—</text>
          <text class="site-gen-value site-gen-fin" data-site-gen="fin-week" x="${layout.chipSiteGenFinX}" y="438" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="458">Month</text>
          <text class="site-gen-value" data-site-gen="gen-month" x="${layout.chipSiteGenValueX}" y="458" text-anchor="end">—</text>
          <text class="site-gen-value site-gen-fin" data-site-gen="fin-month" x="${layout.chipSiteGenFinX}" y="458" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="478">YTD</text>
          <text class="site-gen-value" data-site-gen="gen-ytd" x="${layout.chipSiteGenValueX}" y="478" text-anchor="end">—</text>
          <text class="site-gen-value site-gen-fin" data-site-gen="fin-ytd" x="${layout.chipSiteGenFinX}" y="478" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="498">Year</text>
          <text class="site-gen-value" data-site-gen="gen-year" x="${layout.chipSiteGenValueX}" y="498" text-anchor="end">—</text>
          <text class="site-gen-value site-gen-fin" data-site-gen="fin-year" x="${layout.chipSiteGenFinX}" y="498" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="518">All time</text>
          <text class="site-gen-value" data-site-gen="gen-alltime" x="${layout.chipSiteGenValueX}" y="518" text-anchor="end">—</text>
          <text class="site-gen-value site-gen-fin" data-site-gen="fin-alltime" x="${layout.chipSiteGenFinX}" y="518" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="538">Capacity Factor (%)</text>
          <text class="site-gen-value" data-site-gen="capacity" x="${layout.chipSiteGenValueX}" y="538" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="558">Power (MW)</text>
          <text class="site-gen-value" data-site-gen="power" x="${layout.chipSiteGenValueX}" y="558" text-anchor="end">—</text>
        </g>
      </g>
    `;
  }

  // ---- live update ------------------------------------------------------

  _update() {
    if (!this.config || !this.shadowRoot) return;
    const root = this.shadowRoot;
    const config = this.config;

    // National grid: owner & site export and to-grid-today.
    const ownerEnergyKwh = this._num(config.owner_grid_energy_entity);
    const siteEnergyKwh = this._num(config.grid_energy_entity);
    const ownerPowerKw = this._num(config.owner_power_entity);
    const sitePowerMw = this._num(config.farm_power_entity);

    // Owner export is reported in kW, but the API often has no value for the
    // tiny owner share. Fall back to scaling the site export by the owner's
    // share of today's generation when owner power is unavailable.
    let ownerExportKw = ownerPowerKw;
    if (
      ownerExportKw === null &&
      sitePowerMw !== null &&
      ownerEnergyKwh !== null &&
      siteEnergyKwh !== null &&
      siteEnergyKwh > 0
    ) {
      ownerExportKw = sitePowerMw * 1000 * (ownerEnergyKwh / siteEnergyKwh);
    }
    const ownerPowerText = this._powerText(ownerExportKw);
    let sitePowerText =
      sitePowerMw === null ? { value: "—", unit: "" } : { value: this._fmt(sitePowerMw, 2), unit: "MW" };
    this._setText(root, '[data-grid="power"]', sitePowerText.value);
    this._setText(root, '[data-grid="power-unit"]', sitePowerText.unit);

    const siteEnergy = this._scaleKwh(siteEnergyKwh);
    this._setText(root, '[data-grid="energy"]', siteEnergy.value);
    this._setText(root, '[data-grid="energy-unit"]', siteEnergy.unit);

    // Header chips
    const wind = this._num(config.wind_speed_entity);
    this._setText(root, '[data-chip="wind"]', wind === null ? "—" : `${this._fmt(wind)} m/s`);
    const active = this._num(config.active_entity);
    this._setText(root, '[data-chip="active"]', active === null ? "—" : `${this._fmt(active, 0)} Turbines Active`);
    const forecast = this._num(config.wind_forecast_entity);
    this._setText(root, '[data-chip="forecast"]', forecast === null ? "—" : `${this._fmt(forecast)} m/s`);

    // Generation & capacity panel (top right) — timeframe values
    (config.owner_generation_entities || []).forEach((item) => {
      const key = `gen-${item.name.toLowerCase().replace(/\s/g, "-")}`;
      const val = this._num(item.entity);
      const scaled = val !== null ? this._scaleKwh(val) : { value: "—", unit: "" };
      this._setText(root, `[data-user-gen="${key}"]`, scaled.value === "—" ? scaled.value : `${scaled.value} ${scaled.unit}`);
      this._setChipStale(root.querySelector(`[data-user-gen="${key}"]`), item.entity);
      const fin = this._num(item.value_entity);
      this._setText(root, `[data-user-gen="fin-${item.name.toLowerCase().replace(/\s/g, "-")}"]`, fin === null ? "—" : `£${this._fmt(fin, 2)}`);
      this._setChipStale(root.querySelector(`[data-user-gen="fin-${item.name.toLowerCase().replace(/\s/g, "-")}"]`), item.value_entity);
    });

    const siteCap = this._num(config.capacity_entity);
    // Your share: owner export power is reported in kW; display in watts.
    this._setText(root, '[data-user-gen="share"]', ownerExportKw === null ? "—" : `${this._fmt(ownerExportKw * 1000, 0)} W`);
    // Owner share (per myriad, ‱) as the single source of truth. Prefer the
    // capacity-derived owner_share entity (in %) when set; it is the fixed share
    // of watts bought and does not vary with generation or capacity factor.
    // Fall back to today's observed owner/site generation ratio.
    const ownerSharePct = this._num(config.owner_share_entity);
    const sharePct =
      ownerSharePct !== null
        ? ownerSharePct
        : ownerEnergyKwh !== null && siteEnergyKwh !== null && siteEnergyKwh > 0
          ? (ownerEnergyKwh / siteEnergyKwh) * 100
          : null;
    this._setText(root, '[data-user-gen="sharepct"]', sharePct === null ? "—" : `${this._fmt(sharePct * 100, 2)}‱`);

    // Site Capacity panel — timeframe values
    (config.site_generation_entities || []).forEach((item) => {
      const key = `gen-${item.name.toLowerCase().replace(/\s/g, "-")}`;
      const val = this._num(item.entity);
      const scaled = val !== null ? this._scaleKwh(val) : { value: "—", unit: "" };
      this._setText(root, `[data-site-gen="${key}"]`, scaled.value === "—" ? scaled.value : `${scaled.value} ${scaled.unit}`);
      this._setChipStale(root.querySelector(`[data-site-gen="${key}"]`), item.entity);
      const fin = this._num(item.value_entity);
      this._setText(root, `[data-site-gen="fin-${item.name.toLowerCase().replace(/\s/g, "-")}"]`, fin === null ? "—" : `£${this._fmt(fin, 2)}`);
      this._setChipStale(root.querySelector(`[data-site-gen="fin-${item.name.toLowerCase().replace(/\s/g, "-")}"]`), item.value_entity);
    });

    this._setText(root, '[data-site-gen="capacity"]', siteCap === null ? "—" : `${this._fmt(siteCap, 1)}%`);
    this._setChipStale(root.querySelector('[data-site-gen="capacity"]'), config.capacity_entity);
    sitePowerText = sitePowerMw === null ? { value: "—", unit: "" } : { value: this._fmt(sitePowerMw, 2), unit: "MW" };
    this._setText(root, '[data-site-gen="power"]', `${sitePowerText.value} ${sitePowerText.unit}`);

    // Version pill: Running vs Latest, green up-to-date, amber update available
    const versionPill = root.querySelector('[data-version="indicator"]');
    if (versionPill) {
      const updateEntity = "update.kirk_hill_wind_farm_update";
      const installed = this._attr(updateEntity, "installed_version") || `v${KIRKHILL_WIND_SCADA_VERSION}`;
      const latest = this._attr(updateEntity, "latest_version") || installed;
      const updateAvail = installed !== latest;
      versionPill.classList.toggle("update-available", updateAvail);
      this._setText(root, '[data-version="text"]', `Running: ${installed}  Latest: ${latest}`);
    }

    // Turbine status pill: green all active, amber some offline, red all off
    const alarmIndicator = root.querySelector('[data-alarm="indicator"]');
    if (alarmIndicator) {
      const active = this._num(config.active_entity);
      const total = config.turbines.length;
      const offline = active === null ? total : total - active;
      alarmIndicator.classList.toggle("fault", offline >= total);
      alarmIndicator.classList.toggle("warn", offline > 0 && offline < total);
    }

    // API connectivity pill: green OK, amber rate-limited, red down (flashes)
    const apiIndicator = root.querySelector('[data-api="indicator"]');
    if (apiIndicator) {
      const apiEntity = config.api_status_entity;
      const apiState = apiEntity ? this._str(apiEntity) : "";
      const apiUp = apiState === "on";
      const apiUnavailable = !apiEntity || apiState === "" || apiState === "unavailable" || apiState === "unknown";
      const inDown = !apiUnavailable && !apiUp;
      const rateLimited = apiUp && this._attr(apiEntity, "rate_limited") === true;
      apiIndicator.classList.toggle("api-down", inDown);
      apiIndicator.classList.toggle("api-rate-limited", rateLimited);
      this._setText(
        root,
        '[data-api="text"]',
        apiUp ? (rateLimited ? "API LIMITED" : "API OK") : inDown ? "API DOWN" : "API —"
      );
    }

    // Turbines
    const totalKw = config.turbines.reduce((sum, t) => {
      const p = this._num(t.power_entity);
      return sum + (Number.isFinite(p) ? p : 0);
    }, 0);

    config.turbines.forEach((t, i) => {
      const node = root.querySelector(`[data-turbine="${CSS.escape(t.id || `T${i + 1}`)}"]`);
      if (!node) return;
      const power = this._num(t.power_entity);
      const stateText = this._str(t.state_entity);
      const category = this._attr(t.state_entity, "status_category");
      const status = this._statusFor(stateText, category);
      const today = this._scaleKwh(this._num(t.generation_today_entity));
      const rotor = this._num(t.rotor_entity);
      const wind = this._num(t.wind_speed_entity);
      const opPct = this._num(t.capacity_entity);
      const last = this._fmtTime(this._attr(t.state_entity, "status_started_at"));

      this._setText(node, ".t-power", power === null ? "—" : `${this._fmt(power, 0)} kW`);
      this._setText(node, ".t-status", status.label);
      this._setText(node, ".t-op", opPct === null ? "—" : `${this._fmt(opPct, 1)}%`);
      this._setText(node, ".t-wind", wind === null ? "—" : `${this._fmt(wind)} m/s`);
      this._setText(node, ".t-detail", `Today ${today.value} ${today.unit}${rotor !== null ? ` · ${this._fmt(rotor, 1)} rpm` : ""}`);
      this._setText(node, ".t-last", `Status since ${last}`);
      const pill = node.querySelector(".status-pill");
      if (pill) {
        pill.setAttribute("class", "status-pill " + status.class);
        pill.removeAttribute("fill");
      }
      const statusText = node.querySelector(".t-status");
      if (statusText) statusText.style.fill = status.color;
      node.querySelectorAll(".node-rect").forEach((r) => r.setAttribute("data-status", status.label));

      // Flow dot speed
      const dot = root.querySelector(`[data-flow="t${i}"]`);
      if (dot) {
        const len = parseFloat(dot.getAttribute("data-len")) || 0;
        const dur = this._dotDur(power, len);
        dot.setAttribute("opacity", dur ? "1" : "0");
        const motion = dot.querySelector("animateMotion");
        if (motion && dur) motion.setAttribute("dur", dur);
      }
    });

    // Bus → grid flow dot
    const busDot = root.querySelector('[data-flow="grid"]');
    if (busDot) {
      const len = parseFloat(busDot.getAttribute("data-len")) || 0;
      const dur = this._dotDur(totalKw, len);
      busDot.setAttribute("opacity", dur ? "1" : "0");
      const motion = busDot.querySelector("animateMotion");
      if (motion && dur) motion.setAttribute("dur", dur);
    }
  }

  _setText(root, selector, value) {
    const el = root.querySelector(selector);
    if (el) el.textContent = value;
  }

  // ---- styles -----------------------------------------------------------

  _styles() {
    return `
      :host {
        display: block; width: 100%; height: 100%; -webkit-tap-highlight-color: transparent;
        

        
        
        
        
        --khscada-font-family: var(--primary-font-family, var(--font-family, Roboto, sans-serif));
        --khscada-primary-color: var(--primary-text-color, var(--text-primary-color, #1c2026));
        --khscada-secondary-color: var(--secondary-text-color, #546e7a);
        --khscada-disabled-color: var(--disabled-text-color, var(--secondary-text-color, #9e9e9e));
        --khscada-accent-color: var(--primary-color, #0284c7);
        --khscada-success-color: var(--success-color, #16a34a);
        --khscada-error-color: var(--error-color, #ef4444);
        --khscada-warn-color: var(--warning-color, #f59e0b);
        --khscada-card-bg: var(--card-background-color, var(--paper-card-background-color, #ffffff));
        --khscada-panel-bg: var(--card-background-color, var(--paper-card-background-color, #ffffff));
        --khscada-bus-bg: color-mix(in srgb, var(--primary-color, #0284c7) 8%, transparent);
        --khscada-grid-bg: color-mix(in srgb, var(--success-color, #16a34a) 8%, transparent);
        --khscada-alarm-ok-bg: color-mix(in srgb, var(--success-color, #4caf50) 10%, transparent);
        --khscada-alarm-warn-bg: color-mix(in srgb, var(--warning-color, #ffb300) 10%, transparent);
        --khscada-alarm-fault-bg: color-mix(in srgb, var(--error-color, #ef5350) 10%, transparent);
        --khscada-divider: var(--divider-color, var(--ha-divider-color, #cbd5e1));
      }
      ha-card { overflow: hidden; height: calc(100vh - 64px); box-sizing: border-box; background: transparent; }
      .shell { padding: 12px; background: var(--khscada-card-bg); border-radius: 12px; height: 100%; box-sizing: border-box; }
      svg { width: 100%; height: 100%; display: block; touch-action: none; user-select: none; -webkit-user-select: none; }

      /* Modal chart timeframe bar */
      .time-range-bar.modal-time-range { margin: 10px 0 6px; padding: 6px 10px; }
      .time-range-bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 8px 12px; background: var(--khscada-card-bg); border-radius: 12px; margin-bottom: 8px; }
      .time-range-label { font: 600 var(--ha-font-size-small, 12px) var(--khscada-font-family); color: var(--khscada-secondary-color); margin-right: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
      .time-range-btn { font: 600 var(--ha-font-size-small, 12px) var(--khscada-font-family); color: var(--khscada-secondary-color); background: var(--khscada-divider); border: none; border-radius: 14px; padding: 4px 12px; cursor: pointer; }
      .time-range-btn:hover { color: var(--khscada-primary-color); }
      .time-range-btn.active { background: color-mix(in srgb, var(--khscada-accent-color) 20%, transparent); color: var(--khscada-accent-color); }
      .bg { fill: var(--khscada-card-bg); }
      text { font-family: var(--khscada-font-family); fill: var(--khscada-primary-color); }

      /* Lines */
      .feed-line { stroke: var(--khscada-accent-color); stroke-opacity: 0.35; stroke-width: 3; }
      .flow-dot { fill: var(--khscada-accent-color); }

      /* Turbine nodes */
      .node-rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .node-rect[data-status] { opacity: 1; }
      .turbine:hover .node-rect { stroke: var(--khscada-accent-color); }
      .t-id { font: 600 calc(var(--ha-font-size-xxlarge, 20px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .status-pill { fill: color-mix(in srgb, var(--khscada-success-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-running { fill: color-mix(in srgb, var(--khscada-success-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-ready { fill: color-mix(in srgb, var(--khscada-accent-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-starting { fill: color-mix(in srgb, var(--khscada-warn-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-curtailed { fill: color-mix(in srgb, var(--khscada-warn-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-no-wind { fill: color-mix(in srgb, var(--khscada-accent-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-stopped { fill: color-mix(in srgb, var(--khscada-disabled-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-fault { fill: color-mix(in srgb, var(--khscada-error-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-maintenance { fill: color-mix(in srgb, var(--khscada-accent-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-unavailable { fill: color-mix(in srgb, var(--khscada-disabled-color) 15%, var(--khscada-card-bg)); }
      .status-pill.status-unknown { fill: color-mix(in srgb, var(--khscada-disabled-color) 15%, var(--khscada-card-bg)); }
      .t-status { fill: var(--khscada-primary-color); font: 600 calc(var(--ha-font-size-small, 12px) * var(--khscada-fs, 1)) var(--khscada-font-family); text-anchor: middle; }
      .t-power { font: 600 calc(var(--ha-font-size-xlarge, 18px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .t-label { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size-small, 12px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .t-op { font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .t-wind { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .t-detail { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .t-last { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size-small, 12px) * var(--khscada-fs, 1)) var(--khscada-font-family); }

      /* Bus */
      .bus rect { fill: var(--khscada-bus-bg); stroke: var(--khscada-accent-color); stroke-width: 2; }

      /* Transformer label (overlaid down the site collection bus) */
      .xfmr-title { font: 600 calc(var(--ha-font-size-xlarge, 18px) * var(--khscada-fs, 1)) var(--khscada-font-family); }

      /* Grid node */
      .grid-rect { fill: var(--khscada-grid-bg); stroke: var(--khscada-success-color); stroke-width: 2; }
      .grid-title { fill: var(--khscada-success-color); font: 600 calc(var(--ha-font-size-xxlarge, 20px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .grid-label { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size-large, 16px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .grid-power { font: 600 calc(var(--ha-font-size-xxlarge, 20px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .grid-energy { font: 600 calc(var(--ha-font-size-xxlarge, 20px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .grid-unit { fill: var(--khscada-disabled-color); font: calc(var(--ha-font-size-large, 16px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .grid-divider { stroke: var(--khscada-success-color); stroke-width: 2; }

      /* Chips */
      .chips rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .chip-label { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size-small, 12px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .chip-value { font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }

      /* Generation & capacity panel (top right) */
      .gen-section-heading { fill: var(--khscada-secondary-color); font: 600 calc(var(--ha-font-size-large, 16px) * var(--khscada-fs, 1)) var(--khscada-font-family); letter-spacing: 0.4px; }
      .user-gen rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; cursor: pointer; }
      .user-gen rect:hover { stroke: var(--khscada-primary-color); stroke-width: 2; }
      .user-gen-title { font: 600 calc(var(--ha-font-size-xlarge, 18px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .user-gen-label { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .user-gen-colh, .site-gen-colh { fill: var(--khscada-primary-color); font: 600 calc(var(--ha-font-size-small, 12px) * var(--khscada-fs, 1)) var(--khscada-font-family); letter-spacing: 0.6px; }
      .user-gen-value { font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .user-gen-fin { fill: var(--khscada-success-color); font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .site-gen-value { fill: var(--khscada-primary-color); font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .site-gen-fin { fill: var(--khscada-success-color); font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .user-gen-share { fill: var(--khscada-success-color); font: 600 calc(var(--ha-font-size-xlarge, 18px) * var(--khscada-fs, 1)) var(--khscada-font-family); }

      /* Site Generation & Capacity panel (below Owner) */
      .site-gen rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; cursor: pointer; }
      .site-gen rect:hover { stroke: var(--khscada-primary-color); stroke-width: 2; }
      .site-gen-title { font: 600 calc(var(--ha-font-size-xlarge, 18px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .site-gen-label { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }

      /* Wind & forecast panel (below Site Generation) */
      .wind-panel rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .wind-title { font: 600 calc(var(--ha-font-size-large, 16px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .wind-label { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .wind-value { font: 600 calc(var(--ha-font-size-xlarge, 18px) * var(--khscada-fs, 1)) var(--khscada-font-family); }

      /* Alarm indicator */
      .alarm rect { fill: var(--khscada-alarm-ok-bg); stroke: var(--khscada-success-color); stroke-width: 2; }
      .alarm-text { fill: var(--khscada-success-color); font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .alarm.fault rect { fill: var(--khscada-alarm-fault-bg); stroke: var(--khscada-error-color); stroke-width: 2; }
      .alarm.fault .alarm-text { fill: var(--khscada-error-color); }
      .alarm.fault { animation: khscada-alarm-flash 1s steps(1, end) infinite; }
      .alarm.warn rect { fill: var(--khscada-alarm-warn-bg); stroke: var(--khscada-warn-color, #ffb300); stroke-width: 2; }
      .alarm.warn .alarm-text { fill: var(--khscada-warn-color, #ffb300); }
      @keyframes khscada-alarm-flash {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.15; }
      }

      /* API connectivity pill */
      .api-status rect { fill: var(--khscada-alarm-ok-bg); stroke: var(--khscada-success-color); stroke-width: 2; }
      .api-status-text { fill: var(--khscada-success-color); font: 600 calc(var(--ha-font-size, 14px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .api-status.api-down rect { fill: var(--khscada-alarm-fault-bg); stroke: var(--khscada-error-color); stroke-width: 2; }
      .api-status.api-down .api-status-text { fill: var(--khscada-error-color); }
      .api-status.api-down { animation: khscada-alarm-flash 1s steps(1, end) infinite; }
      .api-status.api-rate-limited rect { fill: var(--khscada-alarm-warn-bg); stroke: var(--khscada-warn-color, #ffb300); stroke-width: 2; }
      .api-status.api-rate-limited .api-status-text { fill: var(--khscada-warn-color, #ffb300); }

      /* Version badge */
      .version-pill rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .version-text { fill: var(--khscada-secondary-color); font: calc(var(--ha-font-size-small, 12px) * var(--khscada-fs, 1)) var(--khscada-font-family); }
      .version-pill.update-available rect { fill: var(--khscada-alarm-warn-bg); stroke: var(--khscada-warn-color, #ffb300); stroke-width: 2; }
      .version-pill.update-available .version-text { fill: var(--khscada-warn-color, #ffb300); }

      .empty { padding: 24px 16px; color: var(--khscada-secondary-color); }

      /* Turbine detail modal */
      .turbine-detail-modal { position: fixed; inset: 0; z-index: 100; display: flex; align-items: center; justify-content: center; }
      .turbine-detail-modal .modal-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.5); }
      .turbine-detail-modal .modal-content {
        position: relative; width: 95%; max-width: 1200px; max-height: 90vh;
        background: var(--khscada-card-bg); border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.2); display: flex; flex-direction: column;
        overflow: hidden;
      }
      .turbine-detail-modal .modal-header { display: flex; align-items: center; justify-content: space-between;
        padding: 16px 20px; border-bottom: 1px solid var(--khscada-divider); }
      .turbine-detail-modal .modal-header h2 { margin: 0; font: 600 var(--ha-font-size-xlarge, 18px) var(--khscada-font-family); color: var(--khscada-primary-color); }
      .turbine-detail-modal .modal-close { background: none; border: none; font-size: 22px; cursor: pointer; color: var(--khscada-secondary-color); padding: 4px 8px; border-radius: 6px; }
      .turbine-detail-modal .modal-close:hover { background: var(--khscada-divider); }
      .turbine-detail-modal .modal-body { padding: 16px; overflow-y: auto; max-height: calc(90vh - 70px); }

      /* Turbine detail sections */
      .td-section { margin-bottom: 20px; }
      .td-section:last-child { margin-bottom: 0; }
      .td-section h3 { margin: 0 0 10px; font: 600 var(--ha-font-size, 14px) var(--khscada-font-family); color: var(--khscada-primary-color); text-transform: uppercase; letter-spacing: 0.5px; }

      /* Status badge */
      .td-status-badge {
        display: inline-flex; align-items: center; gap: 8px;
        padding: 6px 14px; border-radius: 20px; margin-bottom: 14px;
        font: 600 var(--ha-font-size-small, 12px) var(--khscada-font-family);
        background: color-mix(in srgb, var(--badge-color) 15%, transparent);
        color: var(--badge-color); border: 1px solid color-mix(in srgb, var(--badge-color) 30%, transparent);
      }
      .td-status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--badge-color); }

      /* KPI grid */
      .td-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-bottom: 10px; }
      .td-kpi {
        background: var(--khscada-card-bg); border: 1px solid var(--khscada-divider); border-radius: 8px;
        padding: 10px 12px; display: flex; flex-direction: column; gap: 2px;
      }
      .td-kpi-label { font: var(--ha-font-size-small, 12px) var(--khscada-font-family); color: var(--khscada-secondary-color); }
      .td-kpi-value { font: 600 var(--ha-font-size-xlarge, 18px) var(--khscada-font-family); color: var(--khscada-primary-color); }
      .td-kpi-unit { font: var(--ha-font-size-small, 12px) var(--khscada-font-family); color: var(--khscada-secondary-color); }
      .td-state-line { font: var(--ha-font-size-small, 12px) var(--khscada-font-family); color: var(--khscada-secondary-color); padding: 4px 0; }

      /* Turbine status table */
      .ts-table { width: 100%; border-collapse: collapse; font: var(--ha-font-size-small, 12px) var(--khscada-font-family); }
      .ts-table th { text-align: left; padding: 6px 8px; border-bottom: 2px solid var(--khscada-divider); color: var(--khscada-secondary-color); font-weight: 600; }
      .ts-table td { padding: 6px 8px; border-bottom: 1px solid var(--khscada-divider); color: var(--khscada-primary-color); vertical-align: middle; }
      .ts-tid { font-weight: 600; white-space: nowrap; }
      .ts-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
      .ts-since { white-space: nowrap; color: var(--khscada-secondary-color); }
      .ts-state { color: var(--khscada-secondary-color); font-size: 0.9em; }

      /* Turbine history sub-table */
      .ts-history td { padding: 4px 8px; background: color-mix(in srgb, var(--khscada-card-bg) 50%, transparent); }
      .ts-history-content { padding: 4px 0; }
      .ts-hist-table { width: 100%; border-collapse: collapse; font: var(--ha-font-size-small, 11px) var(--khscada-font-family); }
      .ts-hist-table th { text-align: left; padding: 3px 6px; border-bottom: 1px solid var(--khscada-divider); color: var(--khscada-secondary-color); font-weight: 600; font-size: 0.9em; }
      .ts-hist-table td { padding: 3px 6px; border-bottom: 1px solid color-mix(in srgb, var(--khscada-divider) 50%, transparent); color: var(--khscada-primary-color); }
      .ts-hist-detail { color: var(--khscada-secondary-color); font-size: 0.9em; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .ts-hist-empty { color: var(--khscada-secondary-color); font-style: italic; font-size: 0.9em; }

      /* Spec grid */
      .td-spec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; }
      .td-spec {
        display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
        padding: 6px 0; border-bottom: 1px solid var(--khscada-divider);
      }
      .td-spec-label { font: var(--ha-font-size-small, 12px) var(--khscada-font-family); color: var(--khscada-secondary-color); white-space: nowrap; }
      .td-spec-value { font: var(--ha-font-size, 14px) var(--khscada-font-family); color: var(--khscada-primary-color); text-align: right; }
      .td-coords-link { color: inherit; text-decoration: none; border-bottom: 1px dotted var(--khscada-primary-color); }
      .td-coords-link:hover { border-bottom-style: solid; }

      /* Charts */
      .chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 16px; }
      .chart-item { background: var(--khscada-card-bg); border: 1px solid var(--khscada-divider); border-radius: 8px; padding: 12px; }
      .chart-item.large { grid-column: span 2; }
      .chart-item h3 { margin: 0 0 10px; font: 600 var(--ha-font-size, 14px) var(--khscada-font-family); color: var(--khscada-primary-color); }
      .apex-chart { position: relative; width: 100%; height: 100%; min-height: 280px; }
      .chart-placeholder {
        position: absolute; inset: 0; z-index: 2; pointer-events: none;
        display: flex; align-items: center; justify-content: center;
        color: var(--khscada-secondary-color);
        font: var(--ha-font-size, 14px) var(--khscada-font-family);
      }
      .apexcharts-tooltip {
        background: var(--khscada-card-bg) !important;
        color: var(--khscada-primary-color) !important;
        border: 1px solid var(--khscada-divider) !important;
        box-shadow: none !important;
      }
      .apexcharts-tooltip-title {
        background: var(--khscada-card-bg) !important;
        color: var(--khscada-primary-color) !important;
        border-bottom: 1px solid var(--khscada-divider) !important;
      }
      @media (max-width: 900px) {
        .chart-item.large { grid-column: span 1; }
        .chart-grid { grid-template-columns: 1fr; }
        .td-kpi-grid { grid-template-columns: repeat(2, 1fr); }
      }

      .zoom-overlay { cursor: pointer; }
      .zoom-overlay rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; transition: stroke 0.2s; }
      .zoom-overlay rect:hover { stroke: var(--khscada-accent-color); }
      .zoom-overlay text { fill: var(--khscada-primary-color); font-family: var(--khscada-font-family); }
    `;
  }
}

// Bus → grid flow dot is defined inside _buildTransformer().
if (!customElements.get("kirkhill-wind-scada")) {
  customElements.define("kirkhill-wind-scada", KirkHillWindScada);
}
