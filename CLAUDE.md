# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom component for DaVinci Custom Fireplaces. Communicates via Telnet protocol to a serial-to-Ethernet adapter connected to the fireplace's IFC board.

## Commands

### Run Tests
```bash
# All tests
pytest tests/

# Single test file
pytest tests/test_coordinator.py

# Single test
pytest tests/test_coordinator.py::TestCoordinatorParsing::test_parse_ledcolor_valid

# With verbose output
pytest -v tests/
```

#### Windows Note
The `pytest-homeassistant-custom-component` plugin crashes on Windows (requires Unix-only `fcntl` module). To run coordinator tests on Windows:

```bash
# Temporarily uninstall the HA test plugin
pip uninstall pytest-homeassistant-custom-component -y

# Run tests (coordinator tests will pass, config_flow tests will error due to missing 'hass' fixture)
pytest -v tests/

# Reinstall if needed
pip install pytest-homeassistant-custom-component
```

Config flow tests require the full HA test environment (Linux only).

### Type Checking / Linting
```bash
# If using ruff
ruff check custom_components/

# If using mypy
mypy custom_components/davinci_fireplace/
```

### Manual Testing
Copy `custom_components/davinci_fireplace/` to Home Assistant's `config/custom_components/` and restart HA.

## Architecture

### Core Components

**coordinator.py** - Central hub managing everything:
- `DaVinciCoordinator`: Telnet connection lifecycle, command queue (1s rate limit), response parsing, push message handling (HEY), exponential backoff reconnection
  - Runs three concurrent asyncio tasks: `_connection_loop` (maintains connection), `_command_loop` (rate-limited sending), `_periodic_refresh_loop` (polling)
- `FireplaceState`: Dataclass holding all device state (lamp, LED, flame, fan)
- `DaVinciEntityMixin`: Shared entity functionality (availability, device_info, callback registration)

**Entity files** (light.py, switch.py, fan.py) - Thin wrappers that:
- Read state from `coordinator.state.*`
- Call `coordinator.send_command()` for actions
- Call `coordinator.async_refresh_property()` after commands

### Data Flow

```
User Action → Entity.async_turn_on() → coordinator.send_command("SET ...")
                                                    ↓
                                          Command Queue (1s spacing)
                                                    ↓
                                    Telnet → Telnet Interface → Serial → IFC Board
                                                    ↓
IFC Board Response → coordinator._handle_get_response() → state update
                                                    ↓
                            coordinator._notify_state_update() → entity callbacks
                                                    ↓
                                          HA UI updates
```

### Protocol Essentials

- **Line terminator**: CR (`\r`), not LF
- **Commands**: `SET <prop> <value>` and `GET <prop>`
- **Push messages**: `HEY <prop> <value>` (unsolicited state changes)
- **Scale conversions**: Fireplace uses 0-10, HA uses 0-100 (fan) or 0-255 (light brightness)
- **Important**: Power and intensity are separate. Must pair `SET LAMPLEVEL 5` with `SET LAMP ON`

See PROTOCOL.md for full protocol documentation.

### Config Flow

- `config_flow.py`: Tests Telnet connection before accepting config
- `strings.json` / `translations/en.json`: UI strings (must stay in sync)
- Options flow allows changing refresh interval after setup

## Testing Notes

- `tests/conftest.py` provides fixtures: `mock_hass`, `coordinator`, `mock_connection`
- Config flow tests require HA test fixtures (`hass: HomeAssistant`)
- Coordinator tests can run without HA fixtures using the mock_hass fixture

## Key Files

| File | Purpose |
|------|---------|
| coordinator.py | Telnet connection, state management, command queue |
| const.py | Constants: timing, backoff, property list |
| diagnostics.py | HA diagnostics support (state dump for troubleshooting) |
| PROTOCOL.md | Full protocol documentation |
| manifest.json | HA integration metadata, HACS compatibility |
| hacs.json | HACS custom repository metadata |

## Git Conventions

- Never add a "Co-Authored-By: Claude" line to commit messages
