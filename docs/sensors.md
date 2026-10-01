# Sensors

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
- Value (yesterday/today/week/month/ytd/year) [GBP] for owner and site — live-accurate when a price is set; otherwise `£0.00`
  - Value (2025/2024/alltime) [GBP] report `unknown` (`—`) in every case — see the suppression note below
- Owner price (number) [p/kWh] — user-set owner price driving the owner £ figures
- Negotiated price (number) [GBP/MWh] — user-set CfD price driving the site £ figures
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