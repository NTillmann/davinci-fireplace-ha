# DaVinci Fireplace Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/NTillmann/davinci-fireplace-ha.svg)](https://github.com/NTillmann/davinci-fireplace-ha/releases)
[![License](https://img.shields.io/github/license/NTillmann/davinci-fireplace-ha.svg)](LICENSE)

A Home Assistant custom component for controlling [DaVinci Custom Fireplaces](https://www.davincifireplace.com/) — luxury linear gas fireplaces by Travis Industries. The fireplace's IFC (Intelligent Fireplace Controller) board provides a serial interface that can be bridged to your network via a Telnet interface (serial-to-Ethernet converter).

## Requirements

- Home Assistant 2024.1.0 or newer
- DaVinci Custom Fireplace with IFC (Intelligent Fireplace Controller) board
- **Serial-to-Ethernet converter** — The fireplace's IFC board has a TTL serial interface, not Ethernet. You'll need a serial-to-Ethernet/Telnet converter (e.g., USR-TCP232 or similar) to bridge it to your network. Some converters require an RS232 level shifter if they don't support TTL directly.

## Disclaimer

**This is an independent, community-developed project.** It is not affiliated with, endorsed by, sponsored by, or in any way officially connected with Travis Industries, Inc., DaVinci Custom Fireplaces, or any of their subsidiaries or affiliates.

The names "DaVinci," "DaVinci Custom Fireplaces," and "Travis Industries" as well as related names, marks, emblems, and images are registered trademarks of their respective owners.

This software is provided "as is," without warranty of any kind, express or implied. Use of this integration is entirely at your own risk. The authors assume no liability for any damages, including but not limited to property damage, personal injury, or any other losses arising from the use of this software or the control of fireplace equipment.

**Always follow the manufacturer's safety guidelines when operating your fireplace.**

## Resources

- [IFC Serial Interface - Current (PDF)](https://www.travisindustries.com/docs/17601989.pdf) — Official Travis Industries documentation
- [IFC Serial Interface - Older Version (PDF)](https://www.travisindustries.com/docs/17601989-old.pdf) — Earlier revision (contains protocol details)

## Features

- **Flame Control**: On/off switch for the fireplace flame
- **Lamp Control**: Dimmable light for the fireplace lamp (0-100%)
- **LED Control**: RGBW accent lighting
- **Heat Fan**: Fan with 10-speed control

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add `https://github.com/NTillmann/davinci-fireplace-ha` as an Integration
5. Click "Add"
6. Search for "DaVinci Fireplace" and install
7. Restart Home Assistant

### Manual Installation

1. Download the `custom_components/davinci_fireplace` folder
2. Copy it to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **Add Integration**
3. Search for "DaVinci Fireplace"
4. Enter your Telnet interface's IP address and port (default: 10001)
5. Click **Submit**

> **Tip:** The IP address is that of your Telnet interface (serial-to-Ethernet converter), not the fireplace itself. Check your router's DHCP client list or your device's configuration utility. The port depends on your Telnet interface's settings.

### Options

After setup, you can configure:
- **Refresh interval**: How often to poll the fireplace state (1, 5, 15, or 30 minutes)

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `switch.davinci_fireplace_flame` | Switch | Fireplace flame on/off |
| `light.davinci_fireplace_lamp` | Light | Dimmable lamp (10 brightness levels) |
| `light.davinci_fireplace_led` | Light | RGBW LED with color and white control |
| `fan.davinci_fireplace_heat_fan` | Fan | Heat fan with 10 speed levels |

### LED Light Modes

The LED light supports both RGB color and a separate white channel:
- **Color mode**: Use the color picker to set RGB values (white channel = 0)
- **White mode**: Set RGB to black and adjust white brightness

## Protocol

The integration connects to your Telnet interface, which relays commands to the fireplace's IFC board over serial:

- Commands: `SET <property> <value>` and `GET <property>`
- Responses: `OK`, `ERROR`, or the property value
- Push messages: `HEY <property> <value>` for unsolicited state updates

For full protocol documentation, see [PROTOCOL.md](PROTOCOL.md).

## Connection Handling

- Automatic reconnection with exponential backoff (10s, 20s, 40s, ... up to 1 hour)
- Entities show as "unavailable" when disconnected
- State refresh 10 seconds after reconnection
- Configurable periodic refresh (default: 5 minutes)

## Notes

- **Instant brightness changes** — This integration does not implement fade transitions
- **Single connection** — The serial-to-Ethernet converter typically supports one client at a time
- **10-step controls** — Lamp brightness and fan speed use 10 discrete levels

## Troubleshooting

### Cannot connect

1. Verify the Telnet interface's IP address and port are correct
2. Ensure the port is not blocked by a firewall
3. Check that the Telnet interface is powered and connected to your network
4. Check that the fireplace is powered on
5. Verify the serial connection between the Telnet interface and IFC board
6. Try connecting manually: `telnet <ip> <port>`

### Entities show as unavailable

The integration cannot reach the Telnet interface. Check:
- Telnet interface network connectivity and power
- Fireplace power
- Serial cable connection between Telnet interface and IFC board
- Home Assistant logs for connection errors

### Enabling debug logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.davinci_fireplace: debug
```

## Contributing

- Report issues via [GitHub Issues](https://github.com/NTillmann/davinci-fireplace-ha/issues)
- Pull requests welcome

## License

MIT License
