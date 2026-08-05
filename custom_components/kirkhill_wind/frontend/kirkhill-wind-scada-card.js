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
            ${linesHtml}
            ${dotsHtml}
            ${turbinesHtml}
            ${this._buildBus(layout)}
            ${this._buildTransformer(layout)}
            ${this._buildGrid(layout)}
            ${this._buildHeaderChips()}
            ${this._buildLegend(layout)}
          </svg>
        </div>
      </ha-card>
    `;
    this._update();
  }

  _layout() {
    const H = this._vbH;
    const tTop = 74;
    const legendY = H - 150;
    const tBottom = legendY - 60;
    const span = Math.max(320, tBottom - tTop);
    const gap = Math.max(96, span / 8);
    return {
      H,
      gap,
      tTop,
      busY2: tBottom,
      busSummaryY: legendY - 24,
      legendY,
      mid: Math.round(H / 2),
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
        <rect class="bus-summary" x="530" y="${layout.busSummaryY}" width="200" height="30" rx="6"/>
        <text class="bus-total" x="630" y="${layout.busSummaryY + 20}" text-anchor="middle"></text>
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
    return `
      <g class="grid">
        <rect class="grid-rect" x="1110" y="${cy - 180}" width="120" height="360" rx="10"/>
        <text class="grid-title" x="1170" y="${cy - 144}" text-anchor="middle">NATIONAL</text>
        <text class="grid-title" x="1170" y="${cy - 122}" text-anchor="middle">GRID</text>
        <g class="grid-icon">
          <path d="M1162 ${cy - 100} h16 M1170 ${cy - 108} v16" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        </g>
        <text class="grid-label" x="1170" y="${cy - 60}" text-anchor="middle">Export</text>
        <text class="grid-power" x="1170" y="${cy - 28}" text-anchor="middle">—</text>
        <text class="grid-unit" x="1170" y="${cy - 10}" text-anchor="middle">MW</text>
        <line x1="1130" y1="${cy + 15}" x2="1210" y2="${cy + 15}" class="grid-divider"/>
        <text class="grid-label" x="1170" y="${cy + 42}" text-anchor="middle">To grid today</text>
        <text class="grid-energy" x="1170" y="${cy + 70}" text-anchor="middle">—</text>
        <text class="grid-unit" x="1170" y="${cy + 88}" text-anchor="middle">kWh</text>
      </g>
    `;
  }

  _buildHeaderChips() {
    return `
      <g class="chips">
        <rect x="700" y="60" width="160" height="30" rx="15"/>
        <text class="chip-label" x="712" y="80">Wind</text>
        <text class="chip-value" data-chip="wind" x="852" y="80" text-anchor="end">—</text>
        <rect x="700" y="100" width="160" height="30" rx="15"/>
        <text class="chip-label" x="712" y="120">Active</text>
        <text class="chip-value" data-chip="active" x="852" y="120" text-anchor="end">—</text>
      </g>
    `;
  }

  _buildLegend(layout) {
    const entries = Object.entries(KirkHillWindScada.STATUS)
      .map(([key, v]) => `<span class="lg-item"><span class="lg-dot" style="background:${v.color}"></span>${v.label}</span>`)
      .join("");
    return `<foreignObject x="700" y="${layout.legendY}" width="480" height="120">
      <div xmlns="http://www.w3.org/1999/xhtml" class="legend">${entries}</div>
    </foreignObject>`;
  }

  // ---- live update ------------------------------------------------------

  _update() {
    if (!this.config || !this.shadowRoot) return;
    const root = this.shadowRoot;
    const config = this.config;

    // Farm / grid values
    const gridPowerMw = this._num(config.farm_power_entity);
    const gridEnergyKwh = this._num(config.grid_energy_entity);
    this._setText(root, ".grid-power", gridPowerMw === null ? "—" : this._fmt(gridPowerMw));
    const scaled = this._scaleKwh(gridEnergyKwh);
    this._setText(root, ".grid-energy", scaled.value);

    // Header chips
    const wind = this._num(config.wind_speed_entity);
    this._setText(root, '[data-chip="wind"]', wind === null ? "—" : `${this._fmt(wind)} m/s`);
    const active = this._num(config.active_entity);
    this._setText(root, '[data-chip="active"]', active === null ? "—" : `${this._fmt(active, 0)} of ${config.turbines.length}`);

    // Bus total
    const totalKw = config.turbines.reduce((sum, t) => {
      const p = this._num(t.power_entity);
      return sum + (Number.isFinite(p) ? p : 0);
    }, 0);
    this._setText(root, ".bus-total", totalKw > 0 ? `Σ ${this._fmt(totalKw)} kW` : "Σ — kW");

    // Turbines
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
      :host { display: block; width: 100%; height: 100%; }
      ha-card { overflow: hidden; height: calc(100vh - 64px); box-sizing: border-box; }
      .shell { padding: 12px; background: #0b1120; border-radius: 12px; height: 100%; box-sizing: border-box; }
      svg { width: 100%; height: 100%; display: block; }
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
      .bus rect:not(.bus-summary) { fill: #0f2742; stroke: #1d4ed8; stroke-width: 2; }
      .bus-title { fill: #60a5fa; font: bold 11px sans-serif; }
      .bus-summary { fill: #111a2e; stroke: #1e293b; }
      .bus-total { fill: #fbbf24; font: bold 14px sans-serif; }

      /* Transformer */
      .transformer rect { fill: #111a2e; stroke: #1e293b; stroke-width: 1.5; }
      .transformer circle { fill: #334155; stroke: #64748b; stroke-width: 1.5; }
      .xfmr-title { fill: #e2e8f0; font: bold 12px sans-serif; }
      .xfmr-sub { fill: #94a3b8; font: 10px sans-serif; }

      /* Grid node */
      .grid-rect { fill: #1a2e05; stroke: #4d7c0f; stroke-width: 2; }
      .grid-title { fill: #a3e635; font: bold 16px sans-serif; }
      .grid-icon { color: #a3e635; }
      .grid-label { fill: #94a3b8; font: 11px sans-serif; }
      .grid-power { fill: #f8fafc; font: bold 34px sans-serif; }
      .grid-energy { fill: #f8fafc; font: bold 26px sans-serif; }
      .grid-unit { fill: #64748b; font: 11px sans-serif; }
      .grid-divider { stroke: #365314; stroke-width: 2; }

      /* Chips */
      .chips rect { fill: #111a2e; stroke: #1e293b; stroke-width: 1.5; }
      .chip-label { fill: #94a3b8; font: 11px sans-serif; }
      .chip-value { fill: #f8fafc; font: bold 12px sans-serif; }

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
