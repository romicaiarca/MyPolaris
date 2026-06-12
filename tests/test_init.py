"""Integration setup helper tests for MyPolaris."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

from custom_components.mypolaris import _remove_stale_location_devices
from custom_components.mypolaris.const import DOMAIN


@dataclass
class _FakeDevice:
    id: str
    identifiers: set[tuple[str, str]]


@dataclass
class _FakeEntity:
    entity_id: str
    platform: str
    config_entry_id: str


class _FakeDeviceRegistry:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def async_remove_device(self, device_id: str) -> None:
        self.removed.append(device_id)


class _FakeEntityRegistry:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def async_remove(self, entity_id: str) -> None:
        self.removed.append(entity_id)


def test_remove_stale_location_devices_removes_only_invalid_pdl_devices() -> None:
    entry = SimpleNamespace(entry_id="entry-1")
    device_registry = _FakeDeviceRegistry()
    entity_registry = _FakeEntityRegistry()
    valid_device = _FakeDevice(
        "device-valid",
        {(DOMAIN, "entry-1_289029")},
    )
    stale_device = _FakeDevice(
        "device-stale",
        {(DOMAIN, "entry-1_304505")},
    )
    unrelated_device = _FakeDevice(
        "device-other",
        {(DOMAIN, "other-entry_304505")},
    )

    def _entities_for_device(_registry, device_id, include_disabled_entities=False):
        if device_id == "device-stale":
            return [
                _FakeEntity("sensor.stale", DOMAIN, "entry-1"),
                _FakeEntity("sensor.other_platform", "other", "entry-1"),
            ]
        return []

    with (
        patch("custom_components.mypolaris.dr.async_get", return_value=device_registry),
        patch("custom_components.mypolaris.er.async_get", return_value=entity_registry),
        patch(
            "custom_components.mypolaris.dr.async_entries_for_config_entry",
            return_value=[valid_device, stale_device, unrelated_device],
        ),
        patch(
            "custom_components.mypolaris.er.async_entries_for_device",
            side_effect=_entities_for_device,
        ),
    ):
        _remove_stale_location_devices(None, entry, {"289029"})

    assert entity_registry.removed == ["sensor.stale"]
    assert device_registry.removed == ["device-stale"]
