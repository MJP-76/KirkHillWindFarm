# Kirkhill Coop Wind Farm Integration
A Home Assistant integration for monitoring wind farm generation, turbine status, and energy data from the Kirkhill Coop dashboard API.

Excuse me as I am learning the API
<br>- This is a fork of my Ripple integration that I never completed for obvious reasons
<br>- Still in active test&dev

If you like my work:
<br><a href="https://www.buymeacoffee.com/mjp76" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>
<br>Use my [Octopus.Energy �](https://share.octopus.energy/iron-moose-196) referral code. You get £50 credit for joining and I get £50 credit.

## Features
- Live wind farm power monitoring
- Wind speed tracking
- Capacity factor sensor
- Per-turbine energy sensors (auto-discovered)
- Energy Dashboard support
- Scope switching (owner/site)

## Installation
<br>[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

You will need:
- API key from Kirkhill dashboard

1. Add this repository to HACS (Custom Repositories)
2. Install "Kirkhill Coop Wind Farm"
3. Restart Home Assistant
4. Add integration via UI


## Sensors

- Power (kW)
- Wind speed (m/s)
- Capacity factor (%)
- Total energy (kWh)
- Turbine energy sensors (T1–T8)

## Energy Dashboard Support

This integration supports:
- `device_class: energy`
- `state_class: total_increasing`
- Full long-term statistics

## License

MIT
