"""The MyPolaris integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_AREA_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SESSION_COOKIE,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MyPolarisCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MyPolaris from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    update_interval = timedelta(
        minutes=entry.options.get("update_interval_minutes", 30)
    )

    api_key = entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY, "")
    session_cookie = entry.options.get(CONF_SESSION_COOKIE) or entry.data.get(CONF_SESSION_COOKIE, "")

    coordinator = MyPolarisCoordinator(
        hass,
        entry.data[CONF_EMAIL],
        entry.data.get(CONF_PASSWORD, ""),
        api_key,
        update_interval,
        async_get_clientsession(hass),
        session_cookie=session_cookie,
    )
    coordinator.config_entry_id = entry.entry_id
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start_keepalive()
    entry.async_on_unload(coordinator.async_stop_keepalive)

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register one device per location so each PdL shows up grouped in HA.
    area_id = entry.options.get(CONF_AREA_ID) or entry.data.get(CONF_AREA_ID)
    device_reg = dr.async_get(hass)
    for loc in (coordinator.data or {}).get("locatii") or []:
        device = device_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_{loc['id']}")},
            manufacturer="Polaris",
            name=f"MyPolaris — {loc.get('denumire') or loc['id']}",
            model=f"PdL {loc['id']}",
            configuration_url="https://my.polaris.ro",
        )
        if area_id and device.area_id != area_id:
            device_reg.async_update_device(device.id, area_id=area_id)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok