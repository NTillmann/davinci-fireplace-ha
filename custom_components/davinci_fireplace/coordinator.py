"""Coordinator for DaVinci Fireplace integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    BACKOFF_BASE,
    BACKOFF_MAX,
    COMMAND_DELAY,
    DOMAIN,
    MAX_QUEUE_SIZE,
    REFRESH_PROPERTIES,
    RESPONSE_TIMEOUT,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class DaVinciEntityMixin:
    """Mixin providing common functionality for DaVinci entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    coordinator: "DaVinciCoordinator"  # Set by subclass __init__

    async def async_added_to_hass(self) -> None:
        """Register callback when entity is added."""
        self.coordinator.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback when entity is removed."""
        self.coordinator.unregister_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link entity to device."""
        return self.coordinator.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available (connected to fireplace)."""
        return self.coordinator.state.connected


@dataclass
class FireplaceState:
    """State of the DaVinci fireplace.

    All levels use Home Assistant scales (0-100 or 0-255), not the fireplace's
    native 0-10 scale. Conversion happens in the coordinator and entities.

    Attributes:
        lamp_on: Whether the lamp is powered on.
        lamp_level: Lamp brightness 0-100 (fireplace uses 0-10 internally).
        led_on: Whether the LED is powered on.
        led_rgbw: LED color as (red, green, blue, white), each 0-255.
        flame_on: Whether the flame is on.
        fan_on: Whether the heat fan is powered on.
        fan_speed: Fan speed 0-100 (fireplace uses 0-10 internally).
        connected: Whether we have an active Telnet connection.
    """

    lamp_on: bool = False
    lamp_level: int = 0
    led_on: bool = False
    led_rgbw: tuple[int, int, int, int] = field(default_factory=lambda: (0, 0, 0, 0))
    flame_on: bool = False
    fan_on: bool = False
    fan_speed: int = 0
    connected: bool = False


class DaVinciCoordinator:
    """Coordinator for DaVinci Fireplace Telnet connection.

    This coordinator manages the persistent Telnet connection to the fireplace
    and provides a push-based update model. It does NOT use Home Assistant's
    DataUpdateCoordinator because the fireplace sends unsolicited "HEY" messages
    when state changes (e.g., via physical controls or remote).

    Architecture:
        Three concurrent asyncio tasks run continuously:
        1. _connection_loop: Maintains Telnet connection with auto-reconnect
        2. _command_loop: Processes queued commands with 1s rate limiting
        3. _periodic_refresh_loop: Polls all properties at configured interval

    Push Updates:
        The fireplace sends "HEY <property> <value>" messages when state changes.
        These are parsed and trigger immediate state updates via callbacks.

    Entity Integration:
        Entities register callbacks via register_callback() to receive state
        updates. When state changes, all callbacks are invoked, causing entities
        to call async_write_ha_state() and update the UI.

    Command Queueing:
        Commands are queued via send_command() and processed with 1-second
        delays to avoid overwhelming the fireplace. The queue has a 100-command
        limit; excess commands are dropped with a warning.

    Protocol Notes:
        - Line terminator is CR (\\r), not LF
        - GET responses are correlated by timing, not request ID
        - See PROTOCOL.md for full protocol documentation
    """

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        scan_interval: int,
        entry_id: str,
    ) -> None:
        """Initialize the coordinator."""
        self._hass = hass
        self._host = host
        self._port = port
        self._scan_interval = scan_interval
        self._entry_id = entry_id

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending_get: str | None = None
        self._running: bool = False
        self._callbacks: set[Callable[[], None]] = set()
        self._command_queue: asyncio.Queue[str] = asyncio.Queue()
        self._connection_task: asyncio.Task[None] | None = None
        self._command_task: asyncio.Task[None] | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._reconnect_attempts: int = 0
        self._last_error: str | None = None
        self._last_command: str | None = None  # Track for ERROR context
        self._scheduled_refresh: asyncio.TimerHandle | None = None

        self.state = FireplaceState()

        _LOGGER.debug(
            "Coordinator initialized for %s:%s (scan_interval=%ds)",
            host,
            port,
            scan_interval,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="DaVinci Fireplace",
            manufacturer="Travis Industries",
            model="DaVinci Custom Fireplace",
        )

    @property
    def reconnect_attempts(self) -> int:
        """Return number of reconnection attempts."""
        return self._reconnect_attempts

    @property
    def last_error(self) -> str | None:
        """Return last error message."""
        return self._last_error

    @property
    def command_queue_size(self) -> int:
        """Return current command queue size."""
        return self._command_queue.qsize()

    @property
    def entry_id(self) -> str:
        """Return the config entry ID."""
        return self._entry_id

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback to be called on state updates."""
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """Unregister a callback."""
        self._callbacks.discard(callback)

    def _notify_state_update(self) -> None:
        """Notify all registered callbacks of state change."""
        # Iterate over a copy in case a callback modifies the set
        for callback in list(self._callbacks):
            try:
                callback()
            except Exception:
                _LOGGER.exception("Exception in state update callback")

    def update_scan_interval(self, scan_interval: int) -> None:
        """Update the scan interval."""
        self._scan_interval = scan_interval

    async def async_start(self) -> None:
        """Start the coordinator (called from async_setup_entry)."""
        _LOGGER.debug("Starting coordinator tasks for %s:%s", self._host, self._port)
        self._running = True
        self._connection_task = asyncio.create_task(self._connection_loop())
        self._command_task = asyncio.create_task(self._command_loop())
        self._refresh_task = asyncio.create_task(self._periodic_refresh_loop())

    async def async_stop(self) -> None:
        """Stop the coordinator with proper cleanup (called from async_unload_entry)."""
        self._running = False

        # Cancel scheduled refresh callback
        if self._scheduled_refresh:
            self._scheduled_refresh.cancel()
            self._scheduled_refresh = None

        # Cancel all tasks
        for task in (self._connection_task, self._command_task, self._refresh_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        # Close writer if open
        if self._writer and not self._writer.is_closing():
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()

        # Clear callbacks to prevent memory leaks
        self._callbacks.clear()

        _LOGGER.debug("Coordinator stopped cleanly")

    async def _connection_loop(self) -> None:
        """Main connection loop with exponential backoff."""
        while self._running:
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=10.0,
                )
                self.state.connected = True
                self._reconnect_attempts = 0
                self._last_error = None
                _LOGGER.info("Connected to Telnet interface at %s:%s", self._host, self._port)
                self._notify_state_update()

                # Refresh 10s after connection to allow fireplace to stabilize
                _LOGGER.debug("Scheduling initial state refresh in 10s")
                self._scheduled_refresh = self._hass.loop.call_later(
                    10.0, lambda: asyncio.create_task(self.async_refresh())
                )

                await self._run_session()

                # Session ended - cancel scheduled refresh (prevents stale callback on reconnect)
                if self._scheduled_refresh:
                    self._scheduled_refresh.cancel()
                    self._scheduled_refresh = None

                # Session ended - clear pending GET (response will never arrive)
                self._pending_get = None

                # Session ended - close writer before reconnecting
                if self._writer and not self._writer.is_closing():
                    self._writer.close()
                    with contextlib.suppress(Exception):
                        await self._writer.wait_closed()

            except (ConnectionError, asyncio.TimeoutError, OSError) as ex:
                self.state.connected = False
                self._last_error = str(ex)
                # Exponential backoff - see PROTOCOL.md "Reconnection Strategy"
                delay = min(BACKOFF_BASE * (2 ** self._reconnect_attempts), BACKOFF_MAX)
                self._reconnect_attempts += 1
                _LOGGER.warning(
                    "Connection failed (attempt %d): %s. Retry in %ds",
                    self._reconnect_attempts,
                    ex,
                    delay,
                )
                self._notify_state_update()
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                _LOGGER.exception("Unexpected error in connection loop: %s", ex)
                self._last_error = str(ex)
                await asyncio.sleep(BACKOFF_BASE)

    async def _run_session(self) -> None:
        """Run a connected session, reading responses."""
        await self._read_responses()

    async def _read_responses(self) -> None:
        """Read and parse responses from fireplace."""
        while self._running and self._reader:
            try:
                # NOTE: Fireplace uses CR (\r) as line terminator, not LF
                line = await asyncio.wait_for(
                    self._reader.readuntil(b"\r"),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                continue  # Keep connection alive
            except asyncio.IncompleteReadError:
                _LOGGER.warning("Connection closed by remote")
                break  # Exit loop, trigger reconnect
            except asyncio.CancelledError:
                raise  # Allow clean shutdown
            except Exception as ex:
                _LOGGER.exception("Unexpected error reading: %s", ex)
                break  # Exit loop, trigger reconnect

            line_str = line.decode().rstrip("\r").strip()
            if not line_str or line_str in ("OK", "ERROR"):
                if line_str == "ERROR":
                    _LOGGER.warning(
                        "Fireplace returned ERROR (last command: %s)",
                        self._last_command or "unknown",
                    )
                continue

            if line_str.startswith("HEY "):
                # HEY format: "HEY <property> <value>"
                self._handle_hey_message(line_str[4:])
            elif self._pending_get:
                _LOGGER.debug(
                    "Received response for %s: %s", self._pending_get, line_str
                )
                self._handle_get_response(self._pending_get, line_str)
                self._pending_get = None
            else:
                # Responses may arrive without a pending GET if commands overlap.
                # Safe to ignore - see PROTOCOL.md "Edge Cases".
                _LOGGER.debug("Ignoring unsolicited message: %s", line_str)

    def _handle_hey_message(self, message: str) -> None:
        """Handle unsolicited HEY message from fireplace."""
        # Format: "<property> <value>" - split on first space
        parts = message.split(" ", 1)
        if len(parts) == 2:
            _LOGGER.debug("Received push update: HEY %s", message)
            self._handle_get_response(parts[0], parts[1])
        else:
            _LOGGER.debug("Malformed HEY message: %s", message)

    def _handle_get_response(self, property_name: str, value: str) -> None:
        """Handle response to a GET command with defensive parsing."""
        try:
            if property_name == "LAMP":
                new_value = value == "ON"
                if self.state.lamp_on != new_value:
                    _LOGGER.debug("State change: lamp_on %s → %s", self.state.lamp_on, new_value)
                self.state.lamp_on = new_value
            elif property_name == "LAMPLEVEL":
                # May receive "ON" instead of integer if responses arrive out of
                # order due to timing. Caught by ValueError below.
                new_value = int(value) * 10  # 0-10 → 0-100
                if self.state.lamp_level != new_value:
                    _LOGGER.debug("State change: lamp_level %d → %d", self.state.lamp_level, new_value)
                self.state.lamp_level = new_value
                # Implicit ON/OFF: infer power state from level (see PROTOCOL.md)
                if new_value > 0 and not self.state.lamp_on:
                    _LOGGER.debug("State change: lamp_on False → True (implicit from LAMPLEVEL)")
                    self.state.lamp_on = True
                elif new_value == 0 and self.state.lamp_on:
                    _LOGGER.debug("State change: lamp_on True → False (implicit from LAMPLEVEL=0)")
                    self.state.lamp_on = False
            elif property_name == "LED":
                new_value = value == "ON"
                if self.state.led_on != new_value:
                    _LOGGER.debug("State change: led_on %s → %s", self.state.led_on, new_value)
                self.state.led_on = new_value
            elif property_name == "LEDCOLOR":
                # LEDCOLOR returns "OFF" when LED is off (see PROTOCOL.md)
                if value == "OFF":
                    if self.state.led_on:
                        _LOGGER.debug("State change: led_on True → False (LEDCOLOR=OFF)")
                    self.state.led_on = False
                else:
                    new_value = self._parse_ledcolor(value)
                    if self.state.led_rgbw != new_value:
                        _LOGGER.debug("State change: led_rgbw %s → %s", self.state.led_rgbw, new_value)
                    self.state.led_rgbw = new_value
                    # Implicit ON/OFF: non-zero color means on, all-zeros means off
                    if any(new_value) and not self.state.led_on:
                        _LOGGER.debug("State change: led_on False → True (implicit from LEDCOLOR)")
                        self.state.led_on = True
                    elif not any(new_value) and self.state.led_on:
                        _LOGGER.debug("State change: led_on True → False (implicit from LEDCOLOR=0,0,0,0)")
                        self.state.led_on = False
            elif property_name == "FLAME":
                new_value = value == "ON"
                if self.state.flame_on != new_value:
                    _LOGGER.debug("State change: flame_on %s → %s", self.state.flame_on, new_value)
                self.state.flame_on = new_value
            elif property_name == "HEATFAN":
                new_value = value == "ON"
                if self.state.fan_on != new_value:
                    _LOGGER.debug("State change: fan_on %s → %s", self.state.fan_on, new_value)
                self.state.fan_on = new_value
            elif property_name == "HEATFANSPEED":
                # May receive "ON" instead of integer if responses arrive out of
                # order due to timing. Caught by ValueError below.
                new_value = int(value) * 10  # 0-10 → 0-100
                if self.state.fan_speed != new_value:
                    _LOGGER.debug("State change: fan_speed %d → %d", self.state.fan_speed, new_value)
                self.state.fan_speed = new_value
                # Implicit ON/OFF: infer power state from speed (see PROTOCOL.md)
                if new_value > 0 and not self.state.fan_on:
                    _LOGGER.debug("State change: fan_on False → True (implicit from HEATFANSPEED)")
                    self.state.fan_on = True
                elif new_value == 0 and self.state.fan_on:
                    _LOGGER.debug("State change: fan_on True → False (implicit from HEATFANSPEED=0)")
                    self.state.fan_on = False
            elif property_name == "LEDBRIGHTNESS":
                # LEDBRIGHTNESS is a derived value; LEDCOLOR already includes it
                _LOGGER.debug("LEDBRIGHTNESS=%s (acknowledged, no action needed)", value)
                return  # No state change, don't notify
            else:
                _LOGGER.debug("Unknown property in response: %s=%s", property_name, value)
                return  # Don't notify for unknown properties
        except (ValueError, IndexError) as ex:
            # Out-of-order responses can cause parse errors. Preserve previous state.
            _LOGGER.debug("Parse error for %s=%s: %s", property_name, value, ex)
            return

        self._notify_state_update()

    def _parse_ledcolor(self, value: str) -> tuple[int, int, int, int]:
        """Parse LEDCOLOR response: 'RED: 255 GREEN: 128 BLUE: 0 WHITE: 50'."""
        pattern = r"RED:\s*(\d+)\s+GREEN:\s*(\d+)\s+BLUE:\s*(\d+)\s+WHITE:\s*(\d+)"
        match = re.match(pattern, value)
        if not match:
            raise ValueError(f"Invalid LEDCOLOR format: {value}")
        r, g, b, w = (int(x) for x in match.groups())
        return (r, g, b, w)

    async def _command_loop(self) -> None:
        """Process command queue with rate limiting."""
        while self._running:
            try:
                cmd = await self._command_queue.get()

                # If this is a GET command, wait for any pending GET response first.
                # This prevents response misattribution - see PROTOCOL.md
                # "Sequential Request Model". Wait up to RESPONSE_TIMEOUT.
                if cmd.startswith("GET "):
                    wait_interval = 0.1
                    max_iterations = int(RESPONSE_TIMEOUT / wait_interval)
                    for _ in range(max_iterations):
                        if self._pending_get is None:
                            break
                        await asyncio.sleep(wait_interval)
                    else:
                        _LOGGER.debug(
                            "Timeout waiting for GET %s response, proceeding anyway",
                            self._pending_get,
                        )

                await self._send_command_internal(cmd)
                await asyncio.sleep(COMMAND_DELAY)
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                _LOGGER.exception("Error in command loop: %s", ex)

    async def _send_command_internal(self, cmd: str) -> None:
        """Send a command to the fireplace."""
        if self._writer is None or self._writer.is_closing():
            _LOGGER.warning("Cannot send command (not connected): %s", cmd)
            return
        try:
            self._last_command = cmd
            # Track GET commands for response correlation - MUST be set when
            # SENDING, not when queuing. See PROTOCOL.md "Response Correlation".
            if cmd.startswith("GET "):
                self._pending_get = cmd[4:]
            self._writer.write(f"{cmd}\r".encode())
            await self._writer.drain()
            _LOGGER.debug("Sent: %s", cmd)
        except (ConnectionError, OSError) as ex:
            _LOGGER.warning("Send failed for '%s': %s", cmd, ex)
            # Connection loop will handle reconnect

    async def send_command(self, cmd: str) -> None:
        """Queue a command to send to the fireplace.

        Commands are queued and sent with 1-second delays between them.
        This is NOT immediate - use for fire-and-forget commands.

        Valid commands:
            SET LAMP ON|OFF
            SET LAMPLEVEL 0-10
            SET LED ON|OFF
            SET LEDCOLOR r,g,b,w  (each 0-255, comma-separated)
            SET FLAME ON|OFF
            SET HEATFAN ON|OFF
            SET HEATFANSPEED 0-10
            GET <property>  (use async_refresh_property instead)

        Args:
            cmd: The raw command string (without \\r terminator).
        """
        queue_size = self._command_queue.qsize()
        if queue_size >= MAX_QUEUE_SIZE:
            _LOGGER.warning(
                "Command queue full (%d commands), dropping: %s", queue_size, cmd
            )
            return
        if queue_size > MAX_QUEUE_SIZE // 2:
            _LOGGER.debug(
                "Command queue growing: %d/%d commands", queue_size, MAX_QUEUE_SIZE
            )
        await self._command_queue.put(cmd)

    async def _send_get(self, property_name: str) -> None:
        """Queue a GET command for sending.

        Note: _pending_get is set in _send_command_internal when the command
        is actually SENT, not here when queued. The wait-for-pending logic
        is in _command_loop to ensure sequential request handling.
        """
        await self.send_command(f"GET {property_name}")

    async def async_refresh(self) -> None:
        """Queue all properties for refresh."""
        for prop in REFRESH_PROPERTIES:
            await self._send_get(prop)

    async def async_refresh_property(self, *props: str) -> None:
        """Queue specific properties for refresh.

        Args:
            *props: Property names to refresh. Valid values:
                LAMP, LAMPLEVEL, LED, LEDCOLOR, FLAME, HEATFAN, HEATFANSPEED
        """
        for prop in props:
            await self._send_get(prop)

    async def _periodic_refresh_loop(self) -> None:
        """Periodically refresh state from fireplace."""
        while self._running:
            try:
                await asyncio.sleep(self._scan_interval)
                if self.state.connected:
                    _LOGGER.debug(
                        "Starting periodic refresh (interval=%ds)", self._scan_interval
                    )
                    await self.async_refresh()
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                _LOGGER.exception("Error in periodic refresh: %s", ex)
