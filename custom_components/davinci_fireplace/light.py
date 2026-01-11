"""Light platform for DaVinci Fireplace integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_WHITE,
    ColorMode,
    LightEntity,
)
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
    """Set up DaVinci Fireplace light entities."""
    coordinator: DaVinciCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up light entities for %s", entry.entry_id)
    async_add_entities(
        [
            DaVinciLampLight(coordinator),
            DaVinciLEDLight(coordinator),
        ]
    )


class DaVinciLampLight(DaVinciEntityMixin, LightEntity):
    """Light entity for DaVinci Fireplace lamp (dimmable).

    Brightness Scale Conversion:
        - Home Assistant uses 0-255 for brightness
        - Fireplace uses 0-10 for LAMPLEVEL
        - Internal state uses 0-100 (percentage)

        HA → Fireplace: round(brightness / 25.5)  (255 → 10)
        Fireplace → Internal: level * 10  (10 → 100)
        Internal → HA: level * 2.55  (100 → 255)
    """

    _attr_name = "Lamp"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: DaVinciCoordinator) -> None:
        """Initialize the lamp light."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_lamp"

    @property
    def is_on(self) -> bool:
        """Return True if lamp is on."""
        return self.coordinator.state.lamp_on

    @property
    def brightness(self) -> int | None:
        """Return brightness 0-255, or None if off.

        Returns minimum 1 when on to avoid UI issues (brightness 0 = off).
        """
        if not self.is_on:
            return None
        # Convert 0-100 to 0-255
        return max(1, int(self.coordinator.state.lamp_level * 2.55))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the lamp."""
        if ATTR_BRIGHTNESS in kwargs:
            # Convert 0-255 to 0-10 for fireplace
            level = round(kwargs[ATTR_BRIGHTNESS] / 25.5)
            _LOGGER.debug("Lamp turn_on with brightness=%d (level=%d)", kwargs[ATTR_BRIGHTNESS], level)
            await self.coordinator.send_command(f"SET LAMPLEVEL {level}")
            # Brightness 0 means turn off
            await self.coordinator.send_command(f"SET LAMP {'OFF' if level == 0 else 'ON'}")
        else:
            # No brightness specified - just turn on at current level
            _LOGGER.debug("Lamp turn_on (no brightness specified)")
            await self.coordinator.send_command("SET LAMP ON")
        await self.coordinator.async_refresh_property("LAMP", "LAMPLEVEL")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the lamp."""
        _LOGGER.debug("Lamp turn_off")
        await self.coordinator.send_command("SET LAMP OFF")
        await self.coordinator.async_refresh_property("LAMP")


class DaVinciLEDLight(DaVinciEntityMixin, LightEntity):
    """Light entity for DaVinci Fireplace LED (RGBW).

    Uses ColorMode.RGBW which matches the fireplace protocol exactly:
    SET LEDCOLOR r,g,b,w (each 0-255)
    """

    _attr_name = "LED"
    _attr_color_mode = ColorMode.RGBW
    _attr_supported_color_modes = {ColorMode.RGBW}

    def __init__(self, coordinator: DaVinciCoordinator) -> None:
        """Initialize the LED light."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_led"

    @property
    def is_on(self) -> bool:
        """Return True if LED is on."""
        return self.coordinator.state.led_on

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        """Return RGBW color tuple, or None if off."""
        if not self.is_on:
            return None
        return self.coordinator.state.led_rgbw

    @property
    def brightness(self) -> int | None:
        """Return brightness 0-255, or None if off.

        For RGBW mode, brightness = max(r, g, b, w) per Home Assistant docs.
        Returns minimum 1 when on to avoid UI issues (brightness 0 = off).
        """
        if not self.is_on:
            return None
        return max(1, *self.coordinator.state.led_rgbw)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the LED."""
        # Check if any color-related attribute is provided
        has_color_attr = any(
            attr in kwargs
            for attr in (ATTR_RGBW_COLOR, ATTR_RGB_COLOR, ATTR_WHITE, ATTR_BRIGHTNESS)
        )

        if not has_color_attr:
            # No color specified - just turn on at current/last color
            _LOGGER.debug("LED turn_on (no color specified)")
            await self.coordinator.send_command("SET LED ON")
            # Refresh both LED and LEDCOLOR since LEDCOLOR returns "OFF" when LED is off
            await self.coordinator.async_refresh_property("LED", "LEDCOLOR")
            return

        r, g, b, w = self.coordinator.state.led_rgbw

        if ATTR_RGBW_COLOR in kwargs:
            # Direct RGBW - use as-is
            r, g, b, w = kwargs[ATTR_RGBW_COLOR]
        elif ATTR_RGB_COLOR in kwargs:
            # RGB without white
            r, g, b = kwargs[ATTR_RGB_COLOR]
            w = 0
        elif ATTR_WHITE in kwargs:
            # White-only mode
            r, g, b = 0, 0, 0
            w = kwargs[ATTR_WHITE]

        # Handle brightness adjustment
        if ATTR_BRIGHTNESS in kwargs:
            target = kwargs[ATTR_BRIGHTNESS]
            current_max = max(r, g, b, w)
            if current_max == 0:
                # Color unknown (LED was off since startup), default to white
                w = target
            else:
                # Scale existing color by brightness
                factor = target / current_max
                r, g, b, w = (min(255, int(c * factor)) for c in (r, g, b, w))

        _LOGGER.debug("LED turn_on with RGBW=(%d,%d,%d,%d)", r, g, b, w)
        await self.coordinator.send_command(f"SET LEDCOLOR {r},{g},{b},{w}")

        # All zeros means turn off
        await self.coordinator.send_command(f"SET LED {'OFF' if (r, g, b, w) == (0, 0, 0, 0) else 'ON'}")
        await self.coordinator.async_refresh_property("LED", "LEDCOLOR")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the LED."""
        _LOGGER.debug("LED turn_off")
        await self.coordinator.send_command("SET LED OFF")
        await self.coordinator.async_refresh_property("LED")
