#!/usr/bin/env python3
"""Analyze recorded Broadlink IR codes for Fujitsu AC.

Decode each recorded command from the JSON file, extract the Fujitsu AC
protocol bytes, and display a detailed analysis.

Usage::

    cd src && python3 -m tools.analyze_codes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fujitsu_ir.broadlink import BroadlinkIR
from fujitsu_ir.const import (
    CMD_LONG_STATE,
    CMD_NAMES,
    CMD_STAY_ON,
    CMD_TURN_OFF,
    CMD_TURN_ON,
    FAN_NAMES,
    MODE_NAMES,
    SWING_NAMES,
)
from fujitsu_ir.protocol import FujitsuAC


def analyze_code(name: str, code: str) -> None:
    """Analyze a single Broadlink IR code and print the result.

    :param name: Human-readable label for this code.
    :param code: Base64-encoded Broadlink IR code.
    """
    print(f"\n{'='*72}")
    print(f"  {name}")
    print(f"{'='*72}")

    try:
        # Decode Broadlink base64 → raw timing → protocol bytes
        timings = BroadlinkIR.decode_base64(code)
        ir_bytes = BroadlinkIR.timings_to_bytes(timings)

        # Show raw bytes
        print(FujitsuAC.describe_bytes(ir_bytes))

        # Decode to AC state
        ac = FujitsuAC.from_bytes(ir_bytes)
        print(f"\n  → Decoded State:")
        for line in ac.describe().split("\n"):
            print(f"     {line}")

        # Round-trip test: re-encode and compare
        re_encoded = ac.encode()
        if re_encoded == ir_bytes:
            print("\n  ✓ Round-trip encoding matches perfectly")
        else:
            print("\n  ✗ Round-trip encoding differs!")
            print(f"    Original:    {FujitsuAC.bytes_to_hex(ir_bytes)}")
            print(f"    Re-encoded:  {FujitsuAC.bytes_to_hex(re_encoded)}")
            # Show which bytes differ
            for i in range(max(len(ir_bytes), len(re_encoded))):
                orig = ir_bytes[i] if i < len(ir_bytes) else None
                reenc = re_encoded[i] if i < len(re_encoded) else None
                if orig != reenc:
                    print(f"    Byte {i}: 0x{orig:02X} → 0x{reenc:02X}" if orig is not None and reenc is not None else f"    Byte {i}: length mismatch")

    except Exception as exc:  # noqa: BLE001  # analysis tool — report, don't crash
        print(f"  ERROR: {exc}")


def main() -> None:
    """Load the JSON file, decode every IR code, and print analysis."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    json_path = (project_root / ".." / "resources" / "fujitsu-ir-codes-broadlink.json").resolve()

    if not json_path.exists():
        json_path = (project_root / "resources" / "fujitsu-ir-codes-broadlink.json").resolve()

    if not json_path.exists():
        print(f"ERROR: Cannot find JSON file at {json_path}")
        sys.exit(1)

    print(f"Reading: {json_path}")

    with json_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    # Navigate to the codes
    codes: dict[str, str] = {}
    if "data" in data:
        for device_name, device_codes in data["data"].items():
            print(f"\nDevice: {device_name}")
            codes = device_codes
    else:
        codes = data

    # Summary table
    print(f"\n{'#'*72}")
    print(f"  SUMMARY TABLE")
    print(f"{'#'*72}")
    print(f"{'Name':<35} {'Power':<6} {'Mode':<10} {'Temp':<8} {'Fan':<8} {'Swing':<8}")
    print(f"{'-'*35} {'-'*6} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")

    for name, code in codes.items():
        try:
            ir_bytes = BroadlinkIR.broadlink_to_bytes(code)
            ac = FujitsuAC.from_bytes(ir_bytes)

            if ac.command in (CMD_TURN_ON, CMD_STAY_ON, CMD_LONG_STATE):
                # Full state command
                power_str = "ON" if ac.state.power else "OFF"
                mode_str = MODE_NAMES.get(ac.state.mode, "?")
                temp_str = f"{ac.state.temperature}°C"
                fan_str = FAN_NAMES.get(ac.state.fan, "?")
                swing_str = SWING_NAMES.get(ac.state.swing, "?")
            else:
                power_str = "OFF" if ac.command == CMD_TURN_OFF else "-"
                mode_str = CMD_NAMES.get(ac.command, "?")
                temp_str = "-"
                fan_str = "-"
                swing_str = "-"

            print(f"{name:<35} {power_str:<6} {mode_str:<10} {temp_str:<8} {fan_str:<8} {swing_str:<8}")
        except Exception as exc:  # noqa: BLE001  # analysis tool — report, don't crash
            print(f"{name:<35} ERROR: {exc}")

    # Detailed analysis
    print(f"\n{'#'*72}")
    print(f"  DETAILED ANALYSIS")
    print(f"{'#'*72}")

    for name, code in codes.items():
        analyze_code(name, code)


if __name__ == "__main__":
    main()
