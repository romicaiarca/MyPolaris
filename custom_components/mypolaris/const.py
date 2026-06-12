"""Constants for MyPolaris integration."""
from datetime import timedelta
from typing import Final

DOMAIN: Final = "mypolaris"
PLATFORMS: Final = ["sensor", "binary_sensor"]

CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_API_KEY: Final = "api_key"
CONF_CAPSOLVER_PROXY: Final = "capsolver_proxy"
CONF_AREA_ID: Final = "area_id"
CONF_SESSION_COOKIE: Final = "session_cookie"
CONF_LOCATIE_ID: Final = "locatie_id"

# Personal CapSolver client key baked in for single-user installs.
# Paste your `CAI-...` or `CAP-...` key between the quotes. Leave empty to require the
# user to provide their own in the config flow.
DEFAULT_API_KEY: Final = ""

DEFAULT_UPDATE_INTERVAL: Final = timedelta(hours=6)
