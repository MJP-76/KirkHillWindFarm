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
- Generation (alltime) [kWh] for owner and site
- Generation source attribute marks these entities as `api_dynamic`
- Value (yesterday/today/week/month/ytd/year/alltime) [GBP] for owner and site — live-accurate when a negotiated price is set; otherwise the projected (non-dynamic) model applies
  - For the projected (fallback) model, the all-time start date is derived from the API all-time timeframe when available
- Negotiated price (number) [GBP/MWh] — user-set path to live-accurate £ values (see note below)
- Open-Meteo forecast wind speed (next hour / next 3h avg / next 24h avg) [m/s] (forecast-only, non-authoritative)
- Wind speed [m/s]
- Active turbines
- Inactive turbines
- Alarm (binary sensor) — on when any turbine is in an actual thermal or electrical fault state

Timeframe generation entities keep a stable raw **kWh** state for reliability in
Home Assistant. The generated dashboard formats those values for display with
automatic unit scaling (**kWh**, **MWh**, **GWh**, **TWh**, **PWh**, **EWh**) and
rounds them to **2 decimal places**.

Financial £ values are **live-accurate when a negotiated price is set**: the
`number.kirk_hill_wind_farm_negotiated_price_gbp_mwh` entity (0.0 by default)
holds the negotiated CfD price in GBP/MWh. When it is >0, each timeframe's value
is `actual generation kWh ÷ 1000 × price`; when it is 0 (or live generation is
unavailable, e.g. before the first successful API fetch) the values fall back to
the projected model based on the configured annual figures.

## Per turbine device (`Turbine T1` … `Turbine T8`)

- Power (owner) [kW]
- Power (site) [kW]
- Capacity factor (owner) [%]
- Capacity factor (site) [%]
- Wind speed (m/s)
- State text
- Active (binary sensor)
- Generation today (site) [kWh]
- Generation all-time (site) [kWh]
- Rotor speed [rpm]
- Today's generation share attribute (`share_percent`)

For turbine down/recovery notifications built on these entities, see
[WhatsApp alerts](whatsapp-alerts.md).