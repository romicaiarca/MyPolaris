"""Coordinator behavior tests for MyPolaris."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from custom_components.mypolaris.coordinator import (
    BASE_URL,
    KEEPALIVE_INTERVAL,
    MyPolarisCoordinator,
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