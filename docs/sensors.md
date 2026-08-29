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
- Projected value (yesterday/today/week/month/ytd/year/alltime) [GBP] for owner and site is non-dynamic
  - For **all-time projected value**, the projection window start date is derived from the API all-time timeframe when available
- Open-Meteo forecast wind speed (next hour / next 3h avg / next 24h avg) [m/s] (forecast-only, non-authoritative)
- Wind speed [m/s]
- Active turbines
- Inactive turbines
- Alarm (binary sensor) — on when any turbine is in an actual thermal or electrical fault state

Timeframe generation entities keep a stable raw **kWh** state for reliability in
Home Assistant. The generated dashboard formats those values for display with
automatic unit scaling (**kWh**, **MWh**, **GWh**, **TWh**, **PWh**, **EWh**) and
rounds them to **2 decimal places**. Financial values are separate **projected**
figures and are not calculated from live generation.

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