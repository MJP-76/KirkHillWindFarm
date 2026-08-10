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
    // Base duration at a 250-unit reference line, falling as power rises:
    // more energy produced = faster dot.
    const base = Math.max(2.5, Math.min(26, 26 - (p / 2400) * 22));
    // Scale by actual line length so every dot moves at the same speed for a
    // given power level, whatever the turbine's distance from the bus.
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
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#0284c7"/>
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
    const bh = Math.max(
      92,
      Math.min(120, Math.floor((gridY - tTop - 30) / Math.max(1, tCount)))
    );
    const pitch = bh;

    // Scale horizontal positions from design width (1240) to current viewBox width
    const busX = 600 * scaleX;
    const leftColX = 30 * scaleX;
    const rightColX = 290 * scaleX;
    const boxW = 190 * scaleX;
    const feedEndX = busX;
    const gridRectX = 975 * scaleX;
    const transformerLineEndX = gridRectX;
    const transformerLineEndY = gridY - 135;
    const gridRectW = 265 * scaleX;
    const ownerCx = 1015 * scaleX;
    const siteCx = 1205 * scaleX;
    const gridTitleX = 1110 * scaleX;
    const gridDividerX1 = 985 * scaleX;
    const gridDividerX2 = 1230 * scaleX;
    const chipLeftColX = 30 * scaleX;
    const chipRightColX = 152 * scaleX;
    const chipActiveX = 284 * scaleX;
    const chipUserGenX = 870 * scaleX;
    const chipUserGenW = 330 * scaleX;
    const chipUserGenTitleX = 882 * scaleX;
    const chipUserGenValueX = 1200 * scaleX;
    const chipSiteGenX = 870 * scaleX;
    const chipSiteGenW = 330 * scaleX;
    const chipSiteGenTitleX = 882 * scaleX;
    const chipSiteGenValueX = 1200 * scaleX;
    const chipWindX = 870 * scaleX;
    const chipWindW = 330 * scaleX;
    const chipWindTitleX = 882 * scaleX;
    const chipWindValueX = 1200 * scaleX;
    const legendX = 30 * scaleX;
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
      chipActiveX,
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
          <text class="t-id" x="${x + 14 * layout.scaleX}" y="${top + 16}">${num}</text>
          <rect class="status-pill" x="${x + 100 * layout.scaleX}" y="${top + 7}" width="${76 * layout.scaleX}" height="20" rx="10"/>
          <text class="t-status" x="${x + 138 * layout.scaleX}" y="${top + 21}"></text>
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
        <text class="grid-col" x="${layout.ownerCx}" y="${cy - 193}" text-anchor="middle">OWNER</text>
        <text class="grid-col" x="${layout.siteCx}" y="${cy - 193}" text-anchor="middle">SITE</text>
        <line class="grid-divider" x1="${layout.gridDividerX1}" y1="${cy - 175}" x2="${layout.gridDividerX2}" y2="${cy - 175}"/>
        <text class="grid-label" x="${layout.gridTitleX}" y="${cy - 153}" text-anchor="middle">Export</text>
        <text class="grid-power" data-grid="owner-power" x="${layout.ownerCx}" y="${cy - 121}" text-anchor="middle">—</text>
        <text class="grid-unit" data-grid="owner-power-unit" x="${layout.ownerCx}" y="${cy - 103}" text-anchor="middle"></text>
        <text class="grid-power" data-grid="site-power" x="${layout.siteCx}" y="${cy - 121}" text-anchor="middle">—</text>
        <text class="grid-unit" data-grid="site-power-unit" x="${layout.siteCx}" y="${cy - 103}" text-anchor="middle"></text>
        <line class="grid-divider" x1="${layout.gridDividerX1}" y1="${cy - 87}" x2="${layout.gridDividerX2}" y2="${cy - 87}"/>
        <text class="grid-label" x="${layout.gridTitleX}" y="${cy - 65}" text-anchor="middle">To Grid Today</text>
        <text class="grid-energy" data-grid="owner-energy" x="${layout.ownerCx}" y="${cy - 39}" text-anchor="middle">—</text>
        <text class="grid-unit" data-grid="owner-energy-unit" x="${layout.ownerCx}" y="${cy - 21}" text-anchor="middle">kWh</text>
        <text class="grid-energy" data-grid="site-energy" x="${layout.siteCx}" y="${cy - 39}" text-anchor="middle">—</text>
        <text class="grid-unit" data-grid="site-energy-unit" x="${layout.siteCx}" y="${cy - 21}" text-anchor="middle">kWh</text>
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
        <rect x="${layout.chipRightColX}" y="24" width="${140 * layout.scaleX}" height="30" rx="15"/>
        <text class="chip-label" x="${layout.chipRightColX + 12 * layout.scaleX}" y="44">Active Turbines</text>
        <text class="chip-value" data-chip="active" x="${layout.chipActiveX}" y="44" text-anchor="end">—</text>

        <!-- Right side: Owner Generation & Capacity (far right) -->
        <g class="user-gen" data-user-gen="panel">
          <rect x="${layout.chipUserGenX}" y="24" width="${layout.chipUserGenW}" height="150" rx="8"/>
          <text class="user-gen-title" x="${layout.chipUserGenTitleX}" y="48">Owner Generation & Capacity</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="92">Generation</text>
          <text class="user-gen-value" data-user-gen="energy" x="${layout.chipUserGenValueX}" y="92" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="128">Your Share (W)</text>
          <text class="user-gen-value user-gen-share" data-user-gen="share" x="${layout.chipUserGenValueX}" y="128" text-anchor="end">—</text>
          <text class="user-gen-label" x="${layout.chipUserGenTitleX}" y="164">Share (‱)</text>
          <text class="user-gen-value" data-user-gen="sharepct" x="${layout.chipUserGenValueX}" y="164" text-anchor="end">—</text>
        </g>

        <!-- Right side: Site Generation & Capacity (below Owner) -->
        <g class="site-gen" data-site-gen="panel">
          <rect x="${layout.chipSiteGenX}" y="184" width="${layout.chipSiteGenW}" height="120" rx="8"/>
          <text class="site-gen-title" x="${layout.chipSiteGenTitleX}" y="208">Site Generation & Capacity</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="234">Generation</text>
          <text class="site-gen-value" data-site-gen="energy" x="${layout.chipSiteGenValueX}" y="234" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="260">Site Capacity Factor (%)</text>
          <text class="site-gen-value" data-site-gen="capacity" x="${layout.chipSiteGenValueX}" y="260" text-anchor="end">—</text>
          <text class="site-gen-label" x="${layout.chipSiteGenTitleX}" y="286">Site Power (MW)</text>
          <text class="site-gen-value" data-site-gen="power" x="${layout.chipSiteGenValueX}" y="286" text-anchor="end">—</text>
        </g>

        <!-- Right side: Wind & Forecast panel (below Site Generation) -->
        <g class="wind-panel" data-wind="panel">
          <rect x="${layout.chipWindX}" y="314" width="${layout.chipWindW}" height="82" rx="8"/>
          <text class="wind-title" x="${layout.chipWindTitleX}" y="338">Wind & Forecast</text>
          <text class="wind-label" x="${layout.chipWindTitleX}" y="364">Current Wind</text>
          <text class="wind-value" data-chip="wind" x="${layout.chipWindValueX}" y="364" text-anchor="end">—</text>
          <text class="wind-label" x="${layout.chipWindTitleX}" y="390">Forecast (1h)</text>
          <text class="wind-value" data-chip="forecast" x="${layout.chipWindValueX}" y="390" text-anchor="end">—</text>
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
    this._setText(root, '[data-grid="owner-power"]', ownerPowerText.value);
    this._setText(root, '[data-grid="owner-power-unit"]', ownerPowerText.unit);
    let sitePowerText =
      sitePowerMw === null ? { value: "—", unit: "" } : { value: this._fmt(sitePowerMw, 2), unit: "MW" };
    this._setText(root, '[data-grid="site-power"]', sitePowerText.value);
    this._setText(root, '[data-grid="site-power-unit"]', sitePowerText.unit);

    const ownerEnergy = this._scaleKwh(ownerEnergyKwh);
    const siteEnergy = this._scaleKwh(siteEnergyKwh);
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

    // Generation & capacity panel (top right)
    const ownerGenToday = this._num(config.owner_generation_today_entity);
    if (ownerGenToday !== null) {
      const scaled = this._scaleKwh(ownerGenToday);
      this._setText(root, '[data-user-gen="energy"]', `${scaled.value} ${scaled.unit}`);
    } else {
      this._setText(root, '[data-user-gen="energy"]', "—");
    }
    const siteCap = this._num(config.capacity_entity);
    // Your share: owner export power is reported in kW; display in watts.
    this._setText(root, '[data-user-gen="share"]', ownerExportKw === null ? "—" : `${this._fmt(ownerExportKw * 1000, 0)} W`);
    // Your share as a % of the site's generation today (observed).
    const sharePct =
      ownerEnergyKwh !== null && siteEnergyKwh !== null && siteEnergyKwh > 0
        ? (ownerEnergyKwh / siteEnergyKwh) * 100
        : null;
    this._setText(root, '[data-user-gen="sharepct"]', sharePct === null ? "—" : `${this._fmt(sharePct * 100, 2)}‱`);

    // Site Generation & Capacity panel
    const siteGenToday = this._num(config.grid_energy_entity);
    if (siteGenToday !== null) {
      const scaled = this._scaleKwh(siteGenToday);
      this._setText(root, '[data-site-gen="energy"]', `${scaled.value} ${scaled.unit}`);
    } else {
      this._setText(root, '[data-site-gen="energy"]', "—");
    }
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
      if (pill) pill.setAttribute("fill", status.color);
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
      :host { display: block; width: 100%; height: 100%; -webkit-tap-highlight-color: transparent; }
      ha-card { overflow: hidden; height: calc(100vh - 64px); box-sizing: border-box; }
      .shell { padding: 12px; background: var(--ha-card-background, #f1f5f9); border-radius: 12px; height: 100%; box-sizing: border-box; }
      svg { width: 100%; height: 100%; display: block; touch-action: none; user-select: none; -webkit-user-select: none; }
      .bg { fill: var(--ha-card-background, #f1f5f9); }

      /* Lines */
      .feed-line { stroke: rgba(2,132,199,0.35); stroke-width: 3; }
      .flow-dot { fill: #0284c7; }

      /* Turbine nodes */
      .node-rect { fill: var(--ha-card-background, #ffffff); stroke: var(--divider-color, #cbd5e1); stroke-width: 1.5; }
      .node-rect[data-status] { opacity: 1; }
      .turbine:hover .node-rect { stroke: #0284c7; }
      .t-id { fill: var(--primary-text-color, #0f172a); font: bold 19px var(--font-family, sans-serif); }
      .status-pill { fill: #22c55e; }
      .t-status { fill: #06121f; font: bold 12px var(--font-family, sans-serif); text-anchor: middle; }
      .t-power { fill: var(--primary-text-color, #0f172a); font: bold 25px var(--font-family, sans-serif); }
      .t-op { fill: var(--primary-text-color, #0f172a); font: bold 14px var(--font-family, sans-serif); }
      .t-wind { fill: var(--secondary-text-color, #475569); font: 14px var(--font-family, sans-serif); }
      .t-detail { fill: var(--secondary-text-color, #475569); font: 14px var(--font-family, sans-serif); }
      .t-last { fill: var(--disabled-text-color, #64748b); font: 12px var(--font-family, sans-serif); }

      /* Bus */
      .bus rect { fill: #e0f2fe; stroke: #2563eb; stroke-width: 2; }

      /* Transformer label (overlaid down the site collection bus) */
      .xfmr-title { fill: var(--primary-text-color, #0f172a); font: bold 18px var(--font-family, sans-serif); }

      /* Grid node */
      .grid-rect { fill: #ecfdf5; stroke: #4d7c0f; stroke-width: 2; }
      .grid-title { fill: #4d7c0f; font: bold 22px var(--font-family, sans-serif); }
      .grid-col { fill: #4d7c0f; font: bold 22px var(--font-family, sans-serif); }
      .grid-label { fill: var(--secondary-text-color, #475569); font: 22px var(--font-family, sans-serif); }
      .grid-power { fill: var(--primary-text-color, #0f172a); font: bold 22px var(--font-family, sans-serif); }
      .grid-energy { fill: var(--primary-text-color, #0f172a); font: bold 22px var(--font-family, sans-serif); }
      .grid-unit { fill: var(--disabled-text-color, #64748b); font: 22px var(--font-family, sans-serif); }
      .grid-divider { stroke: #84cc16; stroke-width: 2; }

      /* Chips */
      .chips rect { fill: var(--ha-card-background, #ffffff); stroke: var(--divider-color, #cbd5e1); stroke-width: 1.5; }
      .chip-label { fill: var(--secondary-text-color, #475569); font: 13px var(--font-family, sans-serif); }
      .chip-value { fill: var(--primary-text-color, #0f172a); font: bold 14px var(--font-family, sans-serif); }

      /* Generation & capacity panel (top right) */
      .user-gen rect { fill: var(--ha-card-background, #ffffff); stroke: var(--divider-color, #cbd5e1); stroke-width: 1.5; }
      .user-gen-title { fill: var(--primary-text-color, #0f172a); font: bold 20px var(--font-family, sans-serif); }
      .user-gen-label { fill: var(--secondary-text-color, #475569); font: 13px var(--font-family, sans-serif); }
      .user-gen-value { fill: var(--primary-text-color, #0f172a); font: bold 23px var(--font-family, sans-serif); }
      .user-gen-share { fill: #16a34a; font: bold 23px var(--font-family, sans-serif); }

      /* Site Generation & Capacity panel (below Owner) */
      .site-gen rect { fill: var(--ha-card-background, #ffffff); stroke: var(--divider-color, #cbd5e1); stroke-width: 1.5; }
      .site-gen-title { fill: var(--primary-text-color, #0f172a); font: bold 20px var(--font-family, sans-serif); }
      .site-gen-label { fill: var(--secondary-text-color, #475569); font: 13px var(--font-family, sans-serif); }
      .site-gen-value { fill: var(--primary-text-color, #0f172a); font: bold 23px var(--font-family, sans-serif); }

      /* Wind & forecast panel (below Site Generation) */
      .wind-panel rect { fill: var(--ha-card-background, #ffffff); stroke: var(--divider-color, #cbd5e1); stroke-width: 1.5; }
      .wind-title { fill: var(--primary-text-color, #0f172a); font: bold 20px var(--font-family, sans-serif); }
      .wind-label { fill: var(--secondary-text-color, #475569); font: 13px var(--font-family, sans-serif); }
      .wind-value { fill: var(--primary-text-color, #0f172a); font: bold 23px var(--font-family, sans-serif); }

      /* Alarm indicator (always visible: OK = green, ALARM = flashing red) */
      .alarm rect { fill: #dcfce7; stroke: #16a34a; stroke-width: 2; }
      .alarm-text { fill: #15803d; font: bold 13px var(--font-family, sans-serif); }
      .alarm.fault rect { fill: #fef2f2; stroke: #ef4444; stroke-width: 2; }
      .alarm.fault .alarm-text { fill: #b91c1c; }
      .alarm.fault { animation: khscada-alarm-flash 1s steps(1, end) infinite; }
      @keyframes khscada-alarm-flash {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.15; }
      }

      /* Legend */
      .legend { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; }
      .lg-item { display: inline-flex; align-items: center; gap: 5px; color: var(--secondary-text-color, #475569); font: 12px var(--font-family, sans-serif); }
      .lg-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

      .empty { padding: 24px 16px; color: var(--secondary-text-color); }
    `;
  }
}

// Bus → grid flow dot is defined inside _buildTransformer().
if (!customElements.get("kirkhill-wind-scada")) {
  customElements.define("kirkhill-wind-scada", KirkHillWindScada);
}
