class KirkHillWindTurbineMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this._render();
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
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return {
      columns: 12,
      rows: 10,
      min_rows: 8,
      max_rows: 12,
    };
  }

  // Fixed internal canvas dimensions — SVG scales via CSS width:100%/height:auto.
  // Zoom is always calculated against these dimensions so it is consistent
  // regardless of when/how wide the card actually renders.
  static MAP_W = 900;
  static MAP_H = 560;
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
      return;
    }

    const { zoom, originX, originY } = this._resolveViewport(visibleTurbines);
    const tiles = this._renderTiles(originX, originY, zoom);
    const markers = visibleTurbines
      .map((t) => this._renderMarker(t, originX, originY, zoom))
      .join("");

    const W = KirkHillWindTurbineMap.MAP_W;
    const H = KirkHillWindTurbineMap.MAP_H;

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
              ${markers}
            </g>
          </svg>
          <div class="legend">
            <span>Rotation speed uses live site capacity factor when available.</span>
            <span>&copy; OpenStreetMap contributors</span>
          </div>
        </div>
      </ha-card>
    `;
  }

  _collectTurbines() {
    return this.config.turbines.map((config) => {
      const state = this._hass?.states?.[config.state_entity];
      const power = this._number(this._hass?.states?.[config.power_entity]?.state);
      const capacity = this._number(this._hass?.states?.[config.capacity_entity]?.state);
      const active = this._hass?.states?.[config.active_entity]?.state === "on";

      return {
        name: config.name || "Turbine",
        stateText: state?.state || "Unavailable",
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

    // Auto zoom: search from 17 down to 8 — sensible range for a wind farm
    for (let zoom = 17; zoom >= 8; zoom--) {
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

    // Fallback: zoom 8, centred on turbines
    const zoom = 8;
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
    const animStyle = duration ? `animation-duration:${duration.toFixed(2)}s;` : "";
    const activeClass = turbine.active ? "is-active" : "is-inactive";
    const spinClass = duration ? "is-spinning" : "";

    return `
      <g class="marker ${activeClass}" transform="translate(${left},${top})">
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
        <text class="turbine-label" y="32">${this._escape(turbine.name)}</text>
        <text class="turbine-detail" y="44">${this._escape(detail)}</text>
      </g>
    `;
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
      }

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

      .turbine-label {
        font-size: 11px;
        font-weight: 700;
        fill: #fff;
        stroke: rgba(0,0,0,0.8);
        stroke-width: 0.4px;
        paint-order: stroke;
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

      .empty { padding: 24px 16px; color: var(--secondary-text-color); }

      @keyframes turbine-spin { to { transform: rotate(360deg); } }
    `;
  }
}

if (!customElements.get("kirkhill-wind-turbine-map")) {
  customElements.define("kirkhill-wind-turbine-map", KirkHillWindTurbineMap);
}
