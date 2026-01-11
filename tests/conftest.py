"""Pytest fixtures for DaVinci Fireplace tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.davinci_fireplace.coordinator import (
    DaVinciCoordinator,
    FireplaceState,
)


@pytest.fixture
def mock_hass() -> MagicMock:
    """Return a mock Home Assistant instance."""
    hass = MagicMock()
    hass.loop = MagicMock()
    return hass


@pytest.fixture
def coordinator(mock_hass: MagicMock) -> DaVinciCoordinator:
    """Return a DaVinciCoordinator instance for testing."""
    return DaVinciCoordinator(
        hass=mock_hass,
        host="192.168.1.100",
        port=10001,
        scan_interval=300,
        entry_id="test_entry_id",
    )


@pytest.fixture
def mock_connection() -> Generator[AsyncMock, None, None]:
    """Mock asyncio.open_connection."""
    with patch("asyncio.open_connection") as mock:
        reader = AsyncMock()
        writer = MagicMock()
        writer.is_closing.return_value = False
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        mock.return_value = (reader, writer)
        yield mock
