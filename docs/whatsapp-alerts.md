# WhatsApp alerts

You can get a WhatsApp message whenever a turbine goes down (or comes back
online). This is not built into the integration — it's a small example you set
up in Home Assistant yourself using the entities this integration exposes.

## What you need

- A WhatsApp notification integration for Home Assistant that provides a
  `whatsapp.send_message` service (for example the
  [ha-whatsapp][ha-whatsapp] integration). It exposes `account` and `target`
  parameters you fill in with your own WhatsApp account and the recipient
  number.
- This integration's status entities.

## Entities to watch

Each turbine reports its own status:

| Entity | Description |
|---|---|
| `binary_sensor.turbine_tX_active` | `on` while the turbine is producing, `off` when it is stopped/down |
| `sensor.turbine_tX_state` | Human-readable state text, which includes the reason (e.g. "Turbine stopped: SCADA (bird and bat protection)") |
| `sensor.kirk_hill_wind_farm_active_turbines` | Count of turbines currently running |
| `sensor.kirk_hill_wind_farm_inactive_turbines` | Count of turbines currently down |

Replace `X` with the turbine number (`T1`…`T8`).

## Example — edge-triggered down/recovery alert

The example below only fires when the set of down turbines actually changes, so
it never alerts continuously. It is driven by a derived template sensor that
holds the comma-separated list of down turbines; the automation triggers on
that sensor changing.

```yaml
# packages/whatsapp_turbine_alerts.yaml
template:
  - sensor:
      - name: "Kirk Hill Turbines Down"
        unique_id: kirkhill_turbines_down
        state: >
          {% set ns = namespace(down=[]) %}
          {% for t in ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"] %}
            {% if is_state("binary_sensor.turbine_" ~ t ~ "_active", "off") %}
              {% set ns.down = ns.down + [t|upper] %}
            {% endif %}
          {% endfor %}
          {{ ns.down | sort | join(",") }}
        icon: mdi:wind-turbine

automation:
  - id: kirkhill_turbine_status_alert
    alias: "Kirk Hill - Turbine status WhatsApp alert"
    trigger:
      - platform: state
        entity_id: sensor.kirk_hill_turbines_down
    condition: []
    action:
      - variables:
          previous: "{{ trigger.from_state.state }}"
          current: "{{ trigger.to_state.state }}"
      - variables:
          # Turbines that newly went down
          went_down: >-
            {% set prev_list = previous.split(",") if previous else [] %}
            {% set curr_list = current.split(",") if current else [] %}
            {{ (curr_list | reject("in", prev_list) | list) | sort | join(",") }}
          # Turbines that newly recovered
          recovered: >-
            {% set prev_list = previous.split(",") if previous else [] %}
            {% set curr_list = current.split(",") if current else [] %}
            {{ (prev_list | reject("in", curr_list) | list) | sort | join(",") }}
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ went_down != '' }}"
            sequence:
              - variables:
                  down_lines: >-
                    {% set ns = namespace(rows=[]) %}
                    {% for t in ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"] %}
                      {% if is_state("binary_sensor.turbine_" ~ t ~ "_active", "off") %}
                        {% set ns.rows = ns.rows + [t|upper ~ ": " ~ states("sensor.turbine_" ~ t ~ "_state")] %}
                      {% endif %}
                    {% endfor %}
                    {{ ns.rows | join("\n") }}
              - service: whatsapp.send_message
                data:
                  account: "YOUR_WHATSAPP_ACCOUNT"
                  target: "RECIPIENT_NUMBER"
                  message: >-
                    ⚠️ *Kirk Hill: turbines down*

                    {{ down_lines }}
          - conditions:
              - condition: template
                value_template: "{{ recovered != '' }}"
            sequence:
              - service: whatsapp.send_message
                data:
                  account: "YOUR_WHATSAPP_ACCOUNT"
                  target: "RECIPIENT_NUMBER"
                  message: >-
                    ✅ *Kirk Hill: turbine(s) back online*

                    {{ recovered.replace(",", ", ") }}
    mode: single
```

## Notes

- Replace `YOUR_WHATSAPP_ACCOUNT` and `RECIPIENT_NUMBER` with your own account
  and recipient for `whatsapp.send_message` (or use `input_text` helpers).
- Turbine status data refreshes roughly every 10 minutes, so alerts land within
  that window. Multiple turbines changing in the same poll produce one combined
  message, not one per turbine.
- Because the automation is edge-triggered on a change to the set of down
  turbines, it sends at most one message per status change — never on a repeat
  schedule.

[ha-whatsapp]: https://github.com/faserf/ha-whatsapp