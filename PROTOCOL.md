# DaVinci Fireplace Serial Protocol

This document describes the serial communication protocol for DaVinci Custom Fireplaces as understood and implemented by this integration.

> **Important:** This is an independent, community-developed reference—not official Travis Industries documentation. The information here is derived from publicly available PDFs (linked below), observed device behavior, and implementation choices made for this driver. Protocol details may vary by firmware version or hardware configuration. Timing parameters and rate limiting are conventions adopted by this implementation and may not reflect official specifications. Use at your own risk.

> **Note:** The IFC board has a TTL serial interface, not Ethernet. To control the fireplace over a network, you need a Telnet interface — a serial-to-Ethernet/Telnet converter (e.g., USR-TCP232). This document describes the protocol as seen over that Telnet connection, but the underlying communication is serial.

## Connection Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Transport | TCP/Telnet | Raw TCP socket |
| Port | User-configured (commonly 10001) | No default in protocol |
| Line Terminator | CR (`\r`, ASCII 13) | **Not LF or CRLF** |
| Encoding | ASCII | Plain text |

### Connection Behavior

- The Telnet interface acts as the Telnet server
- Single connection at a time (most Telnet interfaces only support one client)
- Connection may drop unexpectedly; client must handle reconnection
- After successful connection, wait 10 seconds before sending refresh commands

## Command Format

All commands are plain text terminated with CR (`\r`).

### SET Command

```
SET <property> <value>\r
```

**Response:** `OK` or `ERROR`

### GET Command

```
GET <property>\r
```

**Response:** The property value (format varies by property)

## Response Format

Responses are terminated with CR (`\r`).

| Response | Meaning |
|----------|---------|
| `OK` | Command succeeded |
| `ERROR` | Command failed |
| `<value>` | Response to GET command |
| `HEY <property> <value>` | Unsolicited push notification |

### Push Notifications (HEY Messages)

The fireplace sends unsolicited `HEY` messages when state changes occur (e.g., via physical controls or remote).

Format:
```
HEY <property> <value>\r
```

Example:
```
HEY LAMP ON
HEY FLAME OFF
HEY LEDCOLOR RED: 255 GREEN: 0 BLUE: 128 WHITE: 0
```

The `<value>` portion uses the same format as GET responses.

## Properties

### LAMP (On/Off Switch)

Controls the main lamp power.

| Command | Description |
|---------|-------------|
| `SET LAMP ON` | Turn lamp on |
| `SET LAMP OFF` | Turn lamp off |
| `GET LAMP` | Query lamp state |

**GET Response:** `ON` or `OFF`

### LAMPLEVEL (Brightness)

Controls lamp brightness level.

| Command | Description |
|---------|-------------|
| `SET LAMPLEVEL <n>` | Set brightness (0-10) |
| `GET LAMPLEVEL` | Query brightness |

**GET Response:** Integer `0` to `10`

**Notes:**
- Setting level to 0 does NOT automatically turn off the lamp
- Client should send `SET LAMP OFF` after `SET LAMPLEVEL 0`
- Conversely, setting level > 0 does NOT automatically turn on the lamp
- Client should send `SET LAMP ON` after setting a non-zero level

### LED (On/Off Switch)

Controls the LED power.

| Command | Description |
|---------|-------------|
| `SET LED ON` | Turn LED on |
| `SET LED OFF` | Turn LED off |
| `GET LED` | Query LED state |

**GET Response:** `ON` or `OFF`

### LEDCOLOR (RGBW Color)

Controls the LED color.

| Command | Description |
|---------|-------------|
| `SET LEDCOLOR <r>,<g>,<b>,<w>` | Set RGBW color |
| `GET LEDCOLOR` | Query current color |

**SET Format:** Comma-separated integers, each 0-255
```
SET LEDCOLOR 255,128,64,32
```

**GET Response:** Space-separated labeled values, or `OFF`
```
RED: 255 GREEN: 128 BLUE: 64 WHITE: 32
```
or
```
OFF
```

**Notes:**
- **SET and GET use different formats** - SET is comma-separated, GET is labeled
- GET returns `OFF` when the LED is off (not the last color)
- Setting all values to 0 does NOT automatically turn off the LED
- Client should send `SET LED OFF` when setting `0,0,0,0`
- The white channel is independent of RGB
- For white-only mode: set RGB to 0 and use white channel (e.g., `0,0,0,255`)

### FLAME (On/Off Switch)

Controls the fireplace flame.

| Command | Description |
|---------|-------------|
| `SET FLAME ON` | Turn flame on |
| `SET FLAME OFF` | Turn flame off |
| `GET FLAME` | Query flame state |

**GET Response:** `ON` or `OFF`

### HEATFAN (On/Off Switch)

Controls the heat fan power.

| Command | Description |
|---------|-------------|
| `SET HEATFAN ON` | Turn fan on |
| `SET HEATFAN OFF` | Turn fan off |
| `GET HEATFAN` | Query fan state |

**GET Response:** `ON` or `OFF`

### HEATFANSPEED (Speed Level)

Controls the heat fan speed.

| Command | Description |
|---------|-------------|
| `SET HEATFANSPEED <n>` | Set speed (0-10) |
| `GET HEATFANSPEED` | Query speed |

**GET Response:** Integer `0` to `10`

**Notes:**
- Setting speed to 0 does NOT automatically turn off the fan
- Client should send `SET HEATFAN OFF` after `SET HEATFANSPEED 0`
- Conversely, setting speed > 0 does NOT automatically turn on the fan
- Client should send `SET HEATFAN ON` after setting a non-zero speed

## Timing & Rate Limiting

