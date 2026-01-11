"""DaVinci Fireplace integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import DaVinciCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH, Platform.FAN]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DaVinci Fireplace from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    _LOGGER.debug(
        "Setting up DaVinci Fireplace integration for %s:%s (scan_interval=%ds)",
        host,
        port,
        scan_interval,
    )

    coordinator = DaVinciCoordinator(
        hass,
        host,
        port,
        scan_interval,
        entry.entry_id,
    )

    # Start connection (non-blocking - reconnects in background)
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    _LOGGER.info("DaVinci Fireplace integration setup complete for %s:%s", host, port)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading DaVinci Fireplace integration for %s", entry.data[CONF_HOST])

    # Unload platforms FIRST (entities may still be using coordinator)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: DaVinciCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
        _LOGGER.info("DaVinci Fireplace integration unloaded for %s", entry.data[CONF_HOST])
    else:
        _LOGGER.warning(
            "Failed to unload platforms for DaVinci Fireplace %s", entry.data[CONF_HOST]
        )
    return unload_ok


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update (scan interval change)."""
    new_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    _LOGGER.info(
        "DaVinci Fireplace options updated: scan_interval=%ds for %s",
        new_interval,
        entry.data[CONF_HOST],
    )
    coordinator: DaVinciCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_scan_interval(new_interval)
