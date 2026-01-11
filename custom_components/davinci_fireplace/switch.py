"""Switch platform for DaVinci Fireplace integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DaVinciCoordinator, DaVinciEntityMixin

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DaVinci Fireplace switch entities."""
    coordinator: DaVinciCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up switch entities for %s", entry.entry_id)
    async_add_entities([DaVinciFlameSwitch(coordinator)])


class DaVinciFlameSwitch(DaVinciEntityMixin, SwitchEntity):
    """Switch entity for DaVinci Fireplace flame."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_name = "Flame"

    def __init__(self, coordinator: DaVinciCoordinator) -> None:
        """Initialize the flame switch."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_flame"

    @property
    def is_on(self) -> bool:
        """Return True if flame is on."""
        return self.coordinator.state.flame_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the flame."""
        _LOGGER.debug("Flame turn_on")
        await self.coordinator.send_command("SET FLAME ON")
        await self.coordinator.async_refresh_property("FLAME")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the flame."""
        _LOGGER.debug("Flame turn_off")
        await self.coordinator.send_command("SET FLAME OFF")
        await self.coordinator.async_refresh_property("FLAME")
