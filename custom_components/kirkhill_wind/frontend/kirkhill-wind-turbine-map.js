class KirkHillWindTurbineMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._vb = null;        // current viewBox {x, y, w, h}
    this._defaultVb = null; // viewBox at initial render (for reset)
    this._drag = null;      // {x, y} when dragging
    this._pinchStart = null; // distance between fingers when pinch started
    this._needsRebuild = true;
    this._lastViewport = null; // {zoom, originX, originY} used for marker positions
    // Window-level listeners are registered once and must be removed on
    // disconnect; otherwise every rebuild stacked duplicates (multiplying
    // pan speed and firing after the card is removed from the DOM).
    this._windowMouseMove = null;
    this._windowMouseUp = null;
  }

  connectedCallback() {
    this._render();
  }

  disconnectedCallback() {
    this._removeWindowListeners();
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.turbines) || config.turbines.length === 0) {
      throw new Error("turbines must be a non-empty array");
    }

    this.config = {
      title: "",
      zoom: null,
      ...config,
    };
    this._needsRebuild = true;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return {
      columns: 12,
      rows: 12,
      min_rows: 10,
      max_rows: 14,
    };
  }

  // Fixed internal canvas dimensions — SVG scales via CSS width:100%/height:auto.
  // Zoom is always calculated against these dimensions so it is consistent
  // regardless of when/how wide the card actually renders.
  static MAP_W = 900;
  static MAP_H = 700;
  static MAP_PAD = 80;
  static TILE_SIZE = 256;

  _render() {
    if (!this.config || !this.shadowRoot) {
      return;
    }

    const header = this.config.title ? ` header="${this._escape(this.config.title)}"` : "";
    const turbines = this._collectTurbines();
    const visibleTurbines = turbines.filter((t) =>
      this._isValidCoordinatePair(t.latitude, t.longitude),
    );

    if (visibleTurbines.length === 0) {
      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card${header}>
          <div class="empty">Turbine coordinates are not available yet.</div>
        </ha-card>
      `;
      this._vb = null;
      this._needsRebuild = true;
      return;
    }

    const { zoom, originX, originY } = this._resolveViewport(visibleTurbines);
    const W = KirkHillWindTurbineMap.MAP_W;
    const H = KirkHillWindTurbineMap.MAP_H;

    const svgEl = this.shadowRoot.querySelector("svg.map");

    if (!svgEl || this._needsRebuild) {
      // Full rebuild — only happens on first render or config change
      const tiles = this._renderTiles(originX, originY, zoom);
      const markers = visibleTurbines
        .map((t) => this._renderMarker(t, originX, originY, zoom))
        .join("");

      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card${header}>
          <div class="map-shell">
            <svg class="map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Turbine map">
              <defs>
                <clipPath id="khmap-clip">
                  <rect x="0" y="0" width="${W}" height="${H}" />
                </clipPath>
              </defs>
              <g clip-path="url(#khmap-clip)">
                ${tiles}
                <g class="markers">${markers}</g>
              </g>
            </svg>
            <div class="legend">
              <span class="status">
                <span class="dot running"></span>Running
                <span class="dot stopped"></span>Stopped
              </span>
              <span>Scroll/pinch to zoom · Drag to pan · Double-click to reset</span>
              <span>&copy; OpenStreetMap contributors</span>
            </div>
          </div>
        </ha-card>
      `;

      this._vb = { x: 0, y: 0, w: W, h: H };
      this._defaultVb = { x: 0, y: 0, w: W, h: H };
      this._lastViewport = { zoom, originX, originY };
      this._needsRebuild = false;
      this._attachInteraction();
    } else {
      // Partial update — only refresh marker states (spin speed, active class, detail text)
      const markersEl = this.shadowRoot.querySelector("g.markers");
      if (markersEl && this._lastViewport) {
        const { zoom: vz, originX: vox, originY: voy } = this._lastViewport;
        markersEl.innerHTML = visibleTurbines
          .map((t) => this._renderMarker(t, vox, voy, vz))
          .join("");
      }
    }
  }

  _attachInteraction() {
    const svg = this.shadowRoot.querySelector("svg.map");
    if (!svg) return;

    // Track the current svg so the once-registered window listeners always
    // operate on the latest element (rebuilt on every reload).
    this._currentSvg = svg;

    // Register the window-level listeners exactly once. svg is replaced on
    // each rebuild, so those svg-attached listeners are fine to re-add, but
    // window listeners would duplicate otherwise.
    if (this._windowMouseMove === null) {
      this._windowMouseMove = (e) => {
        if (!this._drag) return;
        const s = this._currentSvg;
        if (!s) return;
        this._panViewBox(e.clientX - this._drag.x, e.clientY - this._drag.y, s);
        this._drag = { x: e.clientX, y: e.clientY };
      };
      window.addEventListener("mousemove", this._windowMouseMove);

      this._windowMouseUp = () => {
        if (!this._drag) return;
        this._drag = null;
        const s = this._currentSvg;
        if (s) {
          s.style.cursor = "grab";
        }
      };
      window.addEventListener("mouseup", this._windowMouseUp);
    }

    // Scroll wheel zoom
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
      this._zoomViewBox(factor, this._svgPoint(svg, e.clientX, e.clientY));
    }, { passive: false });

    // Mouse drag start/end on the svg element itself (re-added per rebuild; the
    // old svg is discarded so these do not leak).
    svg.addEventListener("mousedown", (e) => {
      e.preventDefault();
      this._drag = { x: e.clientX, y: e.clientY };
      svg.style.cursor = "grabbing";
    });

    // Touch drag + pinch
    svg.addEventListener("touchstart", (e) => {
      e.preventDefault();
      if (e.touches.length === 1) {
        this._drag = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        this._pinchStart = null;
      } else if (e.touches.length === 2) {
        this._drag = null;
        this._pinchStart = this._touchDist(e.touches);
      }
    }, { passive: false });

    svg.addEventListener("touchmove", (e) => {
      e.preventDefault();
      if (e.touches.length === 1 && this._drag) {
        this._panViewBox(
          e.touches[0].clientX - this._drag.x,
          e.touches[0].clientY - this._drag.y,
          svg,
        );
        this._drag = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      } else if (e.touches.length === 2 && this._pinchStart !== null) {
        const newDist = this._touchDist(e.touches);
        const factor = this._pinchStart / newDist;
        const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        this._zoomViewBox(factor, this._svgPoint(svg, midX, midY));
        this._pinchStart = newDist;
      }
    }, { passive: false });

    svg.addEventListener("touchend", () => {
      this._drag = null;
      this._pinchStart = null;
    });

    // Double-click / double-tap resets to default view
    svg.addEventListener("dblclick", () => {
      if (this._defaultVb) {
        this._vb = { ...this._defaultVb };
        this._applyViewBox(svg);
      }
    });
  }

  _removeWindowListeners() {
    if (this._windowMouseMove !== null) {
      window.removeEventListener("mousemove", this._windowMouseMove);
      this._windowMouseMove = null;
    }
    if (this._windowMouseUp !== null) {
      window.removeEventListener("mouseup", this._windowMouseUp);
      this._windowMouseUp = null;
    }
    this._currentSvg = null;
  }

  _svgPoint(svg, clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    const vb = this._vb ?? { x: 0, y: 0, w: KirkHillWindTurbineMap.MAP_W, h: KirkHillWindTurbineMap.MAP_H };
    return {
      x: ((clientX - rect.left) / rect.width) * vb.w + vb.x,
      y: ((clientY - rect.top) / rect.height) * vb.h + vb.y,
    };
  }

  _zoomViewBox(factor, center) {
    if (!this._vb) return;
    const W = KirkHillWindTurbineMap.MAP_W;
    const H = KirkHillWindTurbineMap.MAP_H;
    const minW = 80;
    const maxW = W * 4;
    const newW = Math.min(maxW, Math.max(minW, this._vb.w * factor));
    const newH = newW * (H / W);
    const ratioX = (center.x - this._vb.x) / this._vb.w;
    const ratioY = (center.y - this._vb.y) / this._vb.h;
    this._vb = {
      x: center.x - ratioX * newW,
      y: center.y - ratioY * newH,
      w: newW,
      h: newH,
    };
    const svg = this.shadowRoot.querySelector("svg.map");
    if (svg) this._applyViewBox(svg);
  }

  _panViewBox(dx, dy, svg) {
    if (!this._vb) return;
    const rect = svg.getBoundingClientRect();
    this._vb.x -= (dx / rect.width) * this._vb.w;
    this._vb.y -= (dy / rect.height) * this._vb.h;
    this._applyViewBox(svg);
  }

  _applyViewBox(svg) {
    if (!this._vb || !svg) return;
    const { x, y, w, h } = this._vb;
    svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
  }

  _touchDist(touches) {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.hypot(dx, dy);
  }

  _collectTurbines() {
    return this.config.turbines.map((config) => {
      const state = this._hass?.states?.[config.state_entity];
      const power = this._number(this._hass?.states?.[config.power_entity]?.state);
      const capacity = this._number(this._hass?.states?.[config.capacity_entity]?.state);
      const active = this._hass?.states?.[config.active_entity]?.state === "on";
      const status = state?.attributes?.status;
      const statusStartedAt = state?.attributes?.status_started_at;

      return {
        name: config.name || "Turbine",
        stateText: state?.state || "Unavailable",
        status: status || null,
        statusStartedAt: statusStartedAt || null,
        latitude: this._number(state?.attributes?.latitude),
        longitude: this._number(state?.attributes?.longitude),
        power,
        capacity,
        active,
      };
    });
  }

  _isValidCoordinatePair(lat, lon) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
    if (lat < -85 || lat > 85 || lon < -180 || lon > 180) return false;
    // reject null-island
    if (Math.abs(lat) < 0.0001 && Math.abs(lon) < 0.0001) return false;
    return true;
  }

  _project(lat, lon, zoom) {
    const scale = KirkHillWindTurbineMap.TILE_SIZE * Math.pow(2, zoom);
    const sin = Math.sin((lat * Math.PI) / 180);
    return {
      x: ((lon + 180) / 360) * scale,
      y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale,
    };
  }

  _resolveViewport(turbines) {
    const W = KirkHillWindTurbineMap.MAP_W;
    const H = KirkHillWindTurbineMap.MAP_H;
    const PAD = KirkHillWindTurbineMap.MAP_PAD;

    // Manual zoom from config
    const configuredZoom = Number(this.config.zoom);
    if (Number.isFinite(configuredZoom)) {
      const zoom = Math.max(1, Math.min(19, configuredZoom));
      const xs = turbines.map((t) => this._project(t.latitude, t.longitude, zoom).x);
      const ys = turbines.map((t) => this._project(t.latitude, t.longitude, zoom).y);
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      return { zoom, originX: cx - W / 2, originY: cy - H / 2 };
    }

    // Auto zoom: search from 17 down to 12 — sensible range for a wind farm
    for (let zoom = 17; zoom >= 12; zoom--) {
      const xs = turbines.map((t) => this._project(t.latitude, t.longitude, zoom).x);
      const ys = turbines.map((t) => this._project(t.latitude, t.longitude, zoom).y);
      const spanX = Math.max(...xs) - Math.min(...xs);
      const spanY = Math.max(...ys) - Math.min(...ys);
      if (spanX <= W - PAD * 2 && spanY <= H - PAD * 2) {
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
        return { zoom, originX: cx - W / 2, originY: cy - H / 2 };
      }
    }

    // Fallback: zoom 12, centred on turbines
    const zoom = 12;
    const xs = turbines.map((t) => this._project(t.latitude, t.longitude, zoom).x);
    const ys = turbines.map((t) => this._project(t.latitude, t.longitude, zoom).y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
    const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    return { zoom, originX: cx - W / 2, originY: cy - H / 2 };
  }

  _renderTiles(originX, originY, zoom) {
    const TS = KirkHillWindTurbineMap.TILE_SIZE;
    const W = KirkHillWindTurbineMap.MAP_W;
    const H = KirkHillWindTurbineMap.MAP_H;
    const maxTile = Math.pow(2, zoom);
    let html = "";

    for (let tx = Math.floor(originX / TS); tx <= Math.floor((originX + W) / TS); tx++) {
      for (let ty = Math.floor(originY / TS); ty <= Math.floor((originY + H) / TS); ty++) {
        if (ty < 0 || ty >= maxTile) continue;
        const wx = ((tx % maxTile) + maxTile) % maxTile;
        const left = tx * TS - originX;
        const top = ty * TS - originY;
        html += `<image href="https://tile.openstreetmap.org/${zoom}/${wx}/${ty}.png" x="${left}" y="${top}" width="${TS}" height="${TS}" />`;
      }
    }
    return html;
  }

  _renderMarker(turbine, originX, originY, zoom) {
    const { x, y } = this._project(turbine.latitude, turbine.longitude, zoom);
    const left = x - originX;
    const top = y - originY;
    const duration = this._spinDuration(turbine);
    const detail = Number.isFinite(turbine.capacity)
      ? `${turbine.capacity.toFixed(1)}% CF`
      : Number.isFinite(turbine.power)
        ? `${turbine.power.toFixed(2)} kW`
        : turbine.stateText;
    const statusText = turbine.active ? "Running" : "Stopped";
    const statusAt = turbine.statusStartedAt ? ` at ${this._formatShortDateTime(turbine.statusStartedAt)}` : "";
    const titleText = `${turbine.name}: ${statusText} · ${detail}${statusAt}`;
    const animStyle = duration ? `animation-duration:${duration.toFixed(2)}s;` : "";
    const activeClass = turbine.active ? "is-active" : "is-inactive";
    const spinClass = duration ? "is-spinning" : "";

    const label = this._escape(turbine.name);
    return `
      <g class="marker ${activeClass}" transform="translate(${left},${top})">
        <title>${this._escape(titleText)}</title>
        <circle class="marker-disc" r="22" />
        <g class="rotor ${spinClass}" style="${animStyle}">
          <line x1="0" y1="0" x2="0" y2="16" class="tower"></line>
          <circle r="3" class="hub"></circle>
          <g class="blades">
            <path d="M0 0 L-10 -8 Q-14 -10 -12 -14 Q-10 -17 -6 -14 Z" class="blade"></path>
            <path d="M0 0 L5 -14 Q7 -18 11 -16 Q15 -14 12 -10 Z" class="blade"></path>
            <path d="M0 0 L10 8 Q14 10 12 14 Q10 17 6 14 Z" class="blade"></path>
          </g>
        </g>
        <rect class="label-bg" x="-13" y="-41" width="26" height="16" rx="4" />
        <text class="turbine-id" y="-29">${label}</text>
        <text class="turbine-detail" y="36">${this._escape(detail)}</text>
      </g>
    `;
  }

  _formatShortDateTime(value) {
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return value;
    return dt.toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  _spinDuration(turbine) {
    if (!turbine.active) return null;
    let normalized = null;
    if (Number.isFinite(turbine.capacity)) {
      normalized = Math.max(0, Math.min(100, turbine.capacity)) / 100;
    } else if (Number.isFinite(turbine.power) && turbine.power > 0) {
      normalized = Math.max(0.05, Math.min(1, turbine.power / 2500));
    }
    if (!normalized || normalized <= 0) return null;
    return 6 - normalized * 5;
  }

  _number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  _styles() {
    return `
      :host { display: block; }

      ha-card { overflow: hidden; }

      .map-shell {
        display: flex;
        flex-direction: column;
      }

      svg.map {
        width: 100%;
        height: auto;
        display: block;
        background: #cfe4f7;
        cursor: grab;
        touch-action: none;
        user-select: none;
      }

      svg.map:active { cursor: grabbing; }

      .marker { cursor: default; }

      .marker-disc {
        fill: rgba(15, 23, 42, 0.55);
        stroke-width: 2;
      }
      .marker.is-active .marker-disc { stroke: #22c55e; }
      .marker.is-inactive .marker-disc { stroke: #94a3b8; opacity: 0.6; }

      .rotor {
        transform-box: fill-box;
        transform-origin: center;
      }
      .rotor.is-spinning {
        animation: turbine-spin var(--spin-duration, 2s) linear infinite;
        animation-duration: inherit;
      }

      .tower { stroke: #4b5563; stroke-width: 2.5; stroke-linecap: round; }
      .hub { fill: #0f172a; }
      .blade { fill: #f8fafc; stroke: #1f2937; stroke-width: 0.8; stroke-linejoin: round; }
      .marker.is-inactive .blade { fill: #94a3b8; }

      .label-bg {
        fill: rgba(0,0,0,0.65);
      }
      .turbine-id {
        font-size: 11px;
        font-weight: 700;
        fill: #fff;
        text-anchor: middle;
        dominant-baseline: middle;
      }
      .turbine-detail {
        font-size: 9px;
        fill: rgba(255,255,255,0.85);
        text-anchor: middle;
        dominant-baseline: middle;
      }

      .legend {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 8px 12px 12px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .legend .status {
        display: inline-flex;
        align-items: center;
        gap: 8px;
      }
      .legend .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
      }
      .legend .dot.running { background: #22c55e; }
      .legend .dot.stopped { background: #94a3b8; }

      .empty { padding: 24px 16px; color: var(--secondary-text-color); }

      @keyframes turbine-spin { to { transform: rotate(360deg); } }
    `;
  }
}

if (!customElements.get("kirkhill-wind-turbine-map")) {
  customElements.define("kirkhill-wind-turbine-map", KirkHillWindTurbineMap);
}
