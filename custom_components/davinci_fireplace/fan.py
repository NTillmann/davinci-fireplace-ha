"""Fan platform for DaVinci Fireplace integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
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
    """Set up DaVinci Fireplace fan entities."""
    coordinator: DaVinciCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up fan entities for %s", entry.entry_id)
    async_add_entities([DaVinciFan(coordinator)])


class DaVinciFan(DaVinciEntityMixin, FanEntity):
    """Fan entity for DaVinci Fireplace heat fan.

    Speed Scale Conversion:
        - Home Assistant uses 0-100 (percentage)
        - Fireplace uses 0-10 for HEATFANSPEED
        - Internal state uses 0-100 (same as HA)

        HA → Fireplace: round(percentage / 10)  (100 → 10)
        Fireplace → Internal: speed * 10  (10 → 100)

    The fan has 10 discrete speeds (speed_count=10), so HA's slider
    snaps to 0, 10, 20, ..., 100%.
    """

    _attr_name = "Heat Fan"
    _attr_supported_features = FanEntityFeature.SET_SPEED
    _attr_speed_count = 10  # 10 discrete speeds (1-10)

    def __init__(self, coordinator: DaVinciCoordinator) -> None:
        """Initialize the fan."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_fan"

    @property
    def is_on(self) -> bool:
        """Return True if fan is on."""
        return self.coordinator.state.fan_on

    @property
    def percentage(self) -> int:
        """Return the current speed percentage."""
        return self.coordinator.state.fan_speed

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        if percentage is not None:
            _LOGGER.debug("Fan turn_on with percentage=%d", percentage)
            await self.async_set_percentage(percentage)
        else:
            # Plain turn on - just send ON, fireplace remembers last speed
            _LOGGER.debug("Fan turn_on (no percentage specified)")
            await self.coordinator.send_command("SET HEATFAN ON")
            await self.coordinator.async_refresh_property("HEATFAN")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        _LOGGER.debug("Fan turn_off")
        await self.coordinator.send_command("SET HEATFAN OFF")
        await self.coordinator.async_refresh_property("HEATFAN")

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed percentage."""
        # Convert 0-100 to 0-10
        speed = round(percentage / 10)
        _LOGGER.debug("Fan set_percentage=%d (speed=%d)", percentage, speed)
        await self.coordinator.send_command(f"SET HEATFANSPEED {speed}")
        if speed == 0:
            await self.coordinator.send_command("SET HEATFAN OFF")
        else:
            await self.coordinator.send_command("SET HEATFAN ON")
        await self.coordinator.async_refresh_property("HEATFAN", "HEATFANSPEED")
