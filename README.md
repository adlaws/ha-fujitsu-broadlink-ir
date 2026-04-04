# Broadlink IR Control of Fujitsu AC — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Home Assistant custom integration that controls a Fujitsu air conditioner
through a Broadlink IR blaster. Commands are built from the decoded Fujitsu
IR protocol, so no pre-recorded codes are required.

This integration avoids having to purchase and install a
[wifi module](https://www.fujitsugeneral.com.au/anywair) in the airconditioner
by leveraging the same IR protocol used by the remote control.

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
| Swing modes\* | Off, Vertical, Horizontal, Both |
| Outside-unit quiet | On / Off (separate switch entity) |
| Off timer | Turn off after 1–720 minutes (entity service) |
| On timer | Turn on after 1–720 minutes (entity service) |
| Sleep timer | Gradual temperature ramp then off (entity service) |
| Cancel timer | Clear any active timer (entity service) |

> *\* Note that not all swing modes are supported on all models*

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

**Note that not all models support all swing modes.**

### Outside-Unit Quiet Mode

The outside-unit quiet mode is exposed as a separate `switch` entity
(e.g. `switch.lounge_ac_outside_quiet`).  When enabled the outdoor
compressor runs at reduced noise levels.

Toggling the switch while the AC is on sends a full state IR command
immediately.  Toggling it while the AC is off stores the setting so it
will be included in the next power-on command.

### Timers

The integration exposes four entity services for controlling the AC's
built-in timers:

| Service | Description |
|---------|-------------|
| `set_off_timer` | Turn the AC off after a delay (1–720 min) |
| `set_on_timer` | Turn the AC on after a delay, with optional mode/temp/fan/swing |
| `set_sleep_timer` | Gradual temperature adjustment then power off |
| `cancel_timer` | Clear any active timer |

Timers accept either `minutes` (integer, 1–720) or `time` (a wall-clock
time string like `"22:30"` — the integration calculates the offset
automatically).

```yaml
service: fujitsu_ac_ir.set_off_timer
target:
    entity_id: climate.lounge_ac
data:
    minutes: 120
```

```yaml
service: fujitsu_ac_ir.set_on_timer
target:
    entity_id: climate.lounge_ac
data:
    time: "06:00"
    mode: cool
    temperature: 24
```

A simple button card to turn off the AC in 30 minutes:

```yaml
type: button
name: "AC Off in 30 min"
icon: mdi:timer-outline
tap_action:
    action: perform-action
    perform_action: fujitsu_ac_ir.set_off_timer
    target:
        entity_id: climate.lounge_ac
    data:
        minutes: 30
```

Turn the heater on at 5 AM to warm up to 21°C:

```yaml
type: button
name: "Heat to 21°C at 5:00 am"
icon: mdi:radiator
tap_action:
    action: perform-action
    perform_action: fujitsu_ac_ir.set_on_timer
    target:
        entity_id: climate.lounge_ac
    data:
        time: "05:00"
        mode: heat
        temperature: 21
```

See the [Integration Documentation](docs/integration.md#timers) for full
details, all service parameters, and automation examples.

## Limitations

Because of the natire of this integration, there is no way to *query* the
current state of the airconditioner.

This means that, for example, if you use the *remote* to turn on the
airconditioner, change the temperature or anything else, these changes to the
airconditioner's operation will known about by the integration.

This doesn't affect the operation of the integration however - you can safely
use the remote and this integration at the same time.

If you require a deeper level of integration that allows you to be aware of the
current operational details of the airconditioner, you will need to purchase an
[appropriate wifi module](https://www.fujitsugeneral.com.au/anywair) for
your airconditioner and use an alternate integration such as the
[Fujitsu Airstage Home Assistant component](https://github.com/danielkaldheim/ha_airstage).

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

### What About Custom Button Cards?

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
| `services.yaml` | Entity service definitions (timer services) |
| `switch.py` | `FujitsuACOutsideQuietSwitch` entity for outside-unit quiet mode |
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

This was confirmed by examining the
[IRremoteESP8266](https://github.com/crankyoldgit/IRremoteESP8266) project,
the most comprehensive open-source IR protocol library available. Its
`IRFujitsuAC` class implements encode/decode for the full Fujitsu protocol
family but provides no `setClock` or `setCurrentTime` method. By contrast,
other manufacturers (Daikin, Mitsubishi, Panasonic, Haier, and others) do
expose clock-setting commands, which IRremoteESP8266 supports. The absence
in the Fujitsu implementation is a limitation of the protocol itself, not of
this integration.

If your unit displays the wrong time, it must be set manually using the
physical remote control.

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
