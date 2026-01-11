"""Tests for DaVinci Fireplace coordinator."""

from __future__ import annotations

import pytest

from custom_components.davinci_fireplace.const import BACKOFF_BASE, BACKOFF_MAX
from custom_components.davinci_fireplace.coordinator import (
    DaVinciCoordinator,
    FireplaceState,
)


class TestFireplaceState:
    """Tests for FireplaceState dataclass."""

    def test_default_values(self) -> None:
        """Test default state values."""
        state = FireplaceState()
        assert state.lamp_on is False
        assert state.lamp_level == 0
        assert state.led_on is False
        assert state.led_rgbw == (0, 0, 0, 0)
        assert state.flame_on is False
        assert state.fan_on is False
        assert state.fan_speed == 0
        assert state.connected is False


class TestCoordinatorParsing:
    """Tests for coordinator response parsing."""

    def test_parse_ledcolor_valid(self, coordinator: DaVinciCoordinator) -> None:
        """Test parsing valid LEDCOLOR response."""
        result = coordinator._parse_ledcolor("RED: 255 GREEN: 128 BLUE: 64 WHITE: 32")
        assert result == (255, 128, 64, 32)

    def test_parse_ledcolor_with_extra_spaces(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test parsing LEDCOLOR with extra spaces."""
        result = coordinator._parse_ledcolor("RED:  255  GREEN:  128  BLUE:  64  WHITE:  32")
        assert result == (255, 128, 64, 32)

    def test_parse_ledcolor_invalid_format(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test parsing invalid LEDCOLOR format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid LEDCOLOR format"):
            coordinator._parse_ledcolor("INVALID")

    def test_handle_get_response_lamp_on(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling LAMP ON response."""
        coordinator._handle_get_response("LAMP", "ON")
        assert coordinator.state.lamp_on is True

    def test_handle_get_response_lamp_off(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling LAMP OFF response."""
        coordinator.state.lamp_on = True
        coordinator._handle_get_response("LAMP", "OFF")
        assert coordinator.state.lamp_on is False

    def test_handle_get_response_lamplevel(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling LAMPLEVEL response (converts 0-10 to 0-100)."""
        coordinator._handle_get_response("LAMPLEVEL", "5")
        assert coordinator.state.lamp_level == 50

    def test_handle_get_response_lamplevel_invalid(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling invalid LAMPLEVEL response (FIX6 defensive parsing)."""
        coordinator.state.lamp_level = 50
        # Should not raise, should log and ignore
        coordinator._handle_get_response("LAMPLEVEL", "ON")
        # State should remain unchanged
        assert coordinator.state.lamp_level == 50

    def test_handle_get_response_led_on(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling LED ON response."""
        coordinator._handle_get_response("LED", "ON")
        assert coordinator.state.led_on is True

    def test_handle_get_response_ledcolor_off(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling LEDCOLOR OFF response (FIX6)."""
        coordinator.state.led_on = True
        coordinator._handle_get_response("LEDCOLOR", "OFF")
        assert coordinator.state.led_on is False

    def test_handle_get_response_ledcolor_values(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling LEDCOLOR with actual values."""
        coordinator._handle_get_response("LEDCOLOR", "RED: 100 GREEN: 150 BLUE: 200 WHITE: 50")
        assert coordinator.state.led_rgbw == (100, 150, 200, 50)

    def test_handle_get_response_flame(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling FLAME response."""
        coordinator._handle_get_response("FLAME", "ON")
        assert coordinator.state.flame_on is True
        coordinator._handle_get_response("FLAME", "OFF")
        assert coordinator.state.flame_on is False

    def test_handle_get_response_heatfan(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling HEATFAN response."""
        coordinator._handle_get_response("HEATFAN", "ON")
        assert coordinator.state.fan_on is True
        coordinator._handle_get_response("HEATFAN", "OFF")
        assert coordinator.state.fan_on is False

    def test_handle_get_response_heatfanspeed(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling HEATFANSPEED response (converts 0-10 to 0-100)."""
        coordinator._handle_get_response("HEATFANSPEED", "7")
        assert coordinator.state.fan_speed == 70

    def test_handle_get_response_heatfanspeed_invalid(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling invalid HEATFANSPEED response (FIX6)."""
        coordinator.state.fan_speed = 70
        # Should not raise
        coordinator._handle_get_response("HEATFANSPEED", "INVALID")
        # State should remain unchanged
        assert coordinator.state.fan_speed == 70


class TestHeyMessageHandling:
    """Tests for HEY message parsing."""

    def test_handle_hey_message_lamp(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling HEY LAMP ON message."""
        coordinator._handle_hey_message("LAMP ON")
        assert coordinator.state.lamp_on is True

    def test_handle_hey_message_flame(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling HEY FLAME OFF message."""
        coordinator.state.flame_on = True
        coordinator._handle_hey_message("FLAME OFF")
        assert coordinator.state.flame_on is False

    def test_handle_hey_message_ledcolor(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling HEY LEDCOLOR message."""
        coordinator._handle_hey_message("LEDCOLOR RED: 255 GREEN: 0 BLUE: 128 WHITE: 64")
        assert coordinator.state.led_rgbw == (255, 0, 128, 64)

    def test_handle_hey_message_malformed(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test handling malformed HEY message (no space)."""
        # Should not raise, should log and ignore
        coordinator._handle_hey_message("MALFORMED")


class TestExponentialBackoff:
    """Tests for exponential backoff calculation."""

    def test_backoff_sequence(self) -> None:
        """Test that backoff follows expected pattern.

        Formula: min(10 * 2^n, 3600) where n starts at 0
        See PROTOCOL.md "Reconnection Strategy"
        """
        delays = [min(BACKOFF_BASE * (2**i), BACKOFF_MAX) for i in range(0, 10)]
        expected = [10, 20, 40, 80, 160, 320, 640, 1280, 2560, 3600]
        assert delays == expected

    def test_backoff_caps_at_max(self) -> None:
        """Test that backoff is capped at BACKOFF_MAX (1 hour)."""
        delay = min(BACKOFF_BASE * (2**20), BACKOFF_MAX)
        assert delay == 3600


class TestDeviceInfo:
    """Tests for device info."""

    def test_device_info(self, coordinator: DaVinciCoordinator) -> None:
        """Test device info properties."""
        info = coordinator.device_info
        assert ("davinci_fireplace", "test_entry_id") in info["identifiers"]
        assert info["name"] == "DaVinci Fireplace"
        assert info["manufacturer"] == "Travis Industries"
        assert info["model"] == "DaVinci Custom Fireplace"


class TestCallbacks:
    """Tests for callback registration."""

    def test_register_callback(self, coordinator: DaVinciCoordinator) -> None:
        """Test registering a callback."""
        callback = lambda: None
        coordinator.register_callback(callback)
        assert callback in coordinator._callbacks

    def test_unregister_callback(self, coordinator: DaVinciCoordinator) -> None:
        """Test unregistering a callback."""
        callback = lambda: None
        coordinator.register_callback(callback)
        coordinator.unregister_callback(callback)
        assert callback not in coordinator._callbacks

    def test_unregister_nonexistent_callback(
        self, coordinator: DaVinciCoordinator
    ) -> None:
        """Test unregistering a callback that was never registered."""
        callback = lambda: None
        # Should not raise
        coordinator.unregister_callback(callback)

    def test_notify_state_update(self, coordinator: DaVinciCoordinator) -> None:
        """Test that state updates call registered callbacks."""
        called = []
        callback = lambda: called.append(True)
        coordinator.register_callback(callback)
        coordinator._notify_state_update()
        assert len(called) == 1
