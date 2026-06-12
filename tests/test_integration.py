"""Integration lifecycle tests for MyPolaris."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.mypolaris as integration
from custom_components.mypolaris.const import CONF_EMAIL, CONF_SESSION_COOKIE, DOMAIN, PLATFORMS

pytestmark = pytest.mark.asyncio


class _FakeCoordinator:
    def __init__(self) -> None:
        self.email = "user@example.com"
        self.data = {
            "locatii": [
                {"id": "100", "denumire": "Sediul Social"},
            ]
        }
        self.config_entry_id: str | None = None
        self.async_config_entry_first_refresh = AsyncMock()
        self.async_start_keepalive = MagicMock()
        self.async_stop_keepalive = MagicMock()
        self.async_unload = AsyncMock()
        self.session = MagicMock()
        self.session.close = AsyncMock()


async def test_async_setup_entry_registers_coordinator_and_devices(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_SESSION_COOKIE: "abc123",
        },
    )
    entry.add_to_hass(hass)

    fake_coordinator = _FakeCoordinator()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    with patch(
        "custom_components.mypolaris.MyPolarisCoordinator",
        return_value=fake_coordinator,
    ), patch(
        "custom_components.mypolaris.async_create_clientsession",
        return_value=object(),
    ):
        result = await integration.async_setup_entry(hass, entry)

    assert result is True
    assert fake_coordinator.config_entry_id == entry.entry_id
    fake_coordinator.async_config_entry_first_refresh.assert_awaited_once_with()
    fake_coordinator.async_start_keepalive.assert_called_once_with()
    assert hass.data[DOMAIN][entry.entry_id] is fake_coordinator
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
        entry,
        PLATFORMS,
    )

    device_reg = integration.dr.async_get(hass)
    assert any(
        (DOMAIN, f"{entry.entry_id}_100") in device.identifiers
        for device in device_reg.devices.values()
    )


async def test_async_unload_entry_unloads_platforms_and_clears_data(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "user@example.com"},
    )
    entry.add_to_hass(hass)
    fake_coordinator = _FakeCoordinator()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = fake_coordinator
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    result = await integration.async_unload_entry(hass, entry)

    assert result is True
    hass.config_entries.async_unload_platforms.assert_awaited_once_with(
        entry,
        PLATFORMS,
    )
    fake_coordinator.async_unload.assert_awaited_once_with()
    fake_coordinator.session.close.assert_awaited_once_with()
    assert entry.entry_id not in hass.data[DOMAIN]
