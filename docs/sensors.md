# Sensors

!!! note "This list tracks an API that changes"

    Everything below reflects what the upstream API returns **today**. The
    integration depends on an API it does not control, and that API has
    already changed under it — a field renamed, a value enum changed, a
    capacity pair replaced, and sensors added and removed along the way. If an
    entity on this list is missing or reads `unknown`, see
    [The Kirk Hill API](api.md) for what changed upstream and
    [the changelog](changelog.md) for the release that followed it.

## Farm hub device

- Power (owner) [kW]
- Power (site) [MW]
- Capacity factor (owner) [%]
- Capacity factor (site) [%]
- Generation (yesterday) [kWh] for owner and site
- Generation (today) [kWh] for owner and site
- Generation (week) [kWh] for owner and site
- Generation (month) [kWh] for owner and site
- Generation (ytd) [kWh] for owner and site
- Generation (year) [kWh] for owner and site
- Generation (2025) / Generation (2024) [kWh] for owner and site — past calendar years, fetched with `range=YYYY`. These are **sensors only** (not shown on the SCADA card). More years appear automatically as time passes.
- Generation (alltime) [kWh] for owner and site — **calculated as the sum of all the year figures**: `2024 + 2025 + … + the current year to date`, including any future years. The `sum_of_years_kwh` attribute lists the per-year components.
- Generation source attribute marks these entities as `api_dynamic` (`sum_of_years` on the All time entity)
- **Value (yesterday/today/week/month/ytd/year) [GBP] — DISABLED from v4.16.1.** The entities exist but are disabled in the entity registry, and **no card draws a £ column any more** (removed 2026-10-21). Previously `live generation × configured price`, `£0.00` when no price was set
  - Value (2025/2024/alltime) [GBP] report `unknown` in every case — see the suppression note below
- **Member savings value [GBP] — DISABLED from v4.16.1.** The board's capacity-based payment: `owned watts × rate (p/W) ÷ 100` — for example, at a declared 20p/W, 1,000 owned watts reads **£200**. Its attributes are `owned_watts`, `rate_pence_per_watt`, `projection_basis` and `data_stale`. **Nothing reads it**: no card draws a member-savings line any more
- **Payment ledger [GBP] — enabled; the source of every figure in the Return on investment panel.** One line item per period the board declared a p/W rate for, stored in Home Assistant's storage (one file per config entry, never `entry.options`). State is the **all-periods total** (`total_gbp`), `Σ watts × rate ÷ 100`, and reads **`unknown` while no period has been declared — never `£0.00`**. Periods are whole months — `period_start` lands on the 1st and `period_end` on the last day of its month. Attributes: `records` (each `{id, period_start, period_end, rate_p_per_w, capacity_watts, announced_on, note, source, capital_gbp, interest_gbp, value_gbp, roi_pct}`), `record_count`, `total_gbp`, `board_total_gbp`, `self_total_gbp`, `capital_total_gbp`, `interest_total_gbp`, `invested_gbp`, `total_roi_pct`, `annual_rate_p_per_w`, `lifespan_years`, `annual_gbp`, `lifespan_gbp`, `share_value_gbp_per_w`, `lifetime_estimate_gbp`, `lifetime_roi_pct`, `lifetime_remaining_years`, `latest_rate_p_per_w`, `latest_board_rate_p_per_w`, `latest_period_start`, `latest_period_end`, `current_gbp`, `current_basis` (`declared` · `awaiting_next_declaration` · `no_entries`), `current_source` (`board` · `self`), `current_year_gbp` and `year_totals_gbp`. `current_gbp` is the *current* period's figure and stays out of `total_gbp`; while the period is undeclared it is **`None` with `current_basis=awaiting_next_declaration`** — no estimate is derived until the board declares the period covering today (a declaration brings the rate and the capital/interest split together). `share_value_gbp_per_w` is `invested ÷ capacity_watts`: derived, display-only, `None` until both halves exist. `lifetime_estimate_gbp` / `lifetime_roi_pct` / `lifetime_remaining_years` are the labelled lifetime estimate — the board's actuals plus the years left at `annual_rate_p_per_w` (whatever the member last set, never a constant in code), elapsed counted fractionally from the first board period — counted by no total and no period, and `total_roi_pct` above stays the factual return. `roi_pct` is `value ÷ invested × 100` and reads `None` until an invested amount is entered — never `0%`. Writable only through the `kirkhill_wind.add/update/remove_payment_record`, `set_invested_amount` and `set_projection` services — or by editing the shipped `board_announcements.yaml`, whose entries are upserted into the ledger as board records on setup unless Options → **Board figures source** is set to *Manual entry only*. The projection attributes (`annual_rate_p_per_w`, `lifespan_years`, `annual_gbp`, `lifespan_gbp`) are a labelled assumption — normally the board's own published annual equivalent — and fill no period, feed no total and change no ROI. Always available — it reads local storage, not the API
- **Owner price (number) [p/kWh] — DISABLED from v4.16.1**, input `0.0`
- **Owner rate (number) [p/W] — DISABLED from v4.16.1**, input `0.0`. Superseded by the ledger's per-period rates; no card reads it
- **Negotiated price (number) [GBP/MWh] — DISABLED from v4.16.1**, input `0.0`

