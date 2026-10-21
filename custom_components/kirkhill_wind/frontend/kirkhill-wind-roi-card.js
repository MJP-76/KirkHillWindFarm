/**
 * Kirk Hill Wind Farm — Return on investment card.
 *
 * The one place money appears. The SCADA card shows generation, power,
 * capacity and wind only; every financial figure lives here:
 *
 *   - the ledger of periods the board declared a p/W rate for, each shown with
 *     its months, rate × watts, £ figure and ROI against the capital;
 *   - the invested amount, entered once and stored beside the records (never
 *     in entry.options, which config-entry migrations purge);
 *   - totals split into board-announced and self-estimated, so an estimate can
 *     never read as something published;
 *   - plain return per period: value ÷ invested × 100. Deliberately not
 *     annualised -- the board pays per period regardless of how long it runs,
 *     so a per-year figure would be a rate of our own invention.
 *
 * Reads one entity: sensor.<farm>_payment_ledger, whose records already carry
 * value_gbp and roi_pct, so this card reports rather than recalculates.
 *
 * Card type: custom:kirkhill-wind-roi
 */
class KirkHillWindRoi extends HTMLElement {
  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    // A missing entity is a message in the body, not a red error card: the
    // dashboard can legitimately be written before the entity registers.
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

  connectedCallback() {
    if (this.config && this.shadowRoot && !this.shadowRoot.innerHTML.trim()) this._render();
  }

  disconnectedCallback() {
    if (this._updateRaf) { cancelAnimationFrame(this._updateRaf); this._updateRaf = null; }
  }

  getCardSize() {
    return 6;
  }

  // ---- data helpers -------------------------------------------------------

  _entityId() {
    const id = this.config?.payment_ledger_entity;
    return id && this._hass?.states?.[id] ? id : null;
  }

  _attr(id, key) {
    return this._hass?.states?.[id]?.attributes?.[key];
  }

  _num(entityId) {
    const s = this._hass?.states?.[entityId]?.state;
    if (s === undefined || s === null || s === "" || s === "unavailable" || s === "unknown") return null;
    const n = parseFloat(String(s).replace(",", ""));
    return Number.isFinite(n) ? n : null;
  }

  _fmt(n, decimals = 2) {
    if (n === null || n === undefined || !Number.isFinite(n)) return "—";
    const s = n.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    return decimals > 0 ? s.replace(/\.?0+$/, "") : s;
  }

