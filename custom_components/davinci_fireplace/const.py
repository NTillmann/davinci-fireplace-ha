"""Constants for DaVinci Fireplace integration.

See PROTOCOL.md for full protocol documentation.
"""

from __future__ import annotations

DOMAIN = "davinci_fireplace"
DEFAULT_PORT = 10001
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes

# Exponential backoff for reconnection
# Formula: min(BACKOFF_BASE * 2^attempt, BACKOFF_MAX)
# Sequence: 10s, 20s, 40s, 80s, 160s, 320s, 640s, 1280s, 2560s, 3600s (max)
BACKOFF_BASE = 10  # seconds
BACKOFF_MAX = 3600  # 1 hour max

# Telnet protocol timing
COMMAND_DELAY = 1.0  # seconds between commands (rate limit)
RESPONSE_TIMEOUT = 2.0  # seconds to wait for GET response

# Command queue - drops commands when exceeded to prevent memory issues
MAX_QUEUE_SIZE = 100

# Properties to refresh on connect and periodically
# Order matters: query power state before level for correct interpretation
REFRESH_PROPERTIES = [
    "LAMP",
    "LAMPLEVEL",
    "LED",
    "LEDCOLOR",
    "FLAME",
    "HEATFAN",
    "HEATFANSPEED",
]

# Configuration keys
CONF_SCAN_INTERVAL = "scan_interval"
