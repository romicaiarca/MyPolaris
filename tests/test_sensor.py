"""Sensor behavior tests for MyPolaris."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypolaris.const import DOMAIN
from custom_components.mypolaris import sensor as sensor_platform
from custom_components.mypolaris.sensor import (
    MyPolarisCapsolverCallsSensor,
    MyPolarisLastAccessSensor,
)


class _FakeCoordinator:
    def __init__(self, data: dict | None = None) -> None:
        self.email = "user@example.com"
        self.data = data or {
            "locatii": [
                {"id": "100", "denumire": "Sediul Social"},
            ]
        }
        self.last_update_success = True
        self.last_access_at = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)
        self.last_access_endpoint = "/Contact.aspx/GetListaLocatii"
        self.last_access_method = "POST"
        self.last_access_source = "keepalive"
        self.last_access_status = 200
        self.capsolver_calls_since_start = 0
        self.capsolver_proxy = ""
        self._listeners: list[Callable[[], None]] = []
        self._capsolver_listeners: list[Callable[[], None]] = []
        self._update_listeners: list[Callable[[], None]] = []

    def async_add_access_listener(self, update_callback: Callable[[], None]):
        self._listeners.append(update_callback)

        def _remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _remove_listener

    def async_add_capsolver_listener(self, update_callback: Callable[[], None]):
        self._capsolver_listeners.append(update_callback)

        def _remove_listener() -> None:
            if update_callback in self._capsolver_listeners:
                self._capsolver_listeners.remove(update_callback)

        return _remove_listener

    def async_add_listener(self, update_callback: Callable[[], None]):
        self._update_listeners.append(update_callback)

        def _remove_listener() -> None:
            if update_callback in self._update_listeners:
                self._update_listeners.remove(update_callback)

        return _remove_listener


def test_capsolver_calls_sensor_counts_since_restart() -> None:
    coordinator = _FakeCoordinator()
    coordinator.capsolver_calls_since_start = 2
    sensor = MyPolarisCapsolverCallsSensor(coordinator, "entry-1")

    assert sensor.entity_id == "sensor.mypolaris_userexample_com_capsolver_calls_since_restart"
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes == {
        "reset": "restart integrare",
        "tip_task": "ReCaptchaV3TaskProxyLess",
        "proxy": False,
    }


def test_last_access_sensor_exposes_localized_attributes() -> None:
    coordinator = _FakeCoordinator()
    sensor = MyPolarisLastAccessSensor(coordinator, "entry-1")

    assert sensor.entity_id == "sensor.mypolaris_userexample_com_last_access_call"
    assert sensor.available is True
    assert sensor.native_value == coordinator.last_access_at
    assert sensor.extra_state_attributes == {
        "endpoint": "/Contact.aspx/GetListaLocatii",
        "metoda": "POST",
        "sursa": "mentinere sesiune",
        "status": 200,
    }


async def test_async_setup_entry_adds_dynamic_location_and_archive_sensors(hass) -> None:
    coordinator = _FakeCoordinator(
        {
            "locatii": [
                {"id": "100", "denumire": "Sediul Social"},
            ],
            "by_locatie": {
                "100": {"years": [2025]},
            },
        }
    )
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    added_batches: list[tuple[list[object], bool]] = []

    def _async_add_entities(entities, update_before_add=False):
        added_batches.append((list(entities), update_before_add))

    await sensor_platform.async_setup_entry(hass, entry, _async_add_entities)

    assert len(added_batches) == 2
    assert len(added_batches[0][0]) == 8
    assert len(added_batches[1][0]) == 2

    coordinator.data = {
        "locatii": [
            {"id": "100", "denumire": "Sediul Social"},
            {"id": "200", "denumire": "Sediul Nord"},
        ],
        "by_locatie": {
            "100": {"years": [2025, 2024]},
            "200": {"years": [2026]},
        },
    }

    coordinator._update_listeners[0]()

    assert len(added_batches) == 3
    assert len(added_batches[2][0]) == 10
    assert {
        type(entity).__name__ for entity in added_batches[2][0]
    } >= {
        "MyPolarisContractSensor",
        "MyPolarisArhivaFacturiSensor",
        "MyPolarisArhivaPlatiSensor",
    }

    coordinator._update_listeners[0]()

    assert len(added_batches) == 3