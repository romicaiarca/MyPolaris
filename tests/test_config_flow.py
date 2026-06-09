"""Home Assistant config-flow tests for MyPolaris."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypolaris.config_flow import (
    AUTH_METHOD_CREDENTIALS,
    AUTH_METHOD_SESSION_COOKIE,
    CONF_AUTH_METHOD,
)
from custom_components.mypolaris.const import (
    CONF_API_KEY,
    CONF_AREA_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SESSION_COOKIE,
    DOMAIN,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _mock_config_entry_setup():
    with patch(
        "custom_components.mypolaris.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        yield


async def _select_auth_step(hass, next_step_id: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": next_step_id},
    )


async def test_user_step_offers_both_auth_paths(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "user"
    assert set(result["menu_options"]) == {
        AUTH_METHOD_CREDENTIALS,
        AUTH_METHOD_SESSION_COOKIE,
    }


async def test_credentials_step_rejects_invalid_api_key(hass) -> None:
    form = await _select_auth_step(hass, AUTH_METHOD_CREDENTIALS)

    assert form["type"] == FlowResultType.FORM
    assert form["step_id"] == AUTH_METHOD_CREDENTIALS

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_API_KEY: "invalid-key",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == AUTH_METHOD_CREDENTIALS
    assert result["errors"] == {"base": "invalid_api_key"}


async def test_session_cookie_step_creates_entry(hass) -> None:
    form = await _select_auth_step(hass, AUTH_METHOD_SESSION_COOKIE)

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_EMAIL: "user@example.com",
            CONF_SESSION_COOKIE: "abc123",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "MyPolaris - user@example.com"
    assert result["data"] == {
        CONF_EMAIL: "user@example.com",
        CONF_AUTH_METHOD: AUTH_METHOD_SESSION_COOKIE,
        CONF_SESSION_COOKIE: "abc123",
    }


async def test_duplicate_email_is_rejected_case_insensitively(hass) -> None:
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_AUTH_METHOD: AUTH_METHOD_SESSION_COOKIE,
            CONF_SESSION_COOKIE: "old-cookie",
        },
    )
    existing_entry.add_to_hass(hass)

    form = await _select_auth_step(hass, AUTH_METHOD_SESSION_COOKIE)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_EMAIL: "USER@example.com",
            CONF_SESSION_COOKIE: "new-cookie",
        },
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_interval_and_cookie(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_AUTH_METHOD: AUTH_METHOD_SESSION_COOKIE,
            CONF_SESSION_COOKIE: "old-cookie",
        },
        options={"update_interval_minutes": 30},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    updated = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "update_interval_minutes": 45,
            CONF_SESSION_COOKIE: "fresh-cookie",
        },
    )

    assert updated["type"] == FlowResultType.CREATE_ENTRY
    assert updated["data"]["update_interval_minutes"] == 45
    assert updated["data"][CONF_SESSION_COOKIE] == "fresh-cookie"


async def test_options_flow_renders_with_existing_area(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_AUTH_METHOD: AUTH_METHOD_SESSION_COOKIE,
            CONF_SESSION_COOKIE: "old-cookie",
            CONF_AREA_ID: "focsani",
        },
        options={"update_interval_minutes": 30},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM

    updated = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "update_interval_minutes": 60,
            CONF_SESSION_COOKIE: "fresh-cookie",
            CONF_AREA_ID: "focsani",
        },
    )

    assert updated["type"] == FlowResultType.CREATE_ENTRY
    assert updated["data"]["update_interval_minutes"] == 60
    assert updated["data"][CONF_SESSION_COOKIE] == "fresh-cookie"
    assert updated["data"][CONF_AREA_ID] == "focsani"