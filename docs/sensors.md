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
- **Value (yesterday/today/week/month/ytd/year) [GBP] — DISABLED from v4.16.1.** The entities exist but are disabled in the entity registry; the card still draws the column and shows `—` in every cell. Previously `live generation × configured price`, `£0.00` when no price was set
  - Value (2025/2024/alltime) [GBP] report `unknown` (`—`) in every case — see the suppression note below
- **Member savings value [GBP] — DISABLED from v4.16.1.** The board's capacity-based payment: `owned watts × rate (p/W) ÷ 100` (2,559.465 W × 21p = **£537.49** for Feb 2025–Jun 2026). The card line is drawn but reads `—`; its attributes are `owned_watts`, `rate_pence_per_watt`, `projection_basis` and `data_stale`
- **Owner price (number) [p/kWh] — DISABLED from v4.16.1**, input `0.0`
- **Owner rate (number) [p/W] — DISABLED from v4.16.1**, input `0.0`. **This is what the Owner pill on the card edits** (was the declared member savings rate, e.g. 21p/W for Feb 2025–Jun 2026)
- **Negotiated price (number) [GBP/MWh] — DISABLED from v4.16.1**, input `0.0`

Re-enable any of them with `hab entity enable <entity_id>` — nothing was deleted.
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

!!! warning "All 22 earnings entities are currently disabled"
    **2026-10-09** — the 19 value/savings sensors and the 3 price/rate `number`
    entities are **disabled in the entity registry** and every input is `0.0`.
    The card still draws the `Value (£)` column, the pills and the savings line
    — deliberately kept as a reminder — but **nothing is populated or
    calculated**, so every money cell reads `—`. Re-enable with
    `hab entity enable <entity_id>` to bring figures back. See
    [Development decisions](development/decisions.md).

Financial £ values are **live-accurate when a price is set**. Two independent
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

The period never enters the calculation: 1,000 W at 21p/W is £210 for whatever
span the board declares, so 2,559.465 W is £537.49 for Feb 2025–Jun 2026.
There is deliberately **no accrual** — the board reviews its finances and
declares a payment when it declares one, so no effective earning rate is
knowable until then, which is exactly why the web dashboard shows no ongoing
earnings. The board's "15p per watt per 12 months" is an equivalence for that
same declaration, not a daily or monthly rate to divide out. Update
`Owner rate (p/W)` each time a payment is declared; until then the sensor
reads `—`. This figure does not depend on generation, so it is unaffected by
wind, and it is **not** shown on the SCADA card.

The **All-time** value is an exception: it reports `unknown` (the SCADA card
shows `—`) in every case, because the API records energy only — never money —
and applying today's price to history would silently revalue it whenever the
price is edited. The **past-year (2025, 2024)** value sensors follow the same
rule. All are sensors only — the past-year figures are not shown on the SCADA
card. This stands until the CfD strike price history is confirmed (the price
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