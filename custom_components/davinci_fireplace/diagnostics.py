"""Diagnostics support for DaVinci Fireplace integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL, DOMAIN
from .coordinator import DaVinciCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the config entry."""
    coordinator: DaVinciCoordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "config": {
            "host": entry.data.get(CONF_HOST),
            "port": entry.data.get(CONF_PORT),
            "scan_interval": entry.options.get(CONF_SCAN_INTERVAL),
        },
        "state": {
            "connected": coordinator.state.connected,
            "lamp_on": coordinator.state.lamp_on,
            "lamp_level": coordinator.state.lamp_level,
            "led_on": coordinator.state.led_on,
            "led_rgbw": coordinator.state.led_rgbw,
            "flame_on": coordinator.state.flame_on,
            "fan_on": coordinator.state.fan_on,
            "fan_speed": coordinator.state.fan_speed,
        },
        "connection": {
            "reconnect_attempts": coordinator.reconnect_attempts,
            "last_error": coordinator.last_error,
            "queue_size": coordinator.command_queue_size,
        },
    }
