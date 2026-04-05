"""IR transport backends for sending encoded IR commands.

Each transport takes raw IR timing data (alternating mark/space
microsecond durations) and sends it via a specific hardware platform.

To add a new blaster backend, subclass :class:`IRTransport` and
register it in :data:`TRANSPORT_REGISTRY`.
"""

from __future__ import annotations

import abc
import base64
import json
import logging

from homeassistant.core import HomeAssistant

from .const import (
    BROADLINK_IR_TYPE,
    BROADLINK_TICK_US,
)

_LOGGER = logging.getLogger(__name__)

# ============================================================================
# Transport identifiers (used in config entries)
# ============================================================================
TRANSPORT_BROADLINK = "broadlink"
TRANSPORT_ESPHOME = "esphome"
TRANSPORT_SWITCHBOT = "switchbot"
TRANSPORT_AQARA = "aqara"

# Transports that use a ``remote`` entity (entity selector in config flow).
ENTITY_TRANSPORTS = frozenset({TRANSPORT_BROADLINK, TRANSPORT_SWITCHBOT, TRANSPORT_AQARA})

# ============================================================================
# Abstract base
# ============================================================================


class IRTransport(abc.ABC):
    """Abstract base for IR blaster transports.

    Sub-classes must implement :meth:`async_send_timings` which converts
    raw mark/space timing arrays into the hardware-specific format and
    transmits via the appropriate Home Assistant service call.

    :param hass: Home Assistant instance.
    :param device_ref: Identifier for the blaster device.  For most
        transports this is a Home Assistant entity ID
        (e.g. ``remote.broadlink_rm4``).  For ESPHome it is the
        ESPHome device node name (e.g. ``ir_blaster``).
    """

    def __init__(self, hass: HomeAssistant, device_ref: str) -> None:
        """Initialise the transport.

        :param hass: Home Assistant instance.
        :param device_ref: Device reference (entity ID or device name).
        """
        self._hass = hass
        self._device_ref = device_ref

    @property
    def entity_id(self) -> str:
        """Return the device reference string.

        For entity-based transports this is the entity ID; for ESPHome
        it is the node name.

        :return: Device reference string.
        """
        return self._device_ref

    @abc.abstractmethod
    async def async_send_timings(self, timings_us: list[int]) -> None:
        """Send raw IR timing data through the blaster hardware.

        :param timings_us: Alternating mark/space durations in
            microseconds, starting with a mark.
        """


# ============================================================================
# Broadlink backend
# ============================================================================


class BroadlinkTransport(IRTransport):
    """Send IR commands via a Broadlink RM device.

    Converts raw mark/space timing arrays into the Broadlink base64
    packet format and sends via ``remote.send_command``.

    :param hass: Home Assistant instance.
    :param device_ref: Entity ID of the Broadlink remote entity.
    """

    async def async_send_timings(self, timings_us: list[int]) -> None:
        """Encode timings as Broadlink base64 and send.

        :param timings_us: Alternating mark/space durations in
            microseconds.
        """
        b64_code = self.timings_to_broadlink(timings_us)
        try:
            await self._hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self._device_ref,
                    "command": f"b64:{b64_code}",
                },
                blocking=True,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to send IR command via %s", self._device_ref
            )
            raise

    # ----- Broadlink format helpers -----------------------------------------

    @staticmethod
    def timings_to_broadlink(
        timings_us: list[int], repeat: int = 0
    ) -> str:
        """Encode raw IR timings into Broadlink base64 format.

        :param timings_us: Alternating mark/space durations in µs.
        :param repeat: Number of times to repeat the signal.
        :return: Base64-encoded Broadlink IR code.
        """
        timing_bytes = bytearray()
        for us in timings_us:
            ticks = round(us / BROADLINK_TICK_US)
            if ticks > 255:
                timing_bytes.append(0x00)
                timing_bytes.append((ticks >> 8) & 0xFF)
                timing_bytes.append(ticks & 0xFF)
            else:
                timing_bytes.append(max(1, ticks))

        data_len = len(timing_bytes)
        packet = bytearray()
        packet.append(BROADLINK_IR_TYPE)
        packet.append(repeat & 0xFF)
        packet.append(data_len & 0xFF)
        packet.append((data_len >> 8) & 0xFF)
        packet.extend(timing_bytes)
        packet.append(0x0D)
        packet.append(0x05)

        return base64.b64encode(bytes(packet)).decode("ascii")

    @staticmethod
    def broadlink_to_timings(code: str) -> list[int]:
        """Decode a Broadlink base64 code into raw IR timings.

        :param code: Base64-encoded Broadlink IR code.
        :return: Alternating mark/space durations in µs.
        :raises ValueError: If the code is invalid.
        """
        raw = base64.b64decode(code)
        if len(raw) < 4 or raw[0] != BROADLINK_IR_TYPE:
            raise ValueError("Invalid Broadlink IR code")

        data_len = raw[2] | (raw[3] << 8)
        timings: list[int] = []
        i = 4
        end = min(4 + data_len, len(raw))
        while i < end:
            if raw[i] == 0x00:
                if i + 2 < end:
                    ticks = (raw[i + 1] << 8) | raw[i + 2]
                    i += 3
                else:
                    break
            else:
                ticks = raw[i]
                i += 1
            timings.append(round(ticks * BROADLINK_TICK_US))
        return timings


# ============================================================================
# ESPHome backend
# ============================================================================


