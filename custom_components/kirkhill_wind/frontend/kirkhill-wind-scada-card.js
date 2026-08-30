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
 */
class KirkHillWindScada extends HTMLElement {
  static get VIEWBOX() {
    return { w: 1240, h: 860, wMin: 900, wMax: 1800, hMin: 1052, hMax: 1600 };
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
  }

  connectedCallback() {
    if (this.config) this._render();
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
    if (this.config) this._update();
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, rows: 12, min_rows: 8, max_rows: 16 };
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

  _fmt(n, decimals = 1) {
    if (n === null || n === undefined || !Number.isFinite(n)) return "—";
    return n.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
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
    return KirkHillWindScada.STATUS[key] || KirkHillWindScada.STATUS.unknown;
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
          <svg viewBox="0 0 ${layout.W} ${layout.H}" role="img" aria-label="Wind farm SCADA diagram">
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
              ${this._buildLegend(layout)}
            </g>
            <g class="zoom-overlay" data-zoom-reset="btn">
              <rect x="${layout.resetBtnX}" y="${layout.resetBtnY}" width="${44 * layout.scaleX}" height="48" rx="10"/>
              <text x="${layout.resetBtnX + 22 * layout.scaleX}" y="${layout.resetBtnY + 32}" text-anchor="middle" font-size="18">⟲</text>
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
    const modal = document.createElement("div");
    modal.className = "turbine-detail-modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close="backdrop"></div>
      <div class="modal-content">
        <div class="modal-header">
          <h2>${turbine.id} — Historical Data</h2>
          <button class="modal-close" data-close="close" aria-label="Close">✕</button>
        </div>
        <div class="modal-body">
          <div class="chart-grid">
            <div class="chart-item large">
              <h3>Power (25h)</h3>
              <div id="chart-power" class="apex-chart"></div>
            </div>
            <div class="chart-item large">
              <h3>Wind vs Power</h3>
              <div id="chart-wind-power" class="apex-chart"></div>
            </div>
            <div class="chart-item">
              <h3>Capacity Factor (25h)</h3>
              <div id="chart-capacity" class="apex-chart"></div>
            </div>
            <div class="chart-item">
              <h3>Rotor Speed (25h)</h3>
              <div id="chart-rotor" class="apex-chart"></div>
            </div>
            <div class="chart-item">
              <h3>Wind Speed (25h)</h3>
              <div id="chart-wind" class="apex-chart"></div>
            </div>
            <div class="chart-item">
              <h3>Generation Today</h3>
              <div id="chart-generation" class="apex-chart"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    this.shadowRoot.appendChild(modal);
    this._turbineDetailTurbine = turbine;
    this._turbineDetailModal = modal;

    // Add close handlers
    modal.querySelectorAll("[data-close]").forEach(el => {
      el.addEventListener("click", () => this._closeTurbineDetailModal());
    });

    // Close on Escape
    this._boundKeydown = (e) => { if (e.key === "Escape") this._closeTurbineDetailModal(); };
    window.addEventListener("keydown", this._boundKeydown);

    // Initialize charts after a brief delay for DOM
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
    this._turbineDetailTurbine = null;
    if (this._boundKeydown) {
      window.removeEventListener("keydown", this._boundKeydown);
      this._boundKeydown = null;
    }
  }

  async _initTurbineCharts(turbine) {
    const now = new Date();
    const start = new Date(now.getTime() - 25 * 3600 * 1000);
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

    try {
      await this._ensureApexCharts();
      const history = await this._fetchHistory(entities, startISO, endISO);
      this._renderCharts(turbine.id, history);
    } catch (err) {
      console.error("Failed to load turbine history:", err);
    }
  }

  _ensureApexCharts() {
    if (window.ApexCharts) return Promise.resolve();
    if (this._apexLoadPromise) return this._apexLoadPromise;
    const src = `${this._hass.connection.baseUrl}/kirkhill_wind/apexcharts.js`;
    this._apexLoadPromise = new Promise((resolve) => {
      const timer = setTimeout(() => resolve(), 15000);
      const script = document.createElement("script");
      script.src = src;
      script.onload = () => { clearTimeout(timer); resolve(); };
      script.onerror = () => { clearTimeout(timer); resolve(); };
      document.head.appendChild(script);
    });
    return this._apexLoadPromise;
  }