  _esc(value) {
    // Notes are free text typed into a form; they are rendered back as HTML.
    return String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  _fmtMonth(iso) {
    // Rows read as "Feb 2025 - Jun 2026": a period is whole months, so the
    // day of the stored 1st/last-day boundary is noise on screen.
    if (!iso) return "—";
    const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }

  _monthLastDay(month) {
    // "2026-06" -> "2026-06-30". Day 0 of the next month is the last day of
    // this one, so leap February comes out right without a lookup table.
    const year = Number(month.slice(0, 4));
    const monthIndex = Number(month.slice(5, 7));
    const last = new Date(year, monthIndex, 0).getDate();
    return `${month}-${String(last).padStart(2, "0")}`;
  }

  _nextPeriodStart(records) {
    // A new line starts the month after the latest declared period ends:
    // Feb 2025 -> Jun 2026 offers 2026-07. Only the start is offered -- when
    // the board's next period ends is not ours to guess.
    if (!records || !records.length) return "";
    const latest = records.reduce((a, b) => ((a.period_end || "") > (b.period_end || "") ? a : b));
    const iso = String(latest.period_end || "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
    let year = Number(iso.slice(0, 4));
    let month = Number(iso.slice(5, 7)) + 1;
    if (month > 12) { month = 1; year += 1; }
    return `${year}-${String(month).padStart(2, "0")}`;
  }

  _records(id) {
    const records = this._attr(id, "records");
    return Array.isArray(records) ? records.filter((r) => r && r.id) : [];
  }

  // ---- render -------------------------------------------------------------

  _render() {
    if (!this.config || !this.shadowRoot) return;
    const title = this.config.title || "Return on investment";
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        <div class="roi">
          <div class="roi-head">
            <h2>${this._esc(title)}</h2>
            <button class="roi-capital" data-roi-action="edit-invested" title="Set what you invested">
              <span class="roi-capital-label">Invested</span>
              <span class="roi-capital-value" data-roi="invested">—</span>
            </button>
          </div>
          <div class="roi-summary">
            <div class="roi-stat">
              <span class="roi-stat-label">Declared total</span>
              <span class="roi-stat-value" data-roi="total">—</span>
            </div>
            <div class="roi-stat">
              <span class="roi-stat-label">Board announced</span>
              <span class="roi-stat-value" data-roi="board">—</span>
            </div>
            <div class="roi-stat">
              <span class="roi-stat-label">Self estimated</span>
              <span class="roi-stat-value" data-roi="self">—</span>
            </div>
            <div class="roi-stat">
              <span class="roi-stat-label">Return</span>
              <span class="roi-stat-value" data-roi="roi">—</span>
            </div>
          </div>
          <div class="roi-list" data-roi="list"></div>
          <div class="roi-caption" data-roi="caption" hidden></div>
          <div class="roi-form-slot" data-roi="form"></div>
        </div>
      </ha-card>
    `;
    this._bindHead();
    this._update();
  }

  _bindHead() {
    const investBtn = this.shadowRoot.querySelector('[data-roi-action="edit-invested"]');
    if (investBtn) investBtn.addEventListener("click", () => this._showInvestedForm());
  }

  _update() {
    if (!this.config || !this.shadowRoot) return;
    const id = this._entityId();
    const list = this.shadowRoot.querySelector('[data-roi="list"]');
    const caption = this.shadowRoot.querySelector('[data-roi="caption"]');
    if (!list) return;

    if (!id) {
      this._setText("total", "—");
      this._setText("board", "—");
      this._setText("self", "—");
      this._setText("roi", "—");
      this._setText("invested", "—");
      list.innerHTML = `<div class="roi-empty">The payment ledger entity is not available yet.</div>`;
      if (caption) caption.hidden = true;
      return;
    }

    const records = this._records(id);
    const investedRaw = this._attr(id, "invested_gbp");
    const invested = investedRaw === null || investedRaw === undefined ? null : Number(investedRaw);

    this._setText("invested", invested === null ? "Set amount" : `£${this._fmt(invested, 2)}`);
    this._setText("total", this._gbp(this._attr(id, "total_gbp")));
    this._setText("board", this._gbp(this._attr(id, "board_total_gbp")));
    this._setText("self", this._gbp(this._attr(id, "self_total_gbp")));
    const roi = this._attr(id, "total_roi_pct");
    this._setText("roi", roi === null || roi === undefined ? "—" : `${this._fmt(Number(roi), 2)}%`);

    // Rows are rebuilt wholesale; the form lives in its own slot so a
    // half-typed entry is never clobbered by a state refresh.
    const body = records.length
      ? records.map((r) => this._rowHTML(r)).join("")
      : `<div class="roi-empty">No period declared yet. Add the first figure the board announced.</div>`;
    list.innerHTML =
      body + `<button class="roi-btn roi-btn--primary" data-roi-action="add">Add period</button>`;
    this._bindList();

    if (caption) this._updateCaption(id, caption);
  }

  _setText(name, value) {
    const el = this.shadowRoot.querySelector(`[data-roi="${name}"]`);
    if (el) el.textContent = value;
  }

  _gbp(value) {
    return value === null || value === undefined || !Number.isFinite(Number(value))
      ? "—"
      : `£${this._fmt(Number(value), 2)}`;
  }

  _rowHTML(record) {
    const value = Number.isFinite(Number(record.value_gbp)) ? Number(record.value_gbp) : null;
    const roiRaw = record.roi_pct;
    const roi = roiRaw === null || roiRaw === undefined || !Number.isFinite(Number(roiRaw))
      ? null
      : Number(roiRaw);
    const self = record.source === "self";
    return `
      <div class="roi-row${self ? " roi-row--self" : ""}" data-record="${this._esc(record.id)}">
        <div class="roi-row-main">
          <span class="roi-row-dates">${this._fmtMonth(record.period_start)} – ${this._fmtMonth(record.period_end)}${self ? ` <span class="roi-tag">self estimate</span>` : ""}</span>
          <span class="roi-row-rate">${this._fmt(Number(record.rate_p_per_w), 2)} p/W × ${this._fmt(Number(record.capacity_watts), 0)} W${record.note ? ` · <span class="roi-note">${this._esc(record.note)}</span>` : ""}</span>
        </div>
        <div class="roi-row-money">
          <span class="roi-row-value">${value === null ? "—" : `${self ? "~" : ""}£${this._fmt(value, 2)}`}</span>
          <span class="roi-row-roi">${roi === null ? "ROI —" : `ROI ${this._fmt(roi, 2)}%`}</span>
        </div>
        <div class="roi-row-actions">
          <button class="roi-btn roi-icon" data-roi-action="edit" aria-label="Edit this period">&#9998;</button>
          <button class="roi-btn roi-icon roi-icon--danger" data-roi-action="delete" aria-label="Remove this period">&#10005;</button>
        </div>
      </div>`;
  }

  _updateCaption(id, caption) {
    const basis = this._attr(id, "current_basis");
    const source = this._attr(id, "current_source");
    const current = this._attr(id, "current_gbp");
    const figure = current === null || current === undefined || !Number.isFinite(Number(current))
      ? null
      : Number(current);

    if (figure === null) { caption.hidden = true; return; }
    if (basis === "estimated_from_last_declared_rate") {
      caption.innerHTML = `Current period not yet declared — estimated at the last rate: <b>~£${this._fmt(figure, 2)}</b>`;
      caption.hidden = false;
    } else if (source === "self") {
      caption.innerHTML = `Current period is <b>your own estimate</b>, not a board announcement: <b>£${this._fmt(figure, 2)}</b>`;
      caption.hidden = false;
    } else {
      caption.innerHTML = `Current period declared by the board: <b>£${this._fmt(figure, 2)}</b>`;
      caption.hidden = false;
    }
  }

  _bindList() {
    const list = this.shadowRoot.querySelector('[data-roi="list"]');
    if (!list) return;
    list.querySelectorAll('[data-roi-action="add"]').forEach((btn) =>
      btn.addEventListener("click", () => this._showForm(null)));
    list.querySelectorAll('[data-roi-action="edit"]').forEach((btn) =>
      btn.addEventListener("click", () => {
        const record = this._records(this._entityId())
          .find((r) => r.id === btn.closest("[data-record]")?.getAttribute("data-record"));
        if (record) this._showForm(record);
      }));
    list.querySelectorAll('[data-roi-action="delete"]').forEach((btn) =>
      btn.addEventListener("click", async () => {
        const recordId = btn.closest("[data-record]")?.getAttribute("data-record");
        if (!recordId || !window.confirm("Remove this payment record?")) return;
        try {
          await this._hass.callService("kirkhill_wind", "remove_payment_record", { record_id: recordId });
          this._update();
        } catch (err) {
          this._formError(err);
        }
      }));
  }

  // ---- period form --------------------------------------------------------

  _formSlot() {
    return this.shadowRoot.querySelector('[data-roi="form"]');
  }

  _showForm(record) {
    const slot = this._formSlot();
    if (!slot) return;
    const r = record || {};
    // Capacity is blank for a new record: the service defaults it to the owner
    // watts the API reports now, while an edit sends the watts in force then.
    const startMonth = record ? String(r.period_start || "").slice(0, 7) : this._nextPeriodStart(this._records(this._entityId()));
    const endMonth = record ? String(r.period_end || "").slice(0, 7) : "";
    const sourceChecked = record ? r.source !== "self" : true;

    slot.innerHTML = `
      <div class="roi-form">
        <div class="roi-form-title">${record ? "Edit period" : "Add period"}</div>
        <label class="roi-label" for="roi-start">Period start (month)</label>
        <input class="roi-input" id="roi-start" type="month" placeholder="YYYY-MM" value="${this._esc(startMonth)}" />
        <label class="roi-label" for="roi-end">Period end (month)</label>
        <input class="roi-input" id="roi-end" type="month" placeholder="YYYY-MM" value="${this._esc(endMonth)}" />
        <label class="roi-label" for="roi-rate">Rate announced (p/W)</label>
        <input class="roi-input" id="roi-rate" type="number" min="0.01" max="1000" step="0.1" value="${r.rate_p_per_w ?? ""}" />
        <label class="roi-label" for="roi-watts">Watts owned (W)</label>
        <input class="roi-input" id="roi-watts" type="number" min="0" step="1" value="${r.capacity_watts ?? ""}" placeholder="defaults to today's capacity" />
        <label class="roi-label" for="roi-note">Note (optional)</label>
        <input class="roi-input" id="roi-note" type="text" maxlength="200" value="${this._esc(r.note || "")}" placeholder="AGM, meeting, statement" />
        <label class="roi-check">
          <input type="checkbox" id="roi-source" ${sourceChecked ? "checked" : ""} />
          <span>Board announced</span>
        </label>
        <div class="roi-hint">Untick to keep it as your own estimate: it is tagged with ~ and counted under the self total.</div>
        <div class="roi-hint">Months only: a period runs from the 1st to the last day.</div>
        <div class="roi-actions">
          <button class="roi-btn" data-roi-action="cancel">Cancel</button>
          <button class="roi-btn roi-btn--primary" data-roi-action="save">Save</button>
        </div>
        <div class="roi-hint roi-error" data-roi="error"></div>
      </div>`;

    slot.querySelector('[data-roi-action="cancel"]').addEventListener("click", () => this._clearForm());
    slot.querySelector('[data-roi-action="save"]').addEventListener("click", () => this._saveForm(slot, record));
    slot.querySelectorAll("input").forEach((input) =>
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") slot.querySelector('[data-roi-action="save"]').click();
      }));
    const first = slot.querySelector("input");
    if (first) first.focus();
  }

  _clearForm() {
    const slot = this._formSlot();
    if (slot) slot.innerHTML = "";
  }

  _formError(err) {
    const slot = this._formSlot();
    const target = slot?.querySelector('[data-roi="error"]') || this.shadowRoot?.querySelector('[data-roi="caption"]');
    if (target) {
      target.hidden = false;
      target.textContent = err?.message || "Save failed";
    }
  }

  async _saveForm(slot, record) {
    const value = (sel) => slot.querySelector(sel)?.value?.trim() || "";
    const start = value("#roi-start");
    const end = value("#roi-end");
    const rate = parseFloat(value("#roi-rate"));
    const wattsRaw = value("#roi-watts");
    const watts = wattsRaw === "" ? null : parseFloat(wattsRaw);
    const note = value("#roi-note");

    // Validate here as well as on the backend: a rejected service call is a
    // silent no-op from the user's side of a form unless the form says why.
    const fail = (message, input) => {
      const target = slot.querySelector('[data-roi="error"]');
      if (target) target.textContent = message;
      const el = slot.querySelector(input);
      if (el) { el.setAttribute("data-error", "true"); el.focus(); }
      return false;
    };
    if (!start || !end) return fail("Both period months are required.", start ? "#roi-end" : "#roi-start");
    const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
    if (!MONTH_RE.test(start) || !MONTH_RE.test(end)) {
      return fail("A period is two months, entered as YYYY-MM (e.g. 2026-07).", MONTH_RE.test(start) ? "#roi-end" : "#roi-start");
    }
    if (end < start) return fail("The end month must not be before the start month.", "#roi-end");
    if (!Number.isFinite(rate) || rate <= 0) return fail("Enter the rate the board announced, in p/W.", "#roi-rate");
    if (watts !== null && (!Number.isFinite(watts) || watts < 0)) return fail("Watts owned must be 0 or more.", "#roi-watts");

    const payload = {
      period_start: `${start}-01`,
      period_end: this._monthLastDay(end),
      rate_p_per_w: rate,
      source: slot.querySelector("#roi-source")?.checked ? "board" : "self",
    };
    if (watts !== null) payload.capacity_watts = watts;
    if (note) payload.note = note;
    if (record) payload.record_id = record.id;

    try {
      await this._hass.callService(
        "kirkhill_wind",
        record ? "update_payment_record" : "add_payment_record",
        payload
      );
    } catch (err) {
      return fail(err?.message || "Save failed", null);
    }
    this._clearForm();
    this._update();
    return true;
  }

  // ---- invested form ------------------------------------------------------

  _showInvestedForm() {
    const slot = this._formSlot();
    if (!slot) return;
    const id = this._entityId();
    const current = id ? this._attr(id, "invested_gbp") : null;
    slot.innerHTML = `
      <div class="roi-form">
        <div class="roi-form-title">Invested amount</div>
        <label class="roi-label" for="roi-invested">Capital invested (GBP)</label>
        <input class="roi-input" id="roi-invested" type="number" min="0" step="0.01" value="${current ?? ""}" placeholder="e.g. 5000" />
        <div class="roi-hint">Stored with the ledger, never in the config entry. Every ROI on this card is measured against it.</div>
        <div class="roi-actions">
          <button class="roi-btn" data-roi-action="cancel">Cancel</button>
          ${current === null || current === undefined ? "" : `<button class="roi-btn roi-btn--danger" data-roi-action="clear">Clear</button>`}
          <button class="roi-btn roi-btn--primary" data-roi-action="save">Save</button>
        </div>
        <div class="roi-hint roi-error" data-roi="error"></div>
      </div>`;

    slot.querySelector('[data-roi-action="cancel"]').addEventListener("click", () => this._clearForm());
    const clearBtn = slot.querySelector('[data-roi-action="clear"]');
    if (clearBtn) {
      clearBtn.addEventListener("click", async () => {
        try {
          await this._hass.callService("kirkhill_wind", "set_invested_amount", { invested_gbp: null });
          this._clearForm();
          this._update();
        } catch (err) {
          this._formError(err);
        }
      });
    }
    slot.querySelector('[data-roi-action="save"]').addEventListener("click", async () => {
      const raw = slot.querySelector("#roi-invested")?.value?.trim() || "";
      const amount = raw === "" ? null : parseFloat(raw);
      const target = slot.querySelector('[data-roi="error"]');
      if (amount !== null && (!Number.isFinite(amount) || amount < 0)) {
        if (target) target.textContent = "Enter an amount of 0 or more, or clear it.";
        return;
      }
      try {
        await this._hass.callService("kirkhill_wind", "set_invested_amount", { invested_gbp: amount });
      } catch (err) {
        if (target) target.textContent = err?.message || "Save failed";
        return;
      }
      this._clearForm();
      this._update();
    });
    const input = slot.querySelector("#roi-invested");
    if (input) {
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") slot.querySelector('[data-roi-action="save"]').click();
      });
      input.focus();
      input.select();
    }
  }

  // ---- styles -------------------------------------------------------------

  _styles() {
    return `
      :host { display: block; }
      ha-card {
        --khroi-font-family: var(--primary-font-family, var(--font-family, Roboto, sans-serif));
        --khroi-primary: var(--primary-text-color, #1c2026);
        --khroi-secondary: var(--secondary-text-color, #546e7a);
        --khroi-bg: var(--ha-card-background, #fff);
        --khroi-divider: var(--divider-color, rgba(0,0,0,0.12));
        --khroi-accent: var(--primary-color, #0284c7);
        --khroi-warn: var(--warning-color, #ffb300);
        --khroi-error: var(--error-color, #d32f2f);
        --khroi-ok: var(--success-color, #2e7d32);
        font-family: var(--khroi-font-family);
      }
      .roi { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
      .roi-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
      .roi-head h2 { margin: 0; font-size: var(--ha-font-size, 16px); font-weight: 600; color: var(--khroi-primary); }
      .roi-capital {
        display: inline-flex; align-items: center; gap: 8px;
        border: 1px solid var(--khroi-divider); border-radius: 16px;
        background: var(--khroi-bg); color: var(--khroi-primary);
        padding: 6px 12px; cursor: pointer;
        font: 600 calc(var(--ha-font-size-small, 14px)) var(--khroi-font-family);
      }
      .roi-capital:hover { border-color: var(--khroi-accent); }
      .roi-capital-label { color: var(--khroi-secondary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; font-size: 11px; }
      .roi-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
      .roi-stat { border: 1px solid var(--khroi-divider); border-radius: 10px; padding: 10px 12px; background: var(--khroi-bg); }
      .roi-stat-label { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--khroi-secondary); }
      .roi-stat-value { display: block; margin-top: 4px; font-weight: 600; font-size: var(--ha-font-size, 16px); color: var(--khroi-primary); }
      .roi-list { display: flex; flex-direction: column; gap: 6px; }
      .roi-empty { color: var(--khroi-secondary); font-size: calc(var(--ha-font-size-small, 14px)); padding: 6px 2px; }
      .roi-row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border: 1px solid var(--khroi-divider); border-radius: 10px; }
      .roi-row--self { border-style: dashed; }
      .roi-row-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
      .roi-row-dates { font-weight: 600; color: var(--khroi-primary); font-size: calc(var(--ha-font-size-small, 14px)); }
      .roi-row-rate { color: var(--khroi-secondary); font-size: calc(var(--ha-font-size-small, 14px)); overflow-wrap: anywhere; }
      .roi-note { font-style: italic; }
      .roi-tag { display: inline-block; padding: 0 6px; border: 1px solid var(--khroi-warn); border-radius: 8px; color: var(--khroi-warn); font-size: 11px; font-style: normal; vertical-align: middle; }
      .roi-row-money { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; white-space: nowrap; }
      .roi-row-value { font-weight: 600; color: var(--khroi-primary); }
      .roi-row-roi { font-size: calc(var(--ha-font-size-small, 14px)); color: var(--khroi-ok); font-weight: 600; }
      .roi-row-actions { display: flex; gap: 6px; }
      .roi-caption { font-size: calc(var(--ha-font-size-small, 14px)); color: var(--khroi-secondary); }
      .roi-caption b { color: var(--khroi-primary); }
      .roi-btn {
        font: 600 calc(var(--ha-font-size-small, 14px)) var(--khroi-font-family);
        color: var(--khroi-secondary); background: var(--khroi-divider);
        border: none; border-radius: 14px; padding: 6px 14px; cursor: pointer;
      }
      .roi-btn:hover { color: var(--khroi-primary); }
      .roi-btn--primary { background: color-mix(in srgb, var(--khroi-accent) 20%, transparent); color: var(--khroi-accent); }
      .roi-btn--danger { background: color-mix(in srgb, var(--khroi-error) 15%, transparent); color: var(--khroi-error); }
      .roi-icon { width: 30px; height: 28px; padding: 0; border-radius: 8px; border: 1px solid var(--khroi-divider); background: var(--khroi-bg); }
      .roi-icon--danger:hover { color: var(--khroi-error); border-color: var(--khroi-error); }
      .roi-form { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--khroi-divider); padding-top: 14px; }
      .roi-form-title { font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; font-size: 11px; color: var(--khroi-secondary); }
      .roi-label { font: 600 calc(var(--ha-font-size-small, 14px)) var(--khroi-font-family); color: var(--khroi-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
      .roi-input {
        font: var(--ha-font-size, 16px) var(--khroi-font-family); color: var(--khroi-primary);
        background: var(--khroi-bg); border: 1px solid var(--khroi-divider);
        border-radius: 8px; padding: 8px 10px; width: 100%; box-sizing: border-box;
      }
      .roi-input:focus { outline: none; border-color: var(--khroi-accent); }
      .roi-input[data-error="true"] { border-color: var(--khroi-error); }
      .roi-check { display: flex; align-items: center; gap: 8px; font-size: calc(var(--ha-font-size-small, 14px)); color: var(--khroi-primary); cursor: pointer; }
      .roi-check input { width: 16px; height: 16px; accent-color: var(--khroi-accent); cursor: pointer; }
      .roi-hint { font-size: calc(var(--ha-font-size-small, 14px)); color: var(--khroi-secondary); }
      .roi-error { color: var(--khroi-error); }
      .roi-actions { display: flex; justify-content: flex-end; gap: 8px; }
      @media (max-width: 600px) {
        .roi-row { flex-wrap: wrap; }
        .roi-row-money { align-items: flex-start; }
      }
    `;
  }
}

if (!customElements.get("kirkhill-wind-roi")) {
  customElements.define("kirkhill-wind-roi", KirkHillWindRoi);
}
