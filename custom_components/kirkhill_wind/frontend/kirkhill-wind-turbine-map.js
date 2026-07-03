class KirkHillWindTurbineMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._resizeObserver = new ResizeObserver(() => this._render());
  }

  connectedCallback() {
    this._resizeObserver.observe(this);
    this._render();
  }

  disconnectedCallback() {
    this._resizeObserver.disconnect();
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.turbines) || config.turbines.length === 0) {
      throw new Error("turbines must be a non-empty array");
    }

    this.config = {
      title: "",
      zoom: null,
      height: 560,
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

  _render() {
    if (!this.config || !this.shadowRoot) {
      return;
    }

    const width = Math.max(Math.round(this.getBoundingClientRect().width) || 900, 320);
    const height = Number(this.config.height) || 560;
    const header = this.config.title ? ` header="${this._escape(this.config.title)}"` : "";
    const turbines = this._collectTurbines();
    const visibleTurbines = turbines.filter((turbine) =>
      this._isValidCoordinatePair(turbine.latitude, turbine.longitude),
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

    const viewportTurbines = this._selectViewportTurbines(visibleTurbines);
    const viewport = this._resolveViewport(viewportTurbines, width, height);
    const zoom = viewport.zoom;
    const origin = viewport.origin;
    const tiles = this._renderTiles(origin, zoom, width, height);
    const markers = visibleTurbines
      .map((turbine) => this._renderMarker(turbine, origin, zoom))
      .join("");

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card${header}>
        <div class="map-shell" style="height:${height}px;">
          <div class="map-surface">
            ${tiles}
            ${markers}
          </div>
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

  _resolveViewport(turbines, width, height) {
    const configuredZoom = Number(this.config.zoom);
    const manualZoom = Number.isFinite(configuredZoom)
      ? Math.max(1, Math.min(19, configuredZoom))
      : null;

    if (manualZoom !== null) {
      const center = this._centerCoordinates(turbines);
      const projected = this._project(center.latitude, center.longitude, manualZoom);
      return {
        zoom: manualZoom,
        origin: {
          x: projected.x - width / 2,
          y: projected.y - height / 2,
        },
      };
    }

    const padding = 72;
    const usableWidth = Math.max(width - padding * 2, 120);
    const usableHeight = Math.max(height - padding * 2, 120);

    for (let zoom = 19; zoom >= 1; zoom -= 1) {
      const bounds = this._projectedBounds(turbines, zoom);
      if (bounds.width <= usableWidth && bounds.height <= usableHeight) {
        return {
          zoom,
          origin: {
            x: bounds.centerX - width / 2,
            y: bounds.centerY - height / 2,
          },
        };
      }
    }

    const bounds = this._projectedBounds(turbines, 1);
    return {
      zoom: 1,
      origin: {
        x: bounds.centerX - width / 2,
        y: bounds.centerY - height / 2,
      },
    };
  }

  _centerCoordinates(turbines) {
    const latitude =
      turbines.reduce((sum, turbine) => sum + turbine.latitude, 0) / turbines.length;
    const longitude =
      turbines.reduce((sum, turbine) => sum + turbine.longitude, 0) / turbines.length;
    return { latitude, longitude };
  }

  _projectedBounds(turbines, zoom) {
    const projected = turbines.map((turbine) =>
      this._project(turbine.latitude, turbine.longitude, zoom),
    );
    const xs = projected.map((point) => point.x);
    const ys = projected.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    return {
      width: maxX - minX,
      height: maxY - minY,
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2,
    };
  }

  _renderTiles(origin, zoom, width, height) {
    const tileSize = 256;
    const tileCount = 2 ** zoom;
    const minTileX = Math.floor(origin.x / tileSize) - 1;
    const maxTileX = Math.floor((origin.x + width) / tileSize) + 1;
    const minTileY = Math.floor(origin.y / tileSize) - 1;
    const maxTileY = Math.floor((origin.y + height) / tileSize) + 1;
    let html = "";

    for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
      for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
        if (tileY < 0 || tileY >= tileCount) {
          continue;
        }

        const wrappedX = ((tileX % tileCount) + tileCount) % tileCount;
        const left = tileX * tileSize - origin.x;
        const top = tileY * tileSize - origin.y;
        html += `
          <img
            class="tile"
            alt=""
            loading="lazy"
            src="https://tile.openstreetmap.org/${zoom}/${wrappedX}/${tileY}.png"
            style="left:${left}px;top:${top}px;width:${tileSize}px;height:${tileSize}px;"
          >
        `;
      }
    }

    return html;
  }

  _renderMarker(turbine, origin, zoom) {
    const projected = this._project(turbine.latitude, turbine.longitude, zoom);
    const left = projected.x - origin.x;
    const top = projected.y - origin.y;
    const duration = this._spinDuration(turbine);
    const detail = Number.isFinite(turbine.capacity)
      ? `${turbine.capacity.toFixed(1)}% CF`
      : Number.isFinite(turbine.power)
        ? `${turbine.power.toFixed(2)} kW`
        : turbine.stateText;
    const animationStyle = duration ? `--spin-duration:${duration.toFixed(2)}s;` : "";

    return `
      <div class="marker ${turbine.active ? "is-active" : "is-inactive"}" style="left:${left}px;top:${top}px;">
        <div class="rotor ${duration ? "is-spinning" : ""}" style="${animationStyle}">
          <svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
            <line x1="50" y1="50" x2="50" y2="92" class="tower"></line>
            <circle cx="50" cy="36" r="5" class="hub"></circle>
            <g class="blades">
              <path d="M50 36 L24 28 Q16 26 20 20 Q24 16 30 22 Z" class="blade"></path>
              <path d="M50 36 L62 8 Q66 1 73 5 Q79 9 73 16 Z" class="blade"></path>
              <path d="M50 36 L76 44 Q84 46 80 52 Q76 58 70 52 Z" class="blade"></path>
            </g>
          </svg>
        </div>
        <div class="label">${this._escape(turbine.name)}</div>
        <div class="detail">${this._escape(detail)}</div>
      </div>
    `;
  }

  _spinDuration(turbine) {
    if (!turbine.active) {
      return null;
    }

    let normalized = null;

    if (Number.isFinite(turbine.capacity)) {
      normalized = Math.max(0, Math.min(100, turbine.capacity)) / 100;
    } else if (Number.isFinite(turbine.power) && turbine.power > 0) {
      normalized = Math.max(0.05, Math.min(1, turbine.power / 2500));
    }

    if (!normalized || normalized <= 0) {
      return null;
    }

    return 6 - normalized * 5;
  }

  _isValidCoordinatePair(latitude, longitude) {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      return false;
    }
    if (latitude < -85 || latitude > 85 || longitude < -180 || longitude > 180) {
      return false;
    }
    return !(Math.abs(latitude) < 0.0001 && Math.abs(longitude) < 0.0001);
  }

  _selectViewportTurbines(turbines) {
    if (turbines.length < 3) {
      return turbines;
    }

    const medianLatitude = this._median(turbines.map((turbine) => turbine.latitude));
    const medianLongitude = this._median(turbines.map((turbine) => turbine.longitude));
    const threshold = 0.5;
    const clustered = turbines.filter(
      (turbine) =>
        Math.abs(turbine.latitude - medianLatitude) <= threshold &&
        Math.abs(turbine.longitude - medianLongitude) <= threshold,
    );

    if (clustered.length >= Math.max(2, Math.ceil(turbines.length / 2))) {
      return clustered;
    }

    return turbines;
  }

  _median(values) {
    if (values.length === 0) {
      return 0;
    }
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    if (sorted.length % 2 === 1) {
      return sorted[middle];
    }
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }

  _project(latitude, longitude, zoom) {
    const tileSize = 256;
    const scale = tileSize * 2 ** zoom;
    const sinLatitude = Math.sin((latitude * Math.PI) / 180);

    return {
      x: ((longitude + 180) / 360) * scale,
      y:
        (0.5 -
          Math.log((1 + sinLatitude) / (1 - sinLatitude)) / (4 * Math.PI)) *
        scale,
    };
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
      :host {
        display: block;
      }

      ha-card {
        overflow: hidden;
      }

      .map-shell {
        position: relative;
        display: flex;
        flex-direction: column;
      }

      .map-surface {
        position: relative;
        flex: 1;
        overflow: hidden;
        background: #cfe4f7;
      }

      .tile {
        position: absolute;
        object-fit: cover;
        user-select: none;
      }

      .marker {
        position: absolute;
        transform: translate(-50%, -50%);
        min-width: 68px;
        text-align: center;
        pointer-events: none;
      }

      .rotor {
        width: 54px;
        height: 54px;
        margin: 0 auto 4px;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.35));
      }

      .rotor svg {
        width: 100%;
        height: 100%;
      }

      .rotor.is-spinning svg {
        animation: turbine-spin var(--spin-duration, 2s) linear infinite;
      }

      .tower {
        stroke: #4b5563;
        stroke-width: 5;
        stroke-linecap: round;
      }

      .hub {
        fill: #0f172a;
      }

      .blade {
        fill: #f8fafc;
        stroke: #1f2937;
        stroke-width: 1.5;
        stroke-linejoin: round;
      }

      .marker.is-inactive {
        opacity: 0.5;
      }

      .label,
      .detail {
        display: inline-block;
        padding: 2px 6px;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.72);
        color: #fff;
        backdrop-filter: blur(3px);
      }

      .label {
        font-weight: 600;
        font-size: 12px;
      }

      .detail {
        margin-top: 4px;
        font-size: 11px;
      }

      .legend {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 8px 12px 12px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .empty {
        padding: 24px 16px;
        color: var(--secondary-text-color);
      }

      @keyframes turbine-spin {
        from {
          transform: rotate(0deg);
        }
        to {
          transform: rotate(360deg);
        }
      }
    `;
  }
}

if (!customElements.get("kirkhill-wind-turbine-map")) {
  customElements.define("kirkhill-wind-turbine-map", KirkHillWindTurbineMap);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "kirkhill-wind-turbine-map",
  name: "Kirk Hill Wind Turbine Map",
  description: "Animated turbine map for the Kirk Hill Wind Farm dashboard.",
});
