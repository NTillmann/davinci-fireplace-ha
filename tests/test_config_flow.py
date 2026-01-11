"""Tests for DaVinci Fireplace config flow."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.davinci_fireplace.const import DEFAULT_PORT, DOMAIN


async def test_form_success(hass: HomeAssistant) -> None:
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}

    with patch(
        "custom_components.davinci_fireplace.config_flow.DaVinciFireplaceConfigFlow._test_connection",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 10001},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "DaVinci Fireplace (192.168.1.100)"
    assert result["data"] == {CONF_HOST: "192.168.1.100", CONF_PORT: 10001}


async def test_form_connection_error(hass: HomeAssistant) -> None:
    """Test config flow with connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.davinci_fireplace.config_flow.DaVinciFireplaceConfigFlow._test_connection",
        side_effect=asyncio.TimeoutError(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 10001},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_form_os_error(hass: HomeAssistant) -> None:
    """Test config flow with OS error (e.g., connection refused)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.davinci_fireplace.config_flow.DaVinciFireplaceConfigFlow._test_connection",
        side_effect=OSError("Connection refused"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 10001},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_form_default_port(hass: HomeAssistant) -> None:
    """Test config flow uses default port when not specified."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.davinci_fireplace.config_flow.DaVinciFireplaceConfigFlow._test_connection",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100"},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PORT] == DEFAULT_PORT


async def test_form_duplicate_host(hass: HomeAssistant) -> None:
    """Test config flow aborts on duplicate host."""
    # Create first entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.davinci_fireplace.config_flow.DaVinciFireplaceConfigFlow._test_connection",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 10001},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Try to create duplicate
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.davinci_fireplace.config_flow.DaVinciFireplaceConfigFlow._test_connection",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 10001},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
