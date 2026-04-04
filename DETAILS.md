# Fujitsu AC IR Control

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Control a Fujitsu air conditioner via a Broadlink IR blaster by assembling
protocol-correct IR commands on the fly — no pre-recorded codes needed.

## Overview

Fujitsu AC remotes encode the **entire AC state** in every IR transmission —
not just the button that was pressed. This project reverse-engineers the
Fujitsu IR protocol (AR-RWE3E / ARREW4E family, protocol byte `0x31`)
and provides:

* A standalone Python library for encoding and decoding Fujitsu IR commands
* A developer tool for analysing recorded Broadlink IR codes
* A Home Assistant custom integration (`climate` platform) that drives the
  AC through a Broadlink IR blaster, including on/off/sleep timer support

See the [Integration Documentation](docs/integration.md) for detailed
configuration and usage within Home Assistant.

## Installation via HACS

1. Open HACS in your Home Assistant instance.
2. Select **Integrations**.
3. Click the three-dot menu (top right) and choose **Custom repositories**.
4. Enter `https://github.com/adlaws/ha-fujitsu` as the repository URL and
   select **Integration** as the category.
5. Click **Add**, then find **Fujitsu AC IR (Broadlink)** in the list and
   click **Download**.
6. Restart Home Assistant.
7. Go to **Settings → Devices & Services → Add Integration** and search
   for **Fujitsu AC IR**.

## Repository Layout

```text
ha-fujitsu/
├── custom_components/fujitsu_ac_ir/   Home Assistant integration
│   ├── __init__.py
│   ├── brand/                         Brand assets (icon, logo)
│   ├── climate.py                     Climate entity
│   ├── config_flow.py                 UI configuration flow
│   ├── const.py                       Integration constants
│   ├── ir_codec.py                    IR encode / decode logic
│   ├── manifest.json
│   ├── services.yaml                  Timer entity service definitions
│   ├── strings.json
│   ├── switch.py                      Outside-unit quiet switch
│   └── translations/en.json
├── docs/
│   └── integration.md                 Integration-specific documentation
├── resources/
│   └── fujitsu-ir-codes-broadlink.json  Recorded codes for analysis
├── src/
│   ├── fujitsu_ir/                    Standalone protocol library
│   │   ├── __init__.py
│   │   ├── broadlink.py               Broadlink ↔ raw timing conversion
│   │   ├── const.py                   Protocol constants
│   │   └── protocol.py                Encode / decode Fujitsu messages
│   └── tools/
│       ├── __init__.py
│       └── analyze_codes.py           CLI analysis tool
├── hacs.json                          HACS metadata
├── LICENSE                            MIT license
├── pytest.ini                         Test configuration
├── tests/                             Unit tests
│   ├── test_protocol.py               Protocol encode / decode
│   ├── test_broadlink.py              Broadlink format conversion
│   ├── test_recorded_codes.py         Recorded IR code validation
│   └── test_ir_codec.py               HA integration codec
└── README.md                          ← you are here
```

## Fujitsu IR Protocol

### Message Types

The protocol uses two message formats:

* **Short (7 bytes)** — simple commands such as power off and swing toggle
* **Long (16 bytes)** — full state including mode, temperature, fan speed,
  swing setting, and timers

Every "set state" transmission is a long message that carries the complete
desired AC configuration. The AC applies the entire state atomically —
there is no concept of changing a single setting.

### Long Message Byte Map

| Byte | Field | Description |
|------|-------|-------------|
| 0–1 | Header | Always `0x14 0x63` |
| 2 | Device ID | Bits 5:4 hold the device ID (0–3) |
| 3–4 | Fixed | Always `0x10 0x10` |
| 5 | Command | `0xFE` = full state |
| 6 | RestLength | `0x09` (9 bytes follow) |
| 7 | Protocol | `0x31` for AR-RWE3E / ARREW4E family |
| 8 | Power and Temperature | Bit 0 = power on/off. Bits 7:2 = encoded temperature |
| 9 | Mode and Flags | Bits 2:0 = mode. Bit 3 = clean. Bits 5:4 = timer type |
| 10 | Fan and Swing | Bits 2:0 = fan speed. Bits 5:4 = swing mode |
| 11–13 | Timers | Off/sleep timer and on timer values (zeros when unused) |
| 14 | Flags | Bit 5 = always 1. Bit 0 = model flag. Bit 7 = outside quiet |
| 15 | Checksum | Sum of bytes 7–15 ≡ 0 (mod 256) |

