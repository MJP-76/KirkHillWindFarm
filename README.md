# <B>Kirk Hill Wind Farm Home Assistant integration<B>
Excuse me as I am learning the API
<br>- This is a fork of my Ripple integration that I never completed for obvious reasons
<br>- Still in active test&dev

If you like my work:
<br><a href="https://www.buymeacoffee.com/mjp76" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>
<br>Use my [Octopus.Energy 🐙](https://share.octopus.energy/iron-moose-196) referral code. You get £50 credit for joining and I get £50 credit.

# <B>Project updates<B>
- Base HACS installation - completed 29/06/2026
- UI Integration WorkFlow - completed 30/06/2026
- "Site" Wind Farm sensors - Working on 30/06/2026
- "Owner" Wind Farm sensors - Working on 30/06/2026

# <B>Installation<B>
<br>[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
1. Generate your API key @ https://dashboard.kirkhillcoop.org/
2. Add Custom repository:
   - Repository: https://github.com/MJP-76/KirkHillWindFarm
   - Type: Integration
3. Search and install the "Kirk Hill WindFarm" integration
4. Restart Home Assistant
5. Configure through the integration setup UI

# Available sensors
The following sensors are generated from the Kirk Hill Wind Farm API into Home Assistant
<br><B>Working sensors:<B>
<br>-Site sensors<br>
- Active Turbines
- Site Capacity

<br>-Owner sensors
- Owner Capacity Factor
- Owner Generation (7 Day)

<B>WIP Sensors / Nice to have:<B>
<br>-Site sensors<br>
- Wind-Speed
- Turbines Detail
- Site Generation (1 Day)
- Site Generation (7 Day)
- Site Generation (30 Day)

<br>-Owner sensors<br>
- Owner Capacity
- Owner Generation (1 Day)
- Owner Generation (7 Day)
- Owner Generation (30 Day)
