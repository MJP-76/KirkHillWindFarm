# <B>Kirk Hill Wind Farm Home Assistant integration<B>
Note:
<br>- This is a fork of my Ripple integration that I never compleated for obvious reasons
<br>- Still in active test&dev with minimal sensors but many updates ;)

Excuse me as I am learning the API - If you like my project, why not buy_me_a_coffee/mjp-76

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

Use my [Octopus.Energy 🐙](https://share.octopus.energy/iron-moose-196) referral code. You get £50 credit for joining and I get £50 credit.
# Available sensors
The following sensors are generated from the Kirk Hill Wind Farm API into Home Assistant

<B>Working sensors<B>
<br>Site sensors<br>
- Kirk Hill Active Turbines
- Kirk Hill Site Capacity

<br>Owner sensors<br>
- Kirk Hill Capacity Factor
- Kirk Hill Site Capacity
- Kirk Hill Total Generation (7 Day)

<B>WIP Sensors<B>
<br>Site sensors<br>
- Kirk Hill Generation - Site
- Kirk Hill Wind-Speed - Site
- Kirk Hill turbines - Detailed info

<br>Owner sensors<br>


# <B>Pre-reqs<B>
You will require your API key from https://dashboard.kirkhillcoop.org/

# <B>Installation<B>
<B>HACS<B>
1. Add https://github.com/MJP-76/KirkHillWindFarm as a "Custom Repository" in HACS
2. Install the integration in HACS
3. Restart Home Assistant

# Post installation
Configure through the integration setup UI

# <B>Project updates<B>
# Completed
- Base HACS installation - 29/06/2026
- UI Integration WorkFlow - 30/06/2026
- "Whole" Wind Farm sensors - 30/06/2026