class ESPHomeTransport(IRTransport):
    """Send IR commands via an ESPHome device's custom API service.

    The ESPHome device must expose an API service named
    ``send_raw_ir`` that accepts a ``code`` parameter (``int[]``) and
    forwards it to ``remote_transmitter.transmit_raw``.  See the
    integration documentation for the required ESPHome YAML
    configuration.

    Raw timings are converted to **signed** integers: positive values
    are marks (IR LED on), negative values are spaces (IR LED off).
    This matches the format used by ESPHome's
    ``remote_transmitter.transmit_raw`` action.

    :param hass: Home Assistant instance.
    :param device_ref: ESPHome device node name (e.g. ``ir_blaster``).
    """

    #: Name of the ESPHome API service to call (suffix after node name).
    SERVICE_NAME = "send_raw_ir"

    async def async_send_timings(self, timings_us: list[int]) -> None:
        """Convert timings to signed format and send via ESPHome service.

        :param timings_us: Alternating mark/space durations in
            microseconds.
        """
        signed = self.timings_to_signed(timings_us)
        service = f"{self._device_ref}_{self.SERVICE_NAME}"
        try:
            await self._hass.services.async_call(
                "esphome",
                service,
                {"code": signed},
                blocking=True,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to send IR via ESPHome service esphome.%s",
                service,
            )
            raise

    @staticmethod
    def timings_to_signed(timings_us: list[int]) -> list[int]:
        """Convert alternating mark/space timings to signed integers.

        Even-indexed values (marks) stay positive; odd-indexed values
        (spaces) are negated.

        :param timings_us: Alternating mark/space durations in µs.
        :return: Signed timing list for ESPHome ``transmit_raw``.
        """
        return [
            us if i % 2 == 0 else -us
            for i, us in enumerate(timings_us)
        ]


# ============================================================================
# SwitchBot backend
# ============================================================================


class SwitchBotTransport(IRTransport):
    """Send IR commands via a SwitchBot Hub remote entity.

    The timing data is encoded as a JSON array of signed microsecond
    values (positive = mark, negative = space) and sent via
    ``remote.send_command``.

    .. note::

       This transport requires that the SwitchBot HA integration
       (``switchbot_cloud``) forwards raw command strings to the Hub.
       Support is **experimental** — see the integration documentation
       for details and known limitations.

    :param hass: Home Assistant instance.
    :param device_ref: Entity ID of the SwitchBot remote entity.
    """

    async def async_send_timings(self, timings_us: list[int]) -> None:
        """Encode timings and send via SwitchBot remote entity.

        :param timings_us: Alternating mark/space durations in
            microseconds.
        """
        command = self.timings_to_command(timings_us)
        try:
            await self._hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self._device_ref,
                    "command": command,
                },
                blocking=True,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to send IR via SwitchBot %s", self._device_ref
            )
            raise

    @staticmethod
    def timings_to_command(timings_us: list[int]) -> str:
        """Encode timings as a JSON array of signed µs values.

        :param timings_us: Alternating mark/space durations in µs.
        :return: JSON-encoded signed timing array string.
        """
        signed = [
            us if i % 2 == 0 else -us
            for i, us in enumerate(timings_us)
        ]
        return json.dumps(signed, separators=(",", ":"))


# ============================================================================
# Aqara backend
# ============================================================================


class AqaraTransport(IRTransport):
    """Send IR commands via an Aqara Hub remote entity.

    The timing data is encoded as a JSON array of signed microsecond
    values (positive = mark, negative = space) and sent via
    ``remote.send_command``.

    .. note::

       This transport requires that the Aqara HA integration forwards
       raw command strings to the Hub.  Support is **experimental** —
       see the integration documentation for details and known
       limitations.

    :param hass: Home Assistant instance.
    :param device_ref: Entity ID of the Aqara remote entity.
    """

    async def async_send_timings(self, timings_us: list[int]) -> None:
        """Encode timings and send via Aqara remote entity.

        :param timings_us: Alternating mark/space durations in
            microseconds.
        """
        command = self.timings_to_command(timings_us)
        try:
            await self._hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self._device_ref,
                    "command": command,
                },
                blocking=True,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to send IR via Aqara %s", self._device_ref
            )
            raise

    @staticmethod
    def timings_to_command(timings_us: list[int]) -> str:
        """Encode timings as a JSON array of signed µs values.

        :param timings_us: Alternating mark/space durations in µs.
        :return: JSON-encoded signed timing array string.
        """
        signed = [
            us if i % 2 == 0 else -us
            for i, us in enumerate(timings_us)
        ]
        return json.dumps(signed, separators=(",", ":"))


# ============================================================================
# Registry
# ============================================================================

TRANSPORT_REGISTRY: dict[str, type[IRTransport]] = {
    TRANSPORT_BROADLINK: BroadlinkTransport,
    TRANSPORT_ESPHOME: ESPHomeTransport,
    TRANSPORT_SWITCHBOT: SwitchBotTransport,
    TRANSPORT_AQARA: AqaraTransport,
}


def create_transport(
    transport_type: str,
    hass: HomeAssistant,
    device_ref: str,
) -> IRTransport:
    """Create an IR transport instance by type key.

    :param transport_type: Key from ``TRANSPORT_REGISTRY``
        (e.g. ``"broadlink"``).
    :param hass: Home Assistant instance.
    :param device_ref: Entity ID of the blaster device, or ESPHome
        device node name.
    :return: Configured transport instance.
    :raises ValueError: If the transport type is unknown.
    """
    transport_cls = TRANSPORT_REGISTRY.get(transport_type)
    if transport_cls is None:
        raise ValueError(
            f"Unknown IR transport type: {transport_type!r}. "
            f"Valid types: {', '.join(TRANSPORT_REGISTRY)}"
        )
    return transport_cls(hass, device_ref)