  async _fetchHistory(entities, start, end) {
    const hass = this._hass;
    const results = {};

    for (const [key, entityId] of Object.entries(entities)) {
      if (!entityId) { results[key] = []; continue; }
      try {
        const url = `${hass.connection.baseUrl}/api/history/period/${start}?end_time=${end}&filter_entity_id=${entityId}&minimal_response=true`;
        const response = await fetch(url, { headers: { Authorization: `Bearer ${hass.auth.accessToken}` } });
        const data = await response.json();
        results[key] = Array.isArray(data) ? data[0] || [] : [];
      } catch (e) {
        results[key] = [];
      }
    }
    return results;
  }

  _renderCharts(turbineId, history) {
    if (!window.ApexCharts) return;

    const charts = {};

    // Power chart
    if (history.power?.length) {
      charts.power = new ApexCharts(this.shadowRoot.querySelector("#chart-power"), {
        series: [{ name: "Power (kW)", data: history.power.map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)]) }],
        chart: { type: "area", height: 300, toolbar: { show: false }, background: "transparent" },
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "kW" } },
        stroke: { curve: "smooth", width: 2 },
        fill: { type: "gradient", gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.1, stops: [0, 100] } },
        colors: ["#0284c7"],
        tooltip: { x: { format: "HH:mm" } },
      });
      charts.power.render();
    }

    // Wind vs Power scatter
    if (history.wind?.length && history.power?.length) {
      // Interpolate wind to power timestamps
      const windMap = new Map(history.wind.map(w => [new Date(w.last_changed).getTime(), this._numVal(w.state)]));
      const scatterData = history.power
        .map(p => {
          const t = new Date(p.last_changed).getTime();
          const wind = windMap.get(t) || this._interpolateWind(history.wind, t);
          return wind !== null ? { x: this._numVal(p.state), y: wind } : null;
        })
        .filter(d => d !== null);
      if (scatterData.length) {
        charts.windPower = new ApexCharts(this.shadowRoot.querySelector("#chart-wind-power"), {
          series: [{ name: "Wind vs Power", data: scatterData }],
          chart: { type: "scatter", height: 300, toolbar: { show: false }, background: "transparent" },
          xaxis: { title: { text: "Power (kW)" } },
          yaxis: { title: { text: "Wind (m/s)" } },
          colors: ["#f59e0b"],
          markers: { size: 4 },
        });
        charts.windPower.render();
      }
    }

    // Capacity factor
    if (history.capacity?.length) {
      charts.capacity = new ApexCharts(this.shadowRoot.querySelector("#chart-capacity"), {
        series: [{ name: "Capacity %", data: history.capacity.map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)]) }],
        chart: { type: "line", height: 250, toolbar: { show: false }, background: "transparent" },
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "%" }, max: 100 },
        stroke: { curve: "smooth", width: 2 },
        colors: ["#22c55e"],
      });
      charts.capacity.render();
    }

    // Rotor speed
    if (history.rotor?.length) {
      charts.rotor = new ApexCharts(this.shadowRoot.querySelector("#chart-rotor"), {
        series: [{ name: "RPM", data: history.rotor.map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)]) }],
        chart: { type: "line", height: 250, toolbar: { show: false }, background: "transparent" },
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "RPM" } },
        stroke: { curve: "smooth", width: 2 },
        colors: ["#8b5cf6"],
      });
      charts.rotor.render();
    }

    // Wind speed
    if (history.wind?.length) {
      charts.wind = new ApexCharts(this.shadowRoot.querySelector("#chart-wind"), {
        series: [{ name: "Wind (m/s)", data: history.wind.map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)]) }],
        chart: { type: "area", height: 250, toolbar: { show: false }, background: "transparent" },
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "m/s" } },
        stroke: { curve: "smooth", width: 2 },
        fill: { type: "gradient", gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0.05 } },
        colors: ["#f59e0b"],
      });
      charts.wind.render();
    }

    // Generation today (step line)
    if (history.generation?.length) {
      charts.generation = new ApexCharts(this.shadowRoot.querySelector("#chart-generation"), {
        series: [{ name: "Generation (kWh)", data: history.generation.map(p => [new Date(p.last_changed).getTime(), this._numVal(p.state)]) }],
        chart: { type: "stepLine", height: 250, toolbar: { show: false }, background: "transparent" },
        xaxis: { type: "datetime" },
        yaxis: { title: { text: "kWh" } },
        stroke: { width: 2 },
        colors: ["#059669"],
      });
      charts.generation.render();
    }

    this._turbineDetailCharts = charts;
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
      const g = el && el.closest ? el.closest("g.turbine") : null;
      if (g) this._openTurbine(g);
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

    // Transformer label + National Grid live at the bottom of the card; the bus
    // runs down to them, so the flow reads turbines -> bus -> transformer ->
    // grid as a vertical single-line diagram on any window size.
    const gridY = H - 190;

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
      88,
      Math.min(120, Math.floor((gridY - tTop - 30 - (tCount - 1) * gapV) / Math.max(1, tCount)))
    );
    const pitch = bh + gapV;

    // Scale horizontal positions from design width (1240) to current viewBox width.
    // The two columns start with a small gap (40) that shrinks to nothing, then the
    // right column keeps sliding left until it sits directly under the left column,
    // merging the staircase into a single column at narrow widths. The vertical
    // pitch gains a small gap as the columns merge so stacked boxes never touch.
    const busX = 600 * scaleX;
    const leftColX = 30 * scaleX;
    const rightColX = (30 + (190 + 40) * (1 - collapse)) * scaleX;
    const boxW = 190 * scaleX;
    const feedEndX = busX;
    const gridRectX = 975 * scaleX;
    const transformerLineEndX = gridRectX;
    const transformerLineEndY = gridY - 135;
    const gridRectW = 225 * scaleX;
    const gridRightX = gridRectX + gridRectW;
    const ownerCx = 1015 * scaleX;
    const siteCx = 1205 * scaleX;
    const gridTitleX = (gridRectX + gridRightX) / 2;
    const gridDividerX1 = gridRectX + 10 * scaleX;
    const gridDividerX2 = gridRightX - 10 * scaleX;
    const chipLeftColX = 30 * scaleX;
    const chipRightColX = 152 * scaleX;
    const chipWindX = 400 * scaleX;
    const chipWindW = busX - chipWindX - 8;
    const chipWindTitleX = 412 * scaleX;
    const chipWindValueX = chipWindX + chipWindW - 12;
    const chipUserGenX = 910 * scaleX;
    const chipUserGenW = gridRightX - chipUserGenX;
    const chipUserGenTitleX = 922 * scaleX;
    const chipUserGenValueX = gridRightX - 10 * scaleX;
    const chipSiteGenX = 910 * scaleX;
    const chipSiteGenW = gridRightX - chipSiteGenX;
    const chipSiteGenTitleX = 922 * scaleX;
    const chipSiteGenValueX = gridRightX - 10 * scaleX;
    const resetBtnW = 44 * scaleX;
    const resetBtnH = 48;
    const resetBtnX = 30 * scaleX;
    const resetBtnY = legendY + (120 - resetBtnH) / 2;
    const legendX = resetBtnX + resetBtnW + 12 * scaleX;
    const legendW = 500 * scaleX;
    const xfmrTitleX = 630 * scaleX;
    const xfmrRotateX = 630 * scaleX;

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
      chipUserGenX,
      chipUserGenW,
      chipUserGenTitleX,
      chipUserGenValueX,
      chipSiteGenX,
      chipSiteGenW,
      chipSiteGenTitleX,
      chipSiteGenValueX,
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
    };
  }

  _fit() {
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
          <text class="t-power" x="${x + 14 * layout.scaleX}" y="${top + layout.bh - 50}">—</text>
          <text class="t-op" x="${x + layout.boxW - 14 * layout.scaleX}" y="${top + layout.bh - 50}" text-anchor="end">—</text>
          <text class="t-wind" x="${x + 14 * layout.scaleX}" y="${top + layout.bh - 34}">—</text>
          <text class="t-detail" x="${x + 14 * layout.scaleX}" y="${top + layout.bh - 21}"></text>
          <text class="t-last" x="${x + 14 * layout.scaleX}" y="${top + layout.bh - 10}"></text>
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
        <rect x="${layout.busX}" y="30" width="${60 * layout.scaleX}" height="${layout.busY2 - 30}" rx="6"/>
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
        <!-- Left side: Alarm + Active Turbines (above turbine list) -->
        <g class="alarm" data-alarm="indicator">
          <rect x="${layout.chipLeftColX}" y="24" width="${112 * layout.scaleX}" height="30" rx="15"/>
          <text class="alarm-text" data-alarm="text" x="${layout.chipLeftColX + 56 * layout.scaleX}" y="44" text-anchor="middle">OK</text>
        </g>
        <rect x="${layout.chipRightColX}" y="24" width="${150 * layout.scaleX}" height="30" rx="15"/>
        <text class="chip-label" x="${layout.chipRightColX + 10 * layout.scaleX}" y="44" text-anchor="start">Active Turbines</text>
        <text class="chip-value" data-chip="active" x="${layout.chipRightColX + 140 * layout.scaleX}" y="44" text-anchor="end">—</text>

        <!-- Wind & Forecast panel (left of bus, right of turbines) -->
        <g class="wind-panel" data-wind="panel">
          <rect x="${layout.chipWindX}" y="24" width="${layout.chipWindW}" height="82" rx="8"/>
          <text class="wind-title" x="${layout.chipWindTitleX}" y="38">Wind & Forecast</text>
          <text class="wind-label" x="${layout.chipWindTitleX}" y="58">Current Wind</text>
          <text class="wind-value" data-chip="wind" x="${layout.chipWindValueX}" y="58" text-anchor="end">—</text>
          <text class="wind-label" x="${layout.chipWindTitleX}" y="78">Forecast (1h)</text>
          <text class="wind-value" data-chip="forecast" x="${layout.chipWindValueX}" y="78" text-anchor="end">—</text>
        </g>

        <!-- Right side: Owner Generation & Capacity (far right) -->
        <g class="user-gen" data-user-gen="panel">
          <rect x="${layout.chipUserGenX}" y="24" width="${layout.chipUserGenW}" height="260" rx="8"/>
          <text class="user-gen-title" x="${layout.chipUserGenTitleX}" y="48">Owner Generation & Capacity</text>
          <!-- Generation timeframes -->
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="78">Yesterday</text>
          <text class="user-gen-value" data-user-gen="gen-yesterday" x="${layout.chipUserGenValueX}" y="78" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="100">Today</text>
          <text class="user-gen-value" data-user-gen="gen-today" x="${layout.chipUserGenValueX}" y="100" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="122">Week</text>
          <text class="user-gen-value" data-user-gen="gen-week" x="${layout.chipUserGenValueX}" y="122" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="144">Month</text>
          <text class="user-gen-value" data-user-gen="gen-month" x="${layout.chipUserGenValueX}" y="144" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="166">YTD</text>
          <text class="user-gen-value" data-user-gen="gen-ytd" x="${layout.chipUserGenValueX}" y="166" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="188">Year</text>
          <text class="user-gen-value" data-user-gen="gen-year" x="${layout.chipUserGenValueX}" y="188" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="210">All time</text>
          <text class="user-gen-value" data-user-gen="gen-alltime" x="${layout.chipUserGenValueX}" y="210" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="234">Your Share (W)</text>
          <text class="user-gen-value user-gen-share" data-user-gen="share" x="${layout.chipUserGenValueX}" y="234" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="256">Share (‱)</text>
          <text class="user-gen-value" data-user-gen="sharepct" x="${layout.chipUserGenValueX}" y="256" text-anchor="end">—</text>
        </g>

        <!-- Right side: Site Generation & Capacity (below Owner) -->
        <g class="site-gen" data-site-gen="panel">
          <rect x="${layout.chipSiteGenX}" y="300" width="${layout.chipSiteGenW}" height="260" rx="8"/>
          <text class="site-gen-title" x="${layout.chipSiteGenTitleX}" y="324">Site Generation & Capacity</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="354">Yesterday</text>
          <text class="site-gen-value" data-site-gen="gen-yesterday" x="${layout.chipSiteGenValueX}" y="354" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="376">Today</text>
          <text class="site-gen-value" data-site-gen="gen-today" x="${layout.chipSiteGenValueX}" y="376" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="398">Week</text>
          <text class="site-gen-value" data-site-gen="gen-week" x="${layout.chipSiteGenValueX}" y="398" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="420">Month</text>
          <text class="site-gen-value" data-site-gen="gen-month" x="${layout.chipSiteGenValueX}" y="420" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="442">YTD</text>
          <text class="site-gen-value" data-site-gen="gen-ytd" x="${layout.chipSiteGenValueX}" y="442" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="464">Year</text>
          <text class="site-gen-value" data-site-gen="gen-year" x="${layout.chipSiteGenValueX}" y="464" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="486">All time</text>
          <text class="site-gen-value" data-site-gen="gen-alltime" x="${layout.chipSiteGenValueX}" y="486" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="510">Site Capacity Factor (%)</text>
          <text class="site-gen-value" data-site-gen="capacity" x="${layout.chipSiteGenValueX}" y="510" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="532">Site Power (MW)</text>
          <text class="site-gen-value" data-site-gen="power" x="${layout.chipSiteGenValueX}" y="532" text-anchor="end">—</text>
        </g>
      </g>
    `;
  }

  _buildLegend(layout) {
    const entries = Object.entries(KirkHillWindScada.STATUS)
      .map(([key, v]) => `<span class="lg-item"><span class="lg-dot" style="background:${v.color}"></span>${v.label}</span>`)
      .join("");
    return `<foreignObject x="${layout.legendX}" y="${layout.legendY}" width="${layout.legendW}" height="120">
      <div xmlns="http://www.w3.org/1999/xhtml" class="legend">${entries}</div>
    </foreignObject>`;
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
    this._setText(root, '[data-chip="active"]', active === null ? "—" : `${this._fmt(active, 0)} of ${config.turbines.length}`);
    const forecast = this._num(config.wind_forecast_entity);
    this._setText(root, '[data-chip="forecast"]', forecast === null ? "—" : `${this._fmt(forecast)} m/s`);

    // Generation & capacity panel (top right) — timeframe values
    (config.owner_generation_entities || []).forEach((item) => {
      const key = `gen-${item.name.toLowerCase().replace(/\s/g, "-")}`;
      const val = this._num(item.entity);
      const scaled = val !== null ? this._scaleKwh(val) : { value: "—", unit: "" };
      this._setText(root, `[data-user-gen="${key}"]`, scaled.value === "—" ? scaled.value : `${scaled.value} ${scaled.unit}`);
    });

    const siteCap = this._num(config.capacity_entity);
    // Your share: owner export power is reported in kW; display in watts.
    this._setText(root, '[data-user-gen="share"]', ownerExportKw === null ? "—" : `${this._fmt(ownerExportKw * 1000, 0)} W`);
    // Your share as a % of the site's generation today (observed).
    const sharePct =
      ownerEnergyKwh !== null && siteEnergyKwh !== null && siteEnergyKwh > 0
        ? (ownerEnergyKwh / siteEnergyKwh) * 100
        : null;
    this._setText(root, '[data-user-gen="sharepct"]', sharePct === null ? "—" : `${this._fmt(sharePct * 100, 2)}‱`);

    // Site Generation & Capacity panel — timeframe values
    (config.site_generation_entities || []).forEach((item) => {
      const key = `gen-${item.name.toLowerCase().replace(/\s/g, "-")}`;
      const val = this._num(item.entity);
      const scaled = val !== null ? this._scaleKwh(val) : { value: "—", unit: "" };
      this._setText(root, `[data-site-gen="${key}"]`, scaled.value === "—" ? scaled.value : `${scaled.value} ${scaled.unit}`);
    });

    this._setText(root, '[data-site-gen="capacity"]', siteCap === null ? "—" : `${this._fmt(siteCap, 1)}%`);
    sitePowerText = sitePowerMw === null ? { value: "—", unit: "" } : { value: this._fmt(sitePowerMw, 2), unit: "MW" };
    this._setText(root, '[data-site-gen="power"]', `${sitePowerText.value} ${sitePowerText.unit}`);

    // Alarm indicator (always visible: OK or flashing N FAULTS)
    const alarmIndicator = root.querySelector('[data-alarm="indicator"]');
    if (alarmIndicator) {
      const faultCount = config.turbines.reduce((count, t) => {
        const category = this._attr(t.state_entity, "status_category");
        return count + (category === "fault_thermal" || category === "fault_electrical" ? 1 : 0);
      }, 0);
      const inFault = faultCount > 0;
      alarmIndicator.classList.toggle("fault", inFault);
      this._setText(
        root,
        '[data-alarm="text"]',
        inFault ? `${faultCount} FAULT${faultCount === 1 ? "" : "S"}` : "OK"
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
      this._setText(node, ".t-last", `Last status ${last}`);
      const pill = node.querySelector(".status-pill");
      if (pill) {
        pill.setAttribute("class", "status-pill " + status.class);
        pill.removeAttribute("fill");
      }
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
        --khscada-alarm-fault-bg: color-mix(in srgb, var(--error-color, #ef5350) 10%, transparent);
        --khscada-divider: var(--divider-color, var(--ha-divider-color, #cbd5e1));
      }
      ha-card { overflow: hidden; height: calc(100vh - 64px); box-sizing: border-box; background: transparent; }
      .shell { padding: 12px; background: var(--khscada-card-bg); border-radius: 12px; height: 100%; box-sizing: border-box; }
      svg { width: 100%; height: 100%; display: block; touch-action: none; user-select: none; -webkit-user-select: none; }
      .bg { fill: var(--khscada-card-bg); }
      text { font-family: var(--khscada-font-family); fill: var(--khscada-primary-color); }

      /* Lines */
      .feed-line { stroke: var(--khscada-accent-color); stroke-opacity: 0.35; stroke-width: 3; }
      .flow-dot { fill: var(--khscada-accent-color); }

      /* Turbine nodes */
      .node-rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .node-rect[data-status] { opacity: 1; }
      .turbine:hover .node-rect { stroke: var(--khscada-accent-color); }
      .t-id { font: 600 var(--ha-font-size-xxlarge, 20px) var(--khscada-font-family); }
      .status-pill { fill: var(--khscada-success-color); }
      .status-pill.status-running { fill: var(--khscada-success-color); }
      .status-pill.status-ready { fill: var(--khscada-accent-color); }
      .status-pill.status-starting { fill: var(--khscada-warn-color); }
      .status-pill.status-curtailed { fill: var(--khscada-warn-color); }
      .status-pill.status-no-wind { fill: var(--khscada-accent-color); }
      .status-pill.status-stopped { fill: var(--khscada-disabled-color); }
      .status-pill.status-fault { fill: var(--khscada-error-color); }
      .status-pill.status-maintenance { fill: var(--khscada-accent-color); }
      .status-pill.status-unavailable { fill: var(--khscada-disabled-color); }
      .status-pill.status-unknown { fill: var(--khscada-disabled-color); }
      .t-status { fill: var(--khscada-primary-color); font: 600 var(--ha-font-size-small, 12px) var(--khscada-font-family); text-anchor: middle; }
      .t-power { font: 600 var(--ha-font-size-xxxlarge, 24px) var(--khscada-font-family); }
      .t-op { font: 600 var(--ha-font-size, 14px) var(--khscada-font-family); }
      .t-wind { fill: var(--khscada-secondary-color); font: var(--ha-font-size, 14px) var(--khscada-font-family); }
      .t-detail { fill: var(--khscada-secondary-color); font: var(--ha-font-size, 14px) var(--khscada-font-family); }
      .t-last { fill: var(--khscada-disabled-color); font: var(--ha-font-size-small, 12px) var(--khscada-font-family); }

      /* Bus */
      .bus rect { fill: var(--khscada-bus-bg); stroke: var(--khscada-accent-color); stroke-width: 2; }

      /* Transformer label (overlaid down the site collection bus) */
      .xfmr-title { font: 600 var(--ha-font-size-xlarge, 18px) var(--khscada-font-family); }

      /* Grid node */
      .grid-rect { fill: var(--khscada-grid-bg); stroke: var(--khscada-success-color); stroke-width: 2; }
      .grid-title { fill: var(--khscada-success-color); font: 600 var(--ha-font-size-xxlarge, 20px) var(--khscada-font-family); }
      .grid-label { fill: var(--khscada-secondary-color); font: var(--ha-font-size-large, 16px) var(--khscada-font-family); }
      .grid-power { font: 600 var(--ha-font-size-xxlarge, 20px) var(--khscada-font-family); }
      .grid-energy { font: 600 var(--ha-font-size-xxlarge, 20px) var(--khscada-font-family); }
      .grid-unit { fill: var(--khscada-disabled-color); font: var(--ha-font-size-large, 16px) var(--khscada-font-family); }
      .grid-divider { stroke: var(--khscada-success-color); stroke-width: 2; }

      /* Chips */
      .chips rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .chip-label { fill: var(--khscada-secondary-color); font: var(--ha-font-size-small, 12px) var(--khscada-font-family); }
      .chip-value { font: 600 var(--ha-font-size, 14px) var(--khscada-font-family); }

      /* Generation & capacity panel (top right) */
      .user-gen rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .user-gen-title { font: 600 var(--ha-font-size-xxlarge, 20px) var(--khscada-font-family); }
      .user-gen-label { fill: var(--khscada-secondary-color); font: var(--ha-font-size, 14px) var(--khscada-font-family); }
      .user-gen-value { font: 600 var(--ha-font-size-xxxlarge, 24px) var(--khscada-font-family); }
      .user-gen-share { fill: var(--khscada-success-color); font: 600 var(--ha-font-size-xxxlarge, 24px) var(--khscada-font-family); }

      /* Site Generation & Capacity panel (below Owner) */
      .site-gen rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .site-gen-title { font: 600 var(--ha-font-size-xxlarge, 20px) var(--khscada-font-family); }
      .site-gen-label { fill: var(--khscada-secondary-color); font: var(--ha-font-size, 14px) var(--khscada-font-family); }
      .site-gen-value { font: 600 var(--ha-font-size-xxxlarge, 24px) var(--khscada-font-family); }

      /* Wind & forecast panel (below Site Generation) */
      .wind-panel rect { fill: var(--khscada-card-bg); stroke: var(--khscada-divider); stroke-width: 1.5; }
      .wind-title { font: 600 var(--ha-font-size-xxlarge, 20px) var(--khscada-font-family); }
      .wind-label { fill: var(--khscada-secondary-color); font: var(--ha-font-size, 14px) var(--khscada-font-family); }
      .wind-value { font: 600 var(--ha-font-size-xxxlarge, 24px) var(--khscada-font-family); }

      /* Alarm indicator */
      .alarm rect { fill: var(--khscada-alarm-ok-bg); stroke: var(--khscada-success-color); stroke-width: 2; }
      .alarm-text { fill: var(--khscada-success-color); font: 600 var(--ha-font-size, 14px) var(--khscada-font-family); }
      .alarm.fault rect { fill: var(--khscada-alarm-fault-bg); stroke: var(--khscada-error-color); stroke-width: 2; }
      .alarm.fault .alarm-text { fill: var(--khscada-error-color); }
      .alarm.fault { animation: khscada-alarm-flash 1s steps(1, end) infinite; }
      @keyframes khscada-alarm-flash {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.15; }
      }

      /* Legend */
      .legend { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; align-content: center; height: 100%; width: 100%; }
      .lg-item { color: var(--khscada-secondary-color); font: var(--ha-font-size-small, 12px) var(--khscada-font-family); }
      .lg-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

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
      .turbine-detail-modal .chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 16px; }
      .turbine-detail-modal .chart-item { background: var(--khscada-card-bg); border: 1px solid var(--khscada-divider); border-radius: 8px; padding: 12px; }
      .turbine-detail-modal .chart-item.large { grid-column: span 2; }
      .turbine-detail-modal .chart-item h3 { margin: 0 0 10px; font: 600 var(--ha-font-size, 14px) var(--khscada-font-family); color: var(--khscada-primary-color); }
      .turbine-detail-modal .apex-chart { width: 100%; height: 100%; min-height: 280px; }
      @media (max-width: 900px) {
        .turbine-detail-modal .chart-item.large { grid-column: span 1; }
        .turbine-detail-modal .chart-grid { grid-template-columns: 1fr; }
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