| Parameter | Value | Notes |
|-----------|-------|-------|
| Command delay | 1 second | Minimum time between commands |
| GET response timeout | 2 seconds | Time to wait for GET response |
| Post-connect refresh delay | 10 seconds | Wait before first refresh |
| Command queue limit | 100 | Drops commands when queue reaches 100 |

### Rate Limiting

Commands should be sent with at least 1 second between them.

### Response Correlation

Response correlation relies on timing:

1. Send `GET <property>`
2. Track which property was requested
3. Next non-HEY, non-OK/ERROR response is the answer
4. If no response within 2 seconds, assume timeout

If a HEY message arrives between a GET request and its response, the client should handle this gracefully.

## Reconnection Strategy

Use exponential backoff: `min(10 * 2^n, 3600)` seconds, where `n` starts at 0. Starts at 10s, caps at 1 hour. Reset counter on successful connection.

## Security Considerations

The Telnet protocol does not include authentication. Ensure your network is properly secured and consider isolating IoT devices on a separate VLAN.

## Protocol Notes

This section documents protocol behavior discovered through testing and reverse-engineering. Items are organized by category for clarity.

### Observed Behavior

#### Error Responses

The fireplace returns `ERROR` for failed commands. Clients should log errors accordingly.

### Response Behavior

#### LEDCOLOR When Off

When the LED is off, `GET LEDCOLOR` returns `OFF` instead of color values. This correctly reflects that no color is currently displayed. When the LED turns on, it will display the last-set color.

#### Implicit ON from Level Changes

When state changes via physical controls or RF remote, the fireplace sends level/color changes but may not send explicit ON messages:
- Turning on via dimmer: `HEY LAMPLEVEL 5` (no `HEY LAMP ON`)
- Turning on via color: `HEY LEDCOLOR RED: 255 ...` (no `HEY LED ON`)
- Turning off: `HEY LAMP OFF` is sent explicitly

Clients should infer ON state from non-zero levels:
- `LAMPLEVEL > 0` → lamp is on
- `LEDCOLOR` with any non-zero value → LED is on
- `HEATFANSPEED > 0` → fan is on

### Additional Properties

#### LEDBRIGHTNESS

The fireplace sends `HEY LEDBRIGHTNESS <n>` messages (values 0-100) when LED brightness changes. This is a derived value—the LEDCOLOR values already reflect brightness. Clients should acknowledge but ignore this property to avoid state drift.

### Client Implementation Notes

These notes help client developers handle the protocol correctly.

#### Response Parsing

If commands overlap or responses are delayed, a response may not match the expected format for the pending GET. Handle parse variations gracefully and preserve previous state.

#### Message Parsing

- Trim leading/trailing whitespace before parsing
- Responses are case-sensitive: exactly `ON` or `OFF` (uppercase)
- LEDCOLOR format is strict: `RED: <n> GREEN: <n> BLUE: <n> WHITE: <n>`

#### Scale Conversion

When converting between scales, use rounding:
- 0-100 to 0-10: `round(level / 10)`
- 0-100 to 0-255: `round(level * 2.55)`

#### Recommended Command Order

Send level/color commands BEFORE power commands:
```
SET LAMPLEVEL 5
SET LAMP ON
```
This prevents brief flashes at the previous level.

### Hardware Capabilities

- **Instant brightness changes**: This integration does not implement fade transitions (though the protocol may support `LEDFADETIME` on some models)
- **White channel**: The 0-255 value controls intensity

### Other Messages

The fireplace may occasionally send messages that are neither GET responses nor HEY-prefixed. These can be logged at debug level and ignored.

## Example Session

```
# Client connects to Telnet interface at <ip>:10001

# Client sends refresh commands (1 second apart)
> GET LAMP\r
< ON\r
> GET LAMPLEVEL\r
< 7\r
> GET LED\r
< ON\r
> GET LEDCOLOR\r
< RED: 255 GREEN: 128 BLUE: 64 WHITE: 0\r
> GET FLAME\r
< ON\r
> GET HEATFAN\r
< ON\r
> GET HEATFANSPEED\r
< 5\r

# Client turns off lamp
> SET LAMP OFF\r
< OK\r

# Fireplace push notification (user turned flame off via remote)
< HEY FLAME OFF\r

# Client sets LED color
> SET LEDCOLOR 0,255,0,0\r
< OK\r
> SET LED ON\r
< OK\r

# Client queries LED (now on with green color)
> GET LEDCOLOR\r
< RED: 0 GREEN: 255 BLUE: 0 WHITE: 0\r
```

## Additional Features in Official Documentation

The official Travis Industries documentation describes features that may not be present on all hardware configurations or that this integration does not implement:

| Property | Description | Status |
|----------|-------------|--------|
| `VERSION` | Query firmware version | Not implemented |
| `AT` | Connection test (returns OK) | Not implemented |
| `LEDFADETIME` | Fade transition time (0-32767 ms) | Not implemented |
| `LEDDWELLTIME` | Color dwell time before transition | Not implemented |
| `LEDPULSE` | Pulsing animation effect | Not implemented |
| `FLAMELEVEL` | Variable flame intensity (1-10) | Not present on all models |
| `HUMIDITY` | Humidity sensor reading | Not present on all models |
| `TEMPERATURE` | Temperature sensor reading | Not present on all models |
| `DEWPOINT` | Calculated dewpoint | Not present on all models |
| `AUXBURNER` | Auxiliary burner control | Not present on all models |

> **Note:** This integration implements the core features (lamp, LED, flame, heat fan) that are common across DaVinci fireplaces. Additional features may be available depending on your specific hardware configuration and firmware version.

## References

- Manufacturer: Travis Industries
- Product: DaVinci Custom Fireplace with IFC board