Re-enable any of them with `hab entity enable <entity_id>` — nothing was deleted.

Since config entry **v11**, an upgrade purges all three inputs from
`entry.options` whatever they hold, so no monetary value is stored at all — the
defaults in `settings.SETTING_DEFAULTS` answer instead.

- Open-Meteo forecast wind speed (next hour / next 3h avg / next 24h avg) [m/s] (forecast-only, non-authoritative)
- Wind speed [m/s]
- Active turbines
- Inactive turbines
- Alarm (binary sensor) — on when any turbine is in an actual thermal or electrical fault state
- API Status (binary sensor) — on when the Kirk Hill API last responded normally, off when the last fetch failed
- Data complete (binary sensor) — on when every turbine has current power, wind speed, and state data available
- Data generated at (timestamp) — when the API response was generated (data freshness)
- Unknown turbines — count of turbines with no imported state
- Latest import status — status of the latest data import (e.g. `completed`); includes `latest_generation_interval_end` as an attribute
- Owner share [%] — your share of the farm's capacity, derived from the API generation ratio

Timeframe generation entities keep a stable raw **kWh** state for reliability in
Home Assistant. The generated dashboard formats those values for display with
automatic unit scaling (**kWh**, **MWh**, **GWh**, **TWh**, **PWh**, **EWh**) and
rounds them to **2 decimal places**.

!!! note "Financial figures: disabled, and off the Owner and Site panels"
    **2026-10-09** — the 19 value/savings sensors and the 3 price/rate `number`
    entities were **disabled** with their inputs at `0.0`, and nothing is
    calculated from them. Re-enable one with `hab entity enable <entity_id>` if
    you want it for something else.

    **2026-10-21 — the panels carry generation only.** The `Value (£)` column,
    the `£/h` cells, the member-savings line and both price pills were removed
    from the Owner and Site panels. Every financial figure comes from the
    **Payment ledger** sensor above and is drawn in the **Return on
    investment** panel — the top panel of the right column — with the ledger
    and both
    forms behind a click; the disabled entities stay disabled and unread.

**As sensors** — nothing reads them any more — the `Value (…)`
entities are **live-accurate when a price is set**. Two independent
price entities hold the prices, both `0.0` by default:
`number.kirk_hill_wind_farm_owner_price_p_kwh` (Owner price in p/kWh — enter `6`
for 6 pence) drives the owner figures; and
`number.kirk_hill_wind_farm_negotiated_price_gbp_mwh` (Site/CfD price in £/MWh)
drives the site figures. When a price is >0, each timeframe's owner value is
`generation kWh × price(p/kWh) ÷ 100` and each site value is
`generation kWh ÷ 1000 × price(£/MWh)`; when it is 0 (or live generation is
unavailable, e.g. before the first successful API fetch) the sensors read
`£0.00` — there is no projected-model fallback.

**Two different money questions.** The `Value (…)` sensors price your
*generation* (`kWh × price`) — the model the co-op itself moved away from when
it stopped calculating member returns from kWh. Members are now paid for the
watts they *own*, so **Member savings value** uses that instead:
`owned watts × rate ÷ 100`, fed by `capacity_watts` from the API — the same
number the web dashboard multiplies out.

The period never enters the calculation: 1,000 W at a declared 20p/W reads
£200 for whatever span the board declares.
There is deliberately **no accrual** — the board reviews its finances and
declares a payment when it declares one, so no effective earning rate is
knowable until then, which is exactly why the web dashboard shows no ongoing
earnings. Any yearly figure the board quotes is an equivalence for that
same declaration, not a daily or monthly rate to divide out. Update
`Owner rate (p/W)` each time a payment is declared; until then the sensor
reads `—`. This figure does not depend on generation, so it is unaffected by
wind, and it is **not** shown on the SCADA card.

The **All-time** value is an exception: it reports `unknown` in every case,
because the API records energy only — never money — and applying today's price
to history would silently revalue it whenever the price is edited. The
**past-year (2025, 2024)** value sensors follow the same rule. All are sensors
only — no card shows a value cell at all any more. This stands until the CfD
strike price history is confirmed (the price
value(s), whether the CfD has ever changed, and its contract length). The kWh
energy figures are unaffected. Once the history is known, each year gets its own
price — the per-year sensors are the foundation for the multi-CfD price
schedule. See [Development decisions](development/decisions.md).

## Per turbine device (`Turbine T1` … `Turbine T8`)

- Power (owner) [kW]
- Power (site) [kW]
- Capacity factor (owner) [%]
- Capacity factor (site) [%]
- Wind speed (m/s)
- State
- Active (binary sensor)
- Generation today (site) [kWh]
- Generation all-time (site) [kWh]
- Rotor speed [rpm] — includes `sampled_at` attribute (when the rotor speed was last measured)
- Today's generation share attribute (`share_percent`)

For turbine down/recovery notifications built on these entities, see
[WhatsApp alerts](whatsapp-alerts.md).