"""Config flow for DaVinci Fireplace integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import CONF_SCAN_INTERVAL, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class DaVinciFireplaceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for DaVinci Fireplace."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            _LOGGER.debug("Testing connection to fireplace at %s:%s", host, port)

            # Validate connection before accepting
            try:
                await self._test_connection(host, port)
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Connection test timed out for %s:%s (5s timeout)", host, port
                )
                errors["base"] = "cannot_connect"
            except OSError as ex:
                _LOGGER.warning("Connection test failed for %s:%s: %s", host, port, ex)
                errors["base"] = "cannot_connect"
            else:
                _LOGGER.info("Connection test successful for %s:%s", host, port)
                # Create unique ID from IP to prevent duplicates
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="DaVinci Fireplace",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

    async def _test_connection(self, host: str, port: int) -> None:
        """Test Telnet connection with 5s timeout."""
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0,
        )
        writer.close()
        await writer.wait_closed()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return DaVinciOptionsFlow()


class DaVinciOptionsFlow(OptionsFlow):
    """Handle options for DaVinci Fireplace."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            _LOGGER.debug("Options flow saving: %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.In(
                        {
                            60: "1 minute",
                            300: "5 minutes",
                            900: "15 minutes",
                            1800: "30 minutes",
                        }
                    ),
                }
            ),
        )
