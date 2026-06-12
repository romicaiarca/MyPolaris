"""Config flow for MyPolaris."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    AreaSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_API_KEY,
    CONF_AREA_ID,
    CONF_CAPSOLVER_PROXY,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SESSION_COOKIE,
    DEFAULT_API_KEY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

AUTH_METHOD_CREDENTIALS = "credentials"
AUTH_METHOD_SESSION_COOKIE = CONF_SESSION_COOKIE
CONF_AUTH_METHOD = "auth_method"
CAPSOLVER_API_KEY_PREFIXES = ("CAI-", "CAP-")
SUPPORTED_PROXY_SCHEMES = ("http",)
DEFAULT_UPDATE_INTERVAL_MINUTES = int(DEFAULT_UPDATE_INTERVAL.total_seconds() // 60)


def _is_valid_capsolver_api_key(api_key: str) -> bool:
    """Return whether the key looks like a CapSolver client key."""
    return len(api_key) >= 30 and api_key.startswith(CAPSOLVER_API_KEY_PREFIXES)


def _is_valid_proxy_url(proxy_url: str) -> bool:
    """Return whether the optional proxy can be used by aiohttp and CapSolver."""
    if not proxy_url:
        return True
    parsed = urlsplit(proxy_url)
    return (
        parsed.scheme.lower() in SUPPORTED_PROXY_SCHEMES
        and parsed.hostname is not None
        and parsed.port is not None
    )


class MyPolarisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyPolaris."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[
                AUTH_METHOD_CREDENTIALS,
                AUTH_METHOD_SESSION_COOKIE,
            ],
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure MyPolaris with email/password and CapSolver."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            api_key = (user_input.get(CONF_API_KEY) or DEFAULT_API_KEY or "").strip()
            capsolver_proxy = (user_input.get(CONF_CAPSOLVER_PROXY) or "").strip()

            if not password.strip():
                errors["base"] = "invalid_password"
            elif not _is_valid_capsolver_api_key(api_key):
                errors["base"] = "invalid_api_key"
            elif not _is_valid_proxy_url(capsolver_proxy):
                errors["base"] = "invalid_proxy"
            else:
                return await self._async_create_entry(
                    email=email,
                    auth_method=AUTH_METHOD_CREDENTIALS,
                    password=password,
                    api_key=api_key,
                    capsolver_proxy=capsolver_proxy,
                    area_id=user_input.get(CONF_AREA_ID),
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD,
                        autocomplete="current-password",
                    )
                ),
                vol.Required(
                    CONF_API_KEY,
                    default=DEFAULT_API_KEY,
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_CAPSOLVER_PROXY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_AREA_ID): AreaSelector(),
            }
        )

        return self.async_show_form(
            step_id=AUTH_METHOD_CREDENTIALS,
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_session_cookie(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure MyPolaris with a copied browser session cookie."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            session_cookie = (user_input.get(CONF_SESSION_COOKIE) or "").strip()

            if not session_cookie:
                errors["base"] = "invalid_session_cookie"
            else:
                return await self._async_create_entry(
                    email=email,
                    auth_method=AUTH_METHOD_SESSION_COOKIE,
                    session_cookie=session_cookie,
                    area_id=user_input.get(CONF_AREA_ID),
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
                ),
                vol.Required(CONF_SESSION_COOKIE): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_AREA_ID): AreaSelector(),
            }
        )

        return self.async_show_form(
            step_id=AUTH_METHOD_SESSION_COOKIE,
            data_schema=data_schema,
            errors=errors,
        )

    async def _async_create_entry(
        self,
        *,
        email: str,
        auth_method: str,
        password: str = "",
        api_key: str = "",
        capsolver_proxy: str = "",
        session_cookie: str = "",
        area_id: str | None = None,
    ) -> FlowResult:
        """Create a config entry once the selected auth path is validated."""
        await self.async_set_unique_id(email.lower())
        self._abort_if_unique_id_configured()

        data = {
            CONF_EMAIL: email,
            CONF_AUTH_METHOD: auth_method,
        }
        if password:
            data[CONF_PASSWORD] = password
        if api_key:
            data[CONF_API_KEY] = api_key
        if capsolver_proxy:
            data[CONF_CAPSOLVER_PROXY] = capsolver_proxy
        if session_cookie:
            data[CONF_SESSION_COOKIE] = session_cookie
        if area_id:
            data[CONF_AREA_ID] = area_id

        return self.async_create_entry(
            title=f"MyPolaris - {email}",
            data=data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow."""
        return MyPolarisOptionsFlow()


class MyPolarisOptionsFlow(config_entries.OptionsFlow):
    """Options flow for MyPolaris."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            data = dict(user_input)
            capsolver_proxy = (
                data.get(CONF_CAPSOLVER_PROXY) or ""
            ).strip()
            if not _is_valid_proxy_url(capsolver_proxy):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._options_schema(),
                    errors={"base": "invalid_proxy"},
                )
            if capsolver_proxy:
                data[CONF_CAPSOLVER_PROXY] = capsolver_proxy
            else:
                data.pop(CONF_CAPSOLVER_PROXY, None)
            return self.async_create_entry(title="", data=data)

        suggested_values: dict[str, Any] = {
            "update_interval_minutes": self.config_entry.options.get(
                "update_interval_minutes", DEFAULT_UPDATE_INTERVAL_MINUTES
            )
        }
        for option_key in (
            CONF_API_KEY,
            CONF_CAPSOLVER_PROXY,
            CONF_SESSION_COOKIE,
            CONF_AREA_ID,
        ):
            value = self.config_entry.options.get(
                option_key, self.config_entry.data.get(option_key)
            )
            if value not in (None, ""):
                suggested_values[option_key] = value

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                self._options_schema(),
                suggested_values,
            ),
        )

    @staticmethod
    def _options_schema() -> vol.Schema:
        """Return the options form schema."""
        return vol.Schema(
            {
                vol.Required(
                    "update_interval_minutes",
                    default=DEFAULT_UPDATE_INTERVAL_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=1440)),
                vol.Optional(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_CAPSOLVER_PROXY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_SESSION_COOKIE): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_AREA_ID): AreaSelector(),
            }
        )
