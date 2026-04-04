# Fujitsu AC IR — Home Assistant Integration

A Home Assistant custom integration that controls a Fujitsu air conditioner
through a Broadlink IR blaster. Commands are built from the decoded Fujitsu
IR protocol, so no pre-recorded codes are required.

## Prerequisites

* A Broadlink IR blaster (RM4 Mini, RM4 Pro, RM Pro+, or similar) already
  configured in Home Assistant via the
  [Broadlink integration](https://www.home-assistant.io/integrations/broadlink/)
* A Fujitsu air conditioner with an AR-RWE3E remote (or compatible
  ARREW4E-family model)
* Home Assistant 2024.1 or later

## Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Select **Integrations**.
3. Click the three-dot menu (top right) and choose **Custom repositories**.
4. Enter `https://github.com/adlaws/ha-fujitsu-broadlink-ir` as the repository URL and
   select **Integration** as the category.
5. Click **Add**, then find **Fujitsu AC IR (Broadlink)** in the list and
   click **Download**.
6. Restart Home Assistant.

### Manual Installation

1. Copy the `custom_components/fujitsu_ac_ir/` directory into your Home
   Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

### Configuration

1. Navigate to **Settings → Devices & Services → Add Integration**.
2. Search for **Fujitsu AC IR** and select it.
3. Enter a name for the air conditioner (e.g. "Lounge AC").
4. Select the Broadlink remote entity that will transmit the IR commands.

After completing the flow a `climate` entity and an **Outside Quiet**
`switch` entity appear under the name you chose.

## Supported Features

| Feature | Values |
|---------|--------|
| HVAC modes | Off, Auto, Cool, Heat, Dry, Fan Only |
| Temperature range | 16 °C – 30 °C in 0.5 °C steps |
| Fan speeds | Auto, High, Medium, Low, Quiet |
| Swing modes | Off, Vertical, Horizontal, Both |
| Outside-unit quiet | On / Off (separate switch entity) |
| Off timer | Turn off after 1–720 minutes (or at a specific time) |
| On timer | Turn on after 1–720 minutes with specified settings |
| Sleep timer | Gradual “comfort wind-down” shut-off after 1–720 minutes |
| Cancel timer | Cancel any active timer |

### HVAC Modes

* **Off** — sends a short 7-byte power-off command
* **Auto** — the AC selects heating or cooling automatically
* **Cool** — cooling mode
* **Heat** — heating mode
* **Dry** — dehumidification mode
* **Fan Only** — fan runs without compressor

### Fan Speed

Standard Home Assistant fan speeds (Auto, High, Medium, Low) are mapped
directly to the Fujitsu protocol values. An additional custom fan mode
`quiet` is exposed, corresponding to the Fujitsu Quiet setting
(protocol fan value `0x04`).

### Swing

Swing modes map one-to-one to the protocol:

* `off` — louvres hold position
* `vertical` — vertical oscillation
* `horizontal` — horizontal oscillation
* `both` — simultaneous vertical and horizontal oscillation

### Outside-Unit Quiet Mode

The outside-unit quiet mode is exposed as a separate `switch` entity
(e.g. `switch.lounge_ac_outside_quiet`).  When enabled the outdoor
compressor runs at reduced noise levels.

Toggling the switch while the AC is on sends a full state IR command
immediately.  Toggling it while the AC is off stores the setting so it
will be included in the next power-on command.

### Timers

Four entity services are registered on the climate entity for timer
control.  Each accepts either a **minutes** parameter (duration from
now) or a **time** parameter (wall-clock time, offset computed
automatically).

#### `fujitsu_ac_ir.set_off_timer`

Turn the AC off after a duration.  The AC continues running with its
current settings until the timer expires.

```yaml
service: fujitsu_ac_ir.set_off_timer
target:
    entity_id: climate.lounge_ac
data:
    minutes: 30
```

Or using a wall-clock time:

```yaml
service: fujitsu_ac_ir.set_off_timer
target:
    entity_id: climate.lounge_ac
data:
    time: "23:00"
```

#### `fujitsu_ac_ir.set_on_timer`

Turn the AC on after a duration.  You can optionally specify the
mode, temperature, fan speed, and swing it should use:

```yaml
service: fujitsu_ac_ir.set_on_timer
target:
    entity_id: climate.lounge_ac
data:
    time: "06:00"
    mode: cool
    temperature: 24
    fan_mode: auto
    swing_mode: horizontal
```

| Parameter | Valid values |
|-----------|-------------|
| `mode` | `auto`, `cool`, `heat`, `dry`, `fan_only` |
| `fan_mode` | `auto`, `high`, `medium`, `low`, `quiet` |
| `swing_mode` | `off`, `vertical`, `horizontal`, `both` |

If mode/temperature/fan/swing are omitted, the current entity settings
are used.

#### `fujitsu_ac_ir.set_sleep_timer`

Activate the sleep timer.  This is similar to the off timer but the AC
unit manages a gradual comfort wind-down (the exact behaviour depends on
the AC model).

```yaml
service: fujitsu_ac_ir.set_sleep_timer
target:
    entity_id: climate.lounge_ac
data:
    minutes: 120
```

#### `fujitsu_ac_ir.cancel_timer`

Cancel any active timer (on, off, or sleep).  Sends the current state
with the timer cleared.

```yaml
service: fujitsu_ac_ir.cancel_timer
target:
    entity_id: climate.lounge_ac
```

#### Timer Limits

* Maximum duration: **720 minutes** (12 hours).
* When using the *time* parameter, if the target time is in the past
  (today), the timer wraps to the same time tomorrow.
* Only one timer type can be active at a time (setting a new timer
  replaces any existing one).
* The AC unit itself has no internal clock.  The timer value is a
  **duration from now** encoded in the IR command.

### Automation Examples

Turn the AC off at 11 PM every night:

```yaml
automation:
    - alias: "AC off at 11pm"
      trigger:
          - platform: time
            at: "22:30:00"
      action:
          - service: fujitsu_ac_ir.set_off_timer
            target:
                entity_id: climate.lounge_ac
            data:
                minutes: 30
```

Pre-cool the bedroom before wake-up:

```yaml
automation:
    - alias: "Pre-cool bedroom"
      trigger:
          - platform: time
            at: "05:30:00"
      action:
          - service: fujitsu_ac_ir.set_on_timer
            target:
                entity_id: climate.bedroom_ac
            data:
                minutes: 30
                mode: cool
                temperature: 23
                fan_mode: quiet
```

## How Commands Are Sent

Every state change (mode, temperature, fan, swing) assembles a **complete
16-byte IR command** encoding the full desired AC state — exactly as the
physical remote would. The integration then calls the
`remote.send_command` service on the configured Broadlink entity, passing
the base64-encoded Broadlink timing data.

This means the AC always receives an unambiguous, self-contained command
and the integration does not need to track incremental changes.

## Lovelace Dashboard Card

The integration creates a standard `climate` entity, so the built-in
**Thermostat** card works out of the box with no extra configuration.
It provides temperature up/down controls, HVAC mode selection, fan speed,
and swing mode — all wired to the correct IR commands automatically.

### Minimal Thermostat Card

```yaml
type: thermostat
entity: climate.lounge_ac
```

Replace `climate.lounge_ac` with the entity ID created during setup.

### Customised Climate Card

For more control over the layout you can use a `climate-hvac-modes` card
or override which features are shown:

```yaml
type: thermostat
entity: climate.lounge_ac
features:
    - type: climate-hvac-modes
      hvac_modes:
          - "off"
          - auto
          - cool
          - heat
          - dry
          - fan_only
    - type: climate-fan-modes
      fan_modes:
          - auto
          - high
          - medium
          - low
          - quiet
    - type: climate-swing-modes
      swing_modes:
          - "off"
          - vertical
          - horizontal
          - both
```

### What About Custom Button Cards

Because this integration implements the full `ClimateEntity` API, you do
**not** need a grid of custom buttons or an `input_number` helper to
track temperature. The thermostat card already handles:

| Control | How It Appears |
|---------|----------------|
| Power on/off | Selecting "Off" HVAC mode sends the 7-byte power-off IR command |
| Temperature | Built-in up/down arrows adjust in 0.5 °C steps |
| HVAC mode | Icon row — auto, cool, heat, dry, fan-only |
| Fan speed | Dropdown — auto, high, medium, low, quiet |
| Swing | Dropdown — off, vertical, horizontal, both |
| Outside quiet | Separate switch entity (see below) |

### Outside Quiet Switch

The outside-unit quiet mode is controlled by a separate `switch` entity.
You can add it to your dashboard alongside the thermostat card:

```yaml
type: entities
entities:
    - entity: switch.lounge_ac_outside_quiet
      name: Outside Unit Quiet
```

Or combine both in a vertical stack:

```yaml
type: vertical-stack
cards:
    - type: thermostat
      entity: climate.lounge_ac
    - type: entities
      entities:
          - entity: switch.lounge_ac_outside_quiet
            name: Outside Unit Quiet
```

## Troubleshooting

### The AC does not respond to commands

* Verify the Broadlink remote entity works by testing a simple IR command
  from the Home Assistant developer tools.
* Ensure the IR blaster has line-of-sight to the AC's receiver.
* Check the Home Assistant log for errors from the `fujitsu_ac_ir`
  component.

### Temperature is offset by a few degrees

Make sure your Fujitsu model uses the AR-RWE3E / ARREW4E protocol
(protocol byte `0x31`). Models that use the older `0x30` protocol have a
different temperature encoding formula. See the
[project README](../README.md) for details on adapting to other models.

### Quiet fan mode does not appear in the UI

The `quiet` fan mode is a custom string that may not render the same way
as the built-in fan modes in all frontends. It should appear in the fan
speed dropdown of the standard climate card.

## File Reference

| File | Purpose |
|------|---------|
| `__init__.py` | Integration entry point — shared data store and IR send helper |
| `climate.py` | `FujitsuACClimate` entity mapping HA climate API to IR commands |
| `config_flow.py` | UI configuration flow — selects the Broadlink remote entity |
| `const.py` | Protocol constants and configuration keys |
| `ir_codec.py` | Self-contained IR encoder/decoder (`FujitsuACCodec`, `FujitsuACState`) |
| `switch.py` | `FujitsuACOutsideQuietSwitch` entity for outside-unit quiet mode |
| `services.yaml` | Timer service definitions (off, on, sleep, cancel) |
| `manifest.json` | Integration metadata (domain, version, dependencies) |
| `strings.json` | Default UI strings |
| `translations/en.json` | English translations for the configuration flow |

## Other Notes

### Clock / Time Setting

The Fujitsu IR protocol does **not** support setting the air conditioner's
internal clock via infrared. Bytes 11–13 of a 16-byte command frame carry
*relative* on/off/sleep timer values that the remote embeds at transmission
time — they are not an absolute clock and there is no separate "set clock"
command in the protocol.

This integration **does** support the relative timer functionality.  Timer
values represent a **duration from now** in minutes (1–720).  When you use
the *time* parameter in a timer service call, Home Assistant computes the
offset from the current wall-clock time automatically.

If your unit displays the wrong time on its screen, it must be set manually
using the physical remote control.

### Acknowledgements

This integration was developed with the help of the following projects:

* **[IRremoteESP8266](https://github.com/crankyoldgit/IRremoteESP8266)** —
  An extensive Arduino/ESP8266 library for sending and receiving infrared
  signals. Its Fujitsu AC protocol implementation
  ([`ir_Fujitsu.h`](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Fujitsu.h) /
  [`ir_Fujitsu.cpp`](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Fujitsu.cpp))
  was invaluable for understanding the byte-level command structure,
  checksum algorithm, and protocol variants.
* **[python-broadlink](https://github.com/mjg59/python-broadlink)** —
  Python library for controlling Broadlink devices, used by the Home
  Assistant Broadlink integration that this component builds on.

## Removing the Integration

1. Navigate to **Settings → Devices & Services**.
2. Find the **Fujitsu AC IR** entry and select it.
3. Click the three-dot menu and choose **Delete**.
4. If installed via HACS, open HACS, find the integration, and click
   **Remove**. If installed manually, delete the
   `custom_components/fujitsu_ac_ir/` directory.
5. Restart Home Assistant.
