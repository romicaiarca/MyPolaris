"""The MyPolaris integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CONF_API_KEY,
    CONF_AREA_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SESSION_COOKIE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    INTEGRATION_AUTHOR,
    PLATFORMS,
)
from .coordinator import MyPolarisCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MyPolaris from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    default_interval_minutes = int(DEFAULT_UPDATE_INTERVAL.total_seconds() // 60)
    update_interval = timedelta(
        minutes=entry.options.get("update_interval_minutes", default_interval_minutes)
    )

    api_key = entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY, "")
    session_cookie = (
        entry.options.get(CONF_SESSION_COOKIE)
        or entry.data.get(CONF_SESSION_COOKIE, "")
    )
    session = async_create_clientsession(
        hass,
        cookie_jar=aiohttp.DummyCookieJar(),
    )

    coordinator = MyPolarisCoordinator(
        hass,
        entry.data[CONF_EMAIL],
        entry.data.get(CONF_PASSWORD, ""),
        api_key,
        update_interval,
        session,
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
    locatii = (coordinator.data or {}).get("locatii") or []
    _remove_stale_location_devices(hass, entry, {str(loc["id"]) for loc in locatii})
    for loc in locatii:
        device = device_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_{loc['id']}")},
            manufacturer=INTEGRATION_AUTHOR,
            name=f"MyPolaris — {loc.get('denumire') or loc['id']}",
            model=f"PdL {loc['id']}",
            configuration_url="https://my.polaris.ro",
        )
        if area_id and device.area_id != area_id:
            device_reg.async_update_device(device.id, area_id=area_id)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _remove_stale_location_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    valid_location_ids: set[str],
) -> None:
    """Remove stale per-PdL devices left behind by an earlier wrong session."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)
    valid_identifiers = {
        (DOMAIN, f"{entry.entry_id}_{location_id}")
        for location_id in valid_location_ids
    }
    entry_prefix = f"{entry.entry_id}_"

    for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        mypolaris_identifiers = {
            identifier
            for identifier in device.identifiers
            if identifier[0] == DOMAIN and identifier[1].startswith(entry_prefix)
        }
        if not mypolaris_identifiers or mypolaris_identifiers & valid_identifiers:
            continue

        for entity in er.async_entries_for_device(
            entity_reg,
            device.id,
            include_disabled_entities=True,
        ):
            if entity.platform == DOMAIN and entity.config_entry_id == entry.entry_id:
                entity_reg.async_remove(entity.entity_id)
        device_reg.async_remove_device(device.id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: MyPolarisCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()
        await coordinator.session.close()

    return unload_ok
