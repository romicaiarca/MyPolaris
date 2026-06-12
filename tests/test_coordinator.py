"""Coordinator behavior tests for MyPolaris."""
from __future__ import annotations

from datetime import timedelta
import json
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.mypolaris.coordinator import (
    BASE_URL,
    CAPSOLVER_CREATE_TASK_URL,
    CAPSOLVER_GET_TASK_RESULT_URL,
    CAPSOLVER_GET_BALANCE_URL,
    CAPSOLVER_RECAPTCHA_URL,
    HOME_URL,
    INIT_URL,
    KEEPALIVE_INTERVAL,
    MyPolarisCoordinator,
    get_capsolver_balance,
    solve_recaptcha_with_capsolver,
)


def test_async_start_keepalive_schedules_for_cookie_auth(hass) -> None:
    cancel = MagicMock()
    coordinator = MyPolarisCoordinator(
        hass,
        "user@example.com",
        "",
        "",
        timedelta(minutes=30),
        MagicMock(),
        session_cookie="abc123",
    )

    with patch(
        "custom_components.mypolaris.coordinator.async_track_time_interval",
        return_value=cancel,
    ) as mock_track:
        coordinator.async_start_keepalive()

    mock_track.assert_called_once_with(
        hass,
        coordinator._async_keepalive,
        KEEPALIVE_INTERVAL,
    )
    assert coordinator._cancel_keepalive is cancel

    coordinator.async_stop_keepalive()
    cancel.assert_called_once_with()
    assert coordinator._cancel_keepalive is None


def test_async_start_keepalive_skips_unneeded_cases(hass) -> None:
    scenarios = [
        ("", timedelta(minutes=30)),
        ("abc123", KEEPALIVE_INTERVAL),
        ("abc123", timedelta(seconds=90)),
    ]

    for session_cookie, update_interval in scenarios:
        coordinator = MyPolarisCoordinator(
            hass,
            "user@example.com",
            "",
            "",
            update_interval,
            MagicMock(),
            session_cookie=session_cookie,
        )

        with patch(
            "custom_components.mypolaris.coordinator.async_track_time_interval",
        ) as mock_track:
            coordinator.async_start_keepalive()

        mock_track.assert_not_called()
        assert coordinator._cancel_keepalive is None


async def test_async_keepalive_uses_home_init_endpoint(hass) -> None:
    coordinator = MyPolarisCoordinator(
        hass,
        "user@example.com",
        "",
        "",
        timedelta(minutes=30),
        MagicMock(),
        session_cookie="abc123",
    )
    coordinator._post_json = AsyncMock(return_value={"d": {"EsteOK": True}})

    await coordinator._async_keepalive(None)

    coordinator._post_json.assert_awaited_once_with(
        INIT_URL,
        {},
        source="keepalive",
        referer=HOME_URL,
    )


def test_record_last_access_updates_state_and_listeners(hass) -> None:
    coordinator = MyPolarisCoordinator(
        hass,
        "user@example.com",
        "",
        "",
        timedelta(minutes=30),
        MagicMock(),
        session_cookie="abc123",
    )
    listener = MagicMock()
    remove = coordinator.async_add_access_listener(listener)

    coordinator._record_last_access(
        f"{BASE_URL}/Contact.aspx/GetListaLocatii",
        method="POST",
        source="keepalive",
        status=200,
    )

    assert coordinator.last_access_at is not None
    assert coordinator.last_access_endpoint == "/Contact.aspx/GetListaLocatii"
    assert coordinator.last_access_method == "POST"
    assert coordinator.last_access_source == "keepalive"
    assert coordinator.last_access_status == 200
    listener.assert_called_once_with()

    remove()
    coordinator._record_last_access(
        f"{BASE_URL}/InvoicesAndPayments.aspx/LoadDataSold",
        method="POST",
        source="refresh",
        status=200,
    )
    listener.assert_called_once_with()


class _FakeCapsolverResponse:
    def __init__(self, data: dict, status: int = 200) -> None:
        self._data = data
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return json.dumps(self._data)


class _FakeCapsolverSession:
    def __init__(self) -> None:
        self.payloads: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict):
        self.payloads.append((url, json))
        if url == CAPSOLVER_CREATE_TASK_URL:
            return _FakeCapsolverResponse({"errorId": 0, "taskId": "task-1"})
        if url == CAPSOLVER_GET_TASK_RESULT_URL:
            return _FakeCapsolverResponse(
                {
                    "errorId": 0,
                    "status": "ready",
                    "solution": {"gRecaptchaResponse": "token-1"},
                }
            )
        if url == CAPSOLVER_GET_BALANCE_URL:
            return _FakeCapsolverResponse({"errorId": 0, "balance": 4.999})
        raise AssertionError(f"Unexpected URL: {url}")


async def test_capsolver_uses_proxyless_google_demo_payload() -> None:
    session = _FakeCapsolverSession()

    with patch(
        "custom_components.mypolaris.coordinator.asyncio.sleep",
        new=AsyncMock(),
    ):
        solution = await solve_recaptcha_with_capsolver(
            session,
            "CAP-123456789012345678901234567890",
            "site-key",
            "https://my.polaris.ro/Login.aspx",
            "homepage",
        )

    assert solution["gRecaptchaResponse"] == "token-1"
    assert session.payloads == [
        (
            CAPSOLVER_CREATE_TASK_URL,
            {
                "clientKey": "CAP-123456789012345678901234567890",
                "task": {
                    "type": "ReCaptchaV3TaskProxyLess",
                    "websiteURL": CAPSOLVER_RECAPTCHA_URL,
                    "websiteKey": "site-key",
                },
            },
        ),
        (
            CAPSOLVER_GET_TASK_RESULT_URL,
            {
                "clientKey": "CAP-123456789012345678901234567890",
                "taskId": "task-1",
            },
        ),
    ]


async def test_capsolver_get_balance_uses_client_key_payload() -> None:
    session = _FakeCapsolverSession()

    balance = await get_capsolver_balance(
        session,
        "CAP-123456789012345678901234567890",
    )

    assert balance == 4.999
    assert session.payloads == [
        (
            CAPSOLVER_GET_BALANCE_URL,
            {"clientKey": "CAP-123456789012345678901234567890"},
        )
    ]


def test_record_capsolver_call_updates_counter_and_listeners(hass) -> None:
    coordinator = MyPolarisCoordinator(
        hass,
        "user@example.com",
        "",
        "",
        timedelta(minutes=30),
        MagicMock(),
        session_cookie="abc123",
    )
    listener = MagicMock()
    remove = coordinator.async_add_capsolver_listener(listener)

    coordinator._record_capsolver_call()

    assert coordinator.capsolver_calls_since_start == 1
    listener.assert_called_once_with()

    remove()
    coordinator._record_capsolver_call()

    assert coordinator.capsolver_calls_since_start == 2
    listener.assert_called_once_with()


def test_record_capsolver_call_schedules_balance_refresh(hass) -> None:
    coordinator = MyPolarisCoordinator(
        hass,
        "user@example.com",
        "",
        "CAP-123456789012345678901234567890",
        timedelta(minutes=30),
        MagicMock(),
        session_cookie="abc123",
    )

    with patch.object(coordinator, "_schedule_capsolver_balance_refresh") as mock_schedule:
        coordinator._record_capsolver_call()

    assert coordinator.capsolver_calls_since_start == 1
    mock_schedule.assert_called_once_with()