### Short Message Byte Map

| Byte | Field | Description |
|------|-------|-------------|
| 0–1 | Header | Always `0x14 0x63` |
| 2 | Device ID | Bits 5:4 hold the device ID (0–3) |
| 3–4 | Fixed | Always `0x10 0x10` |
| 5 | Command | e.g. `0x02` = power off |
| 6 | Inverse | Bitwise inverse of byte 5 |

### Temperature Encoding

The raw temperature field is 6 bits wide. The formula depends on the
protocol version:

* Protocol `0x31` (AR-RWE3E / ARREW4E):

$$
\text{raw} = (°C - 8) \times 2
$$

* Protocol `0x30` (standard ARRAH2E, ARDB1):

$$
\text{raw} = (°C - 16) \times 4
$$

### Mode Values

| Mode | Value |
|------|-------|
| Auto | `0x00` |
| Cool | `0x01` |
| Dry | `0x02` |
| Fan | `0x03` |
| Heat | `0x04` |

### Fan Speed Values

| Fan Speed | Value |
|-----------|-------|
| Auto | `0x00` |
| High | `0x01` |
| Medium | `0x02` |
| Low | `0x03` |
| Quiet | `0x04` |

### Swing Mode Values

| Swing Mode | Value |
|------------|-------|
| Off | `0x00` |
| Vertical | `0x01` |
| Horizontal | `0x02` |
| Both | `0x03` |

## Standalone Library

The `src/fujitsu_ir/` package provides a pure-Python encoder/decoder with
no external dependencies.

### Encoding an IR Command

```python
from fujitsu_ir import FujitsuAC, FujitsuACState
from fujitsu_ir.const import MODE_COOL, FAN_AUTO, SWING_OFF

state = FujitsuACState(
    power=True,
    temperature=24.0,
    mode=MODE_COOL,
    fan=FAN_AUTO,
    swing=SWING_OFF,
)
ac = FujitsuAC(state)
raw_bytes = ac.encode()
```

### Decoding Raw Bytes

```python
from fujitsu_ir import FujitsuAC

ac = FujitsuAC.from_bytes(raw_bytes)
print(ac.state)
```

### Converting to Broadlink Format

```python
from fujitsu_ir import BroadlinkIR

b64_code = BroadlinkIR.bytes_to_broadlink(raw_bytes)
decoded = BroadlinkIR.broadlink_to_bytes(b64_code)
```

## Analysis Tool

The analysis tool decodes every recorded Broadlink IR code from
`resources/fujitsu-ir-codes-broadlink.json` and prints a byte-level
breakdown:

```bash
cd src
python3 -m tools.analyze_codes
```

The output includes:

* A summary table listing each named command with its key decoded fields
* A detailed per-command section showing all 16 bytes and their
  interpretation

This is useful for verifying round-trip encoding or adapting the library
to other Fujitsu remote models.

## Adapting to Other Fujitsu Models

The library handles two protocol versions controlled by
`FujitsuACState.protocol`:

* `PROTOCOL_ARREW4E` (`0x31`) — AR-RWE3E, ARREW4E and related models
* `PROTOCOL_STANDARD` (`0x30`) — ARRAH2E, ARDB1 and most other models

The protocol byte determines which temperature formula is used during
encoding and decoding. All other fields (mode, fan, swing) are identical
across both versions.

To add support for a new model, record a set of IR codes using a Broadlink
device, decode them with the analysis tool, and compare the byte patterns
against the existing protocol documentation above.

## References

* [IRremoteESP8266 — Fujitsu AC support](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Fujitsu.cpp)
* [python-broadlink — Broadlink IR format](https://github.com/mjg59/python-broadlink)

## Running the Tests

The test suite covers the standalone protocol library, the Broadlink
format converter, round-trip validation against all 45 recorded IR codes,
and the Home Assistant integration codec.

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/pytest tests/ -v
```

Tests run without Home Assistant installed — the integration codec tests
stub the HA package imports so only the pure-Python codec logic is
exercised.
