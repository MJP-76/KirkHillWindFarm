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
    return { w: 1240, h: 860, hMin: 1052, hMax: 1600 };
  }

  static get MAX_ZOOM() {
    return 6;
  }

  static get TAP_MOVE_PX() {
    return 8;
  }

  static get DOUBLE_TAP_MS() {
    return 300;
  }

  static get STATUS() {
    return {
      running: { label: "RUNNING", color: "#22c55e" },
      ready: { label: "READY", color: "#84cc16" },
      starting: { label: "STARTING", color: "#f59e0b" },
      curtailed: { label: "CURTAILED", color: "#f97316" },
      no_wind: { label: "NO WIND", color: "#38bdf8" },
      stopped: { label: "STOPPED", color: "#94a3b8" },
      fault_thermal: { label: "THERMAL FAULT", color: "#ef4444" },
      fault_electrical: { label: "ELEC FAULT", color: "#dc2626" },
      maintenance: { label: "MAINTENANCE", color: "#a855f7" },
      unavailable: { label: "UNAVAILABLE", color: "#64748b" },
      unknown: { label: "UNKNOWN", color: "#94a3b8" },
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._values = new Map();
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

  _dotDur(powerKw) {
    const p = powerKw ?? 0;
    if (p < 1) return null; // no flow
    const t = Math.max(2.5, Math.min(26, 26 - (p / 2400) * 22));
    return `${t.toFixed(1)}s`;
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
          <svg viewBox="0 0 ${vb.w} ${layout.H}" role="img" aria-label="Wind farm SCADA diagram">
            <defs>
              <pattern id="khscada-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(148,163,184,0.08)" stroke-width="1"/>
              </pattern>
              <marker id="khscada-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                      markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>
              </marker>
            </defs>
            <rect class="bg" x="0" y="0" width="${vb.w}" height="${layout.H}" fill="url(#khscada-grid)"/>
            <g data-zoom="wrap" transform="translate(0 0) scale(1)">
              ${linesHtml}
              ${dotsHtml}
              ${turbinesHtml}
              ${this._buildBus(layout)}
              ${this._buildTransformer(layout)}
              ${this._buildGrid(layout)}
              ${this._buildHeaderChips()}
              ${this._buildLegend(layout)}
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
      const g = ev.target.closest("g.turbine");
      if (!g) return;
      this._openTurbine(g);
    };
    svg.addEventListener("click", this._boundClick);
  }

  _openTurbine(g) {
    const key = g.getAttribute("data-turbine");
    const entityId = key ? this._turbineEntities.get(key) : null;
    if (!entityId) return;
    try {
      window.dispatchEvent(
        new CustomEvent("hass-more-info", {
          bubbles: true,
          composed: true,
          detail: { entityId },
        })
      );
    } catch (err) {
      console.error("SCADA: failed to open more-info", err);
    }
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

  _layout() {
    const H = this._vbH;
    const mid = Math.round(H / 2);
    const tCount = this.config.turbines.length;
    const legendY = H - 150;
    const tBottom = legendY - 60;

    // Vertically centre the turbine stack around the mid-line so the whole
    // flow path (turbines -> bus -> transformer -> grid) reads as one
    // centred single-line diagram on any window size.
    const bandTop = 72;
    const band = Math.max(160, tBottom - bandTop);
    const nodeH = 80;
    const minRow = 82;
    let gap = (band - nodeH) / Math.max(1, tCount - 1);
    if (gap < minRow) gap = minRow;
    const blockH = (tCount - 1) * gap + nodeH;
    const tTop = bandTop + (band - blockH) / 2;

    return {
      H,
      gap,
      tTop,
      mid,
      busY2: tBottom,
      busSummaryY: legendY - 24,
      legendY,
    };
  }

  _fit() {
    if (!this.config || !this.shadowRoot) return;
    const shell = this.shadowRoot.querySelector(".shell");
    if (!shell) return;
    const r = shell.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const vb = KirkHillWindScada.VIEWBOX;
    let h = Math.round(vb.w / (r.width / r.height));
    h = Math.max(vb.hMin, Math.min(vb.hMax, h));
    if (h === this._vbH) return;
    this._vbH = h;
    this._render();
  }

  _buildStatic(layout) {
    const turbines = this.config.turbines;
    let turbinesHtml = "";
    let linesHtml = "";
    let dotsHtml = "";

    turbines.forEach((t, i) => {
      const cx = 260;
      const top = layout.tTop + i * layout.gap;
      const cy = top + 40;
      const num = this._escape(t.id || `T${i + 1}`);
      const stateEntity = t.state_entity;
      if (stateEntity) this._turbineEntities.set(t.id || `T${i + 1}`, stateEntity);
      turbinesHtml += `
        <g class="turbine" data-turbine="${this._escape(t.id || `T${i + 1}`)}">
          <rect class="node-rect" x="30" y="${top}" width="230" height="80" rx="8"/>
          <text class="t-id" x="44" y="${top + 16}">${num}</text>
          <rect class="status-pill" x="150" y="${top + 7}" width="96" height="20" rx="10"/>
          <text class="t-status" x="198" y="${top + 21}"></text>
          <text class="t-power" x="44" y="${top + 50}">—</text>
          <text class="t-detail" x="44" y="${top + 67}"></text>
          <text class="t-last" x="44" y="${top + 77}"></text>
        </g>
      `;
      linesHtml += `<line class="feed-line" x1="${cx}" y1="${cy}" x2="600" y2="${cy}"/>`;
      dotsHtml += `
        <circle class="flow-dot" data-flow="t${i}" r="5">
          <animateMotion dur="10s" repeatCount="indefinite"
            path="M ${cx} ${cy} L 600 ${cy}"/>
        </circle>
      `;
    });

    return { turbinesHtml, linesHtml, dotsHtml };
  }

  _buildBus(layout) {
    return `
      <g class="bus">
        <rect x="600" y="30" width="60" height="${layout.busY2 - 30}" rx="6"/>
        <text class="bus-title" x="630" y="20" text-anchor="middle">SITE COLLECTION BUS</text>
      </g>
    `;
  }

  _buildTransformer(layout) {
    const cy = layout.mid;
    return `
      <g class="transformer">
        <line class="feed-line" x1="660" y1="${cy}" x2="830" y2="${cy}" marker-end="url(#khscada-arrow)"/>
        <rect x="830" y="${cy - 70}" width="130" height="140" rx="8"/>
        <text class="xfmr-title" x="895" y="${cy - 54}" text-anchor="middle">TRANSFORMER</text>
        <circle cx="895" cy="${cy - 25}" r="9"/>
        <circle cx="872" cy="${cy - 5}" r="9"/>
        <circle cx="918" cy="${cy - 5}" r="9"/>
        <text class="xfmr-sub" x="895" y="${cy + 32}" text-anchor="middle">33 kV → 132 kV</text>
        <circle class="flow-dot" data-flow="grid" r="5">
          <animateMotion dur="10s" repeatCount="indefinite"
            path="M 660 ${cy} L 830 ${cy} L 960 ${cy} L 1110 ${cy}"/>
        </circle>
        <line class="feed-line" x1="960" y1="${cy}" x2="1110" y2="${cy}" marker-end="url(#khscada-arrow)"/>
      </g>
    `;
  }

  _buildGrid(layout) {
    const cy = layout.mid;
    const ownerCx = 1010;
    const siteCx = 1210;
    return `
      <g class="grid">
        <rect class="grid-rect" x="985" y="${cy - 125}" width="250" height="250" rx="10"/>
        <text class="grid-title" x="1110" y="${cy - 102}" text-anchor="middle">NATIONAL</text>
        <text class="grid-title" x="1110" y="${cy - 80}" text-anchor="middle">GRID</text>
        <text class="grid-col" x="${ownerCx}" y="${cy - 52}" text-anchor="middle">OWNER</text>
        <text class="grid-col" x="${siteCx}" y="${cy - 52}" text-anchor="middle">SITE</text>
        <line class="grid-divider" x1="1000" y1="${cy - 38}" x2="1220" y2="${cy - 38}"/>
        <text class="grid-label" x="1110" y="${cy - 20}" text-anchor="middle">Export (MW)</text>
        <text class="grid-power" data-grid="owner-power" x="${ownerCx}" y="${cy + 8}" text-anchor="middle">—</text>
        <text class="grid-power" data-grid="site-power" x="${siteCx}" y="${cy + 8}" text-anchor="middle">—</text>
        <line class="grid-divider" x1="1000" y1="${cy + 26}" x2="1220" y2="${cy + 26}"/>
        <text class="grid-label" x="1110" y="${cy + 44}" text-anchor="middle">To grid today</text>
        <text class="grid-energy" data-grid="owner-energy" x="${ownerCx}" y="${cy + 72}" text-anchor="middle">—</text>
        <text class="grid-energy" data-grid="site-energy" x="${siteCx}" y="${cy + 72}" text-anchor="middle">—</text>
        <text class="grid-unit" data-grid="owner-energy-unit" x="${ownerCx}" y="${cy + 90}" text-anchor="middle">kWh</text>
        <text class="grid-unit" data-grid="site-energy-unit" x="${siteCx}" y="${cy + 90}" text-anchor="middle">kWh</text>
      </g>
    `;
  }

  _buildHeaderChips() {
    return `
      <g class="chips">
        <!-- Left side: Alarm + Active Turbines (above turbine list) -->
        <g class="alarm" data-alarm="indicator">
          <rect x="30" y="24" width="112" height="30" rx="15"/>
          <text class="alarm-text" data-alarm="text" x="86" y="44" text-anchor="middle">OK</text>
        </g>
        <rect x="152" y="24" width="170" height="30" rx="15"/>
        <text class="chip-label" x="164" y="44">Active Turbines</text>
        <text class="chip-value" data-chip="active" x="310" y="44" text-anchor="end">—</text>

        <!-- Right side: Current Wind, Forecast 1h, Site Capacity -->
        <rect x="700" y="60" width="160" height="30" rx="15"/>
        <text class="chip-label" x="712" y="80">Current Wind</text>
        <text class="chip-value" data-chip="wind" x="852" y="80" text-anchor="end">—</text>
        <rect x="700" y="100" width="160" height="30" rx="15"/>
        <text class="chip-label" x="712" y="120">Forecast 1h</text>
        <text class="chip-value" data-chip="forecast" x="852" y="120" text-anchor="end">—</text>
        <rect x="700" y="140" width="160" height="30" rx="15"/>
        <text class="chip-label" x="712" y="160">Site Capacity</text>
        <text class="chip-value" data-chip="capacity" x="852" y="160" text-anchor="end">—</text>

        <!-- Right side: Your Generation (far right) -->
        <g class="user-gen" data-user-gen="panel">
          <rect x="870" y="24" width="330" height="86" rx="8"/>
          <text class="user-gen-title" x="882" y="42">Your generation</text>
          <text class="user-gen-value" data-user-gen="energy" x="882" y="62">—</text>
          <text class="user-gen-time" data-user-gen="time" x="882" y="80">Last updated: —</text>
          <text class="user-gen-share" data-user-gen="share" x="882" y="100">Your share: —</text>
        </g>
      </g>
    `;
  }

  _buildLegend(layout) {
    const entries = Object.entries(KirkHillWindScada.STATUS)
      .map(([key, v]) => `<span class="lg-item"><span class="lg-dot" style="background:${v.color}"></span>${v.label}</span>`)
      .join("");
    return `<foreignObject x="30" y="${layout.legendY}" width="500" height="120">
      <div xmlns="http://www.w3.org/1999/xhtml" class="legend">${entries}</div>
    </foreignObject>`;
  }

  // ---- live update ------------------------------------------------------

  _update() {
    if (!this.config || !this.shadowRoot) return;
    const root = this.shadowRoot;
    const config = this.config;

    // National grid: owner & site export (MW) and to-grid-today
    const ownerPowerKw = this._num(config.owner_power_entity);
    const sitePowerMw = this._num(config.farm_power_entity);
    this._setText(root, '[data-grid="owner-power"]', ownerPowerKw === null ? "—" : this._fmt(ownerPowerKw / 1000, 2));
    this._setText(root, '[data-grid="site-power"]', sitePowerMw === null ? "—" : this._fmt(sitePowerMw, 2));
    const ownerEnergy = this._scaleKwh(this._num(config.owner_grid_energy_entity));
    const siteEnergy = this._scaleKwh(this._num(config.grid_energy_entity));
    this._setText(root, '[data-grid="owner-energy"]', ownerEnergy.value);
    this._setText(root, '[data-grid="site-energy"]', siteEnergy.value);
    this._setText(root, '[data-grid="owner-energy-unit"]', ownerEnergy.unit);
    this._setText(root, '[data-grid="site-energy-unit"]', siteEnergy.unit);

    // Header chips
    const wind = this._num(config.wind_speed_entity);
    this._setText(root, '[data-chip="wind"]', wind === null ? "—" : `${this._fmt(wind)} m/s`);
    const active = this._num(config.active_entity);
    this._setText(root, '[data-chip="active"]', active === null ? "—" : `${this._fmt(active, 0)} of ${config.turbines.length}`);
    const forecast = this._num(config.wind_forecast_entity);
    this._setText(root, '[data-chip="forecast"]', forecast === null ? "—" : `${this._fmt(forecast)} m/s`);
    const capacity = this._num(config.capacity_entity);
    this._setText(root, '[data-chip="capacity"]', capacity === null ? "—" : `${this._fmt(capacity, 0)}%`);

    // Your generation panel (top right)
    const ownerGenToday = this._num(config.owner_generation_today_entity);
    if (ownerGenToday !== null) {
      const scaled = this._scaleKwh(ownerGenToday);
      this._setText(root, '[data-user-gen="energy"]', `${scaled.value} ${scaled.unit}`);
    } else {
      this._setText(root, '[data-user-gen="energy"]', "—");
    }
    const lastUpdated = this._attr(config.owner_generation_today_entity, "last_updated") ||
                         this._attr(config.owner_generation_today_entity, "last_changed");
    if (lastUpdated) {
      this._setText(root, '[data-user-gen="time"]', `Last updated: ${this._fmtTime(lastUpdated)}`);
    } else {
      this._setText(root, '[data-user-gen="time"]', "Last updated: —");
    }
    // Owner export power is reported in kW; display the share in watts.
    const ownerPower = this._num(config.owner_power_entity);
    if (ownerPower !== null) {
      this._setText(root, '[data-user-gen="share"]', `Your share: ${this._fmt(ownerPower * 1000, 0)} W`);
    } else {
      this._setText(root, '[data-user-gen="share"]', "Your share: —");
    }

    // Alarm indicator (always visible: OK or flashing ALARM)
    const alarmIndicator = root.querySelector('[data-alarm="indicator"]');
    if (alarmIndicator) {
      const alarmOn = this._str(config.alarm_entity) === "on";
      alarmIndicator.classList.toggle("fault", alarmOn);
      this._setText(root, '[data-alarm="text"]', alarmOn ? "⚠ ALARM" : "OK");
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
      const last = this._fmtTime(this._attr(t.state_entity, "status_started_at"));

      this._setText(node, ".t-power", power === null ? "—" : `${this._fmt(power, 0)} kW`);
      this._setText(node, ".t-status", status.label);
      this._setText(node, ".t-detail", `Today ${today.value} ${today.unit}${rotor !== null ? ` · ${this._fmt(rotor, 1)} rpm` : ""}`);
      this._setText(node, ".t-last", `Last status ${last}`);
      const pill = node.querySelector(".status-pill");
      if (pill) pill.setAttribute("fill", status.color);
      node.querySelectorAll(".node-rect").forEach((r) => r.setAttribute("data-status", status.label));

      // Flow dot speed
      const dot = root.querySelector(`[data-flow="t${i}"]`);
      if (dot) {
        const dur = this._dotDur(power);
        dot.setAttribute("opacity", dur ? "1" : "0");
        const motion = dot.querySelector("animateMotion");
        if (motion && dur) motion.setAttribute("dur", dur);
      }
    });

    // Bus → grid flow dot
    const busDot = root.querySelector('[data-flow="grid"]');
    if (busDot) {
      const dur = this._dotDur(totalKw);
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
      :host { display: block; width: 100%; height: 100%; -webkit-tap-highlight-color: transparent; }
      ha-card { overflow: hidden; height: calc(100vh - 64px); box-sizing: border-box; }
      .shell { padding: 12px; background: #0b1120; border-radius: 12px; height: 100%; box-sizing: border-box; }
      svg { width: 100%; height: 100%; display: block; touch-action: none; user-select: none; -webkit-user-select: none; }
      .bg { fill: #0b1120; }

      /* Lines */
      .feed-line { stroke: rgba(56,189,248,0.25); stroke-width: 3; }
      .flow-dot { fill: #38bdf8; }

      /* Turbine nodes */
      .node-rect { fill: #111a2e; stroke: #1e293b; stroke-width: 1.5; }
      .node-rect[data-status] { opacity: 1; }
      .turbine:hover .node-rect { stroke: #38bdf8; }
      .t-id { fill: #e2e8f0; font: bold 17px sans-serif; }
      .status-pill { fill: #22c55e; }
      .t-status { fill: #06121f; font: bold 10px sans-serif; text-anchor: middle; }
      .t-power { fill: #f8fafc; font: bold 23px sans-serif; }
      .t-detail { fill: #94a3b8; font: 11px sans-serif; }
      .t-last { fill: #64748b; font: 10px sans-serif; }

      /* Bus */
      .bus rect { fill: #0f2742; stroke: #1d4ed8; stroke-width: 2; }
      .bus-title { fill: #60a5fa; font: bold 11px sans-serif; }

      /* Transformer */
      .transformer rect { fill: #111a2e; stroke: #1e293b; stroke-width: 1.5; }
      .transformer circle { fill: #334155; stroke: #64748b; stroke-width: 1.5; }
      .xfmr-title { fill: #e2e8f0; font: bold 12px sans-serif; }
      .xfmr-sub { fill: #94a3b8; font: 10px sans-serif; }

      /* Grid node */
      .grid-rect { fill: #1a2e05; stroke: #4d7c0f; stroke-width: 2; }
      .grid-title { fill: #a3e635; font: bold 16px sans-serif; }
      .grid-col { fill: #a3e635; font: bold 11px sans-serif; }
      .grid-label { fill: #94a3b8; font: 11px sans-serif; }
      .grid-power { fill: #f8fafc; font: bold 22px sans-serif; }
      .grid-energy { fill: #f8fafc; font: bold 20px sans-serif; }
      .grid-unit { fill: #64748b; font: 11px sans-serif; }
      .grid-divider { stroke: #365314; stroke-width: 2; }

      /* Chips */
      .chips rect { fill: #111a2e; stroke: #1e293b; stroke-width: 1.5; }
      .chip-label { fill: #94a3b8; font: 11px sans-serif; }
      .chip-value { fill: #f8fafc; font: bold 12px sans-serif; }

      /* User generation panel (top right) */
      .user-gen rect { fill: #111a2e; stroke: #1e293b; stroke-width: 1.5; }
      .user-gen-title { fill: #94a3b8; font: bold 11px sans-serif; }
      .user-gen-value { fill: #f8fafc; font: bold 18px sans-serif; }
      .user-gen-time { fill: #64748b; font: 10px sans-serif; }
      .user-gen-share { fill: #22c55e; font: bold 12px sans-serif; }

      /* Alarm indicator (always visible: OK = green, ALARM = flashing red) */
      .alarm rect { fill: #052e16; stroke: #22c55e; stroke-width: 2; }
      .alarm-text { fill: #4ade80; font: bold 12px sans-serif; }
      .alarm.fault rect { fill: #450a0a; stroke: #ef4444; stroke-width: 2; }
      .alarm.fault .alarm-text { fill: #fca5a5; }
      .alarm.fault { animation: khscada-alarm-flash 1s steps(1, end) infinite; }
      @keyframes khscada-alarm-flash {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.15; }
      }

      /* Legend */
      .legend { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; }
      .lg-item { display: inline-flex; align-items: center; gap: 5px; color: #94a3b8; font: 10px sans-serif; }
      .lg-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

      .empty { padding: 24px 16px; color: var(--secondary-text-color); }
    `;
  }
}

// Bus → grid flow dot is defined inside _buildTransformer().
if (!customElements.get("kirkhill-wind-scada")) {
  customElements.define("kirkhill-wind-scada", KirkHillWindScada);
}
