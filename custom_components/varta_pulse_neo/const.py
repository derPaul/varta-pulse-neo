"""Constants for the VARTA pulse neo integration."""

from __future__ import annotations

DOMAIN = "varta_pulse_neo"
MANUFACTURER = "VARTA"
MODEL = "pulse neo"

CONF_UNIT_ID = "unit_id"
CONF_WEB_HTTPS = "web_https"

DEFAULT_NAME = "VARTA pulse neo"
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 255
DEFAULT_WEB_USERNAME = "user1"
DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300

# Battery state as reported in register 1065.
BATTERY_STATES: dict[int, str] = {
    0: "busy",
    1: "run",
    2: "charge",
    3: "discharge",
    4: "standby",
    5: "error",
    6: "passive",
    7: "islanding",
}
