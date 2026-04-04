"""IR transport backends for sending encoded IR commands.

Each transport takes raw IR timing data (alternating mark/space
microsecond durations) and sends it via a specific hardware platform.

To add a new blaster backend, subclass :class:`IRTransport` and
register it in :data:`TRANSPORT_REGISTRY`.
"""

from __future__ import annotations

import abc
import base64
import logging
from typing import Any

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

# ============================================================================
# Abstract base
# ============================================================================


class IRTransport(abc.ABC):
    """Abstract base for IR blaster transports.

    Sub-classes must implement :meth:`async_send_timings` which converts
    raw mark/space timing arrays into the hardware-specific format and
    transmits via the appropriate Home Assistant service call.

    :param hass: Home Assistant instance.
    :param entity_id: The HA entity that controls the IR blaster.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        """Initialise the transport.

        :param hass: Home Assistant instance.
        :param entity_id: Entity ID of the IR blaster device.
        """
        self._hass = hass
        self._entity_id = entity_id

    @property
    def entity_id(self) -> str:
        """Return the entity ID of the IR blaster.

        :return: Entity ID string.
        """
        return self._entity_id

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
    :param entity_id: Entity ID of the Broadlink remote entity.
    """

    async def async_send_timings(self, timings_us: list[int]) -> None:
        """Encode timings as Broadlink base64 and send.

        :param timings_us: Alternating mark/space durations in
            microseconds.
        """
        b64_code = self._timings_to_broadlink(timings_us)
        try:
            await self._hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self._entity_id,
                    "command": f"b64:{b64_code}",
                },
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Failed to send IR command via %s", self._entity_id
            )

    # ----- Broadlink format helpers -----------------------------------------

    @staticmethod
    def _timings_to_broadlink(
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
# Registry
# ============================================================================

TRANSPORT_REGISTRY: dict[str, type[IRTransport]] = {
    TRANSPORT_BROADLINK: BroadlinkTransport,
}


def create_transport(
    transport_type: str,
    hass: HomeAssistant,
    entity_id: str,
) -> IRTransport:
    """Create an IR transport instance by type key.

    :param transport_type: Key from ``TRANSPORT_REGISTRY``
        (e.g. ``"broadlink"``).
    :param hass: Home Assistant instance.
    :param entity_id: Entity ID of the blaster device.
    :return: Configured transport instance.
    :raises ValueError: If the transport type is unknown.
    """
    transport_cls = TRANSPORT_REGISTRY.get(transport_type)
    if transport_cls is None:
        raise ValueError(
            f"Unknown IR transport type: {transport_type!r}. "
            f"Valid types: {', '.join(TRANSPORT_REGISTRY)}"
        )
    return transport_cls(hass, entity_id)
