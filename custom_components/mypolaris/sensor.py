"""Sensor platform for mypolaris."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .utils import (
    format_ron as _format_ron,
    localize_access_source,
    month_name as _month_name,
    slug_for_entity_id,
    sort_by_dmy as _sort_by_dmy,
)
from .const import DOMAIN
from .coordinator import MyPolarisCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyPolaris sensors — one full set per location (PdL)."""
    coordinator: MyPolarisCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _locatii() -> list[dict[str, str]]:
        return (coordinator.data or {}).get("locatii") or []

    def _build_static_for(loc: dict[str, str]) -> list[SensorEntity]:
        return [
            MyPolarisContractSensor(coordinator, entry.entry_id, loc),
            MyPolarisSoldCurentSensor(coordinator, entry.entry_id, loc),
            MyPolarisSoldFacturaSensor(coordinator, entry.entry_id, loc),
            MyPolarisFacturiNeplatiteCountSensor(coordinator, entry.entry_id, loc),
            MyPolarisFacturiNeplatiteTotalSensor(coordinator, entry.entry_id, loc),
            MyPolarisLastUpdateSensor(coordinator, entry.entry_id, loc),
        ]

    known_locatii: set[str] = set()
    # (locatie_id, year) pairs already materialised
    known_year_pairs: set[tuple[str, int]] = set()

    initial: list[SensorEntity] = [
        MyPolarisLastAccessSensor(coordinator, entry.entry_id),
        MyPolarisCapsolverCallsSensor(coordinator, entry.entry_id),
    ]
    for loc in _locatii():
        known_locatii.add(loc["id"])
        initial.extend(_build_static_for(loc))
    if initial:
        async_add_entities(initial, True)

    @callback
    def _add_dynamic_sensors() -> None:
        if not coordinator.data:
            return
        new_entities: list[SensorEntity] = []

        # 1) Locations that appeared after first refresh.
        for loc in _locatii():
            if loc["id"] in known_locatii:
                continue
            known_locatii.add(loc["id"])
            new_entities.extend(_build_static_for(loc))

        # 2) Per-location year archive sensors.
        by_locatie = (coordinator.data or {}).get("by_locatie") or {}
        for loc in _locatii():
            bucket = by_locatie.get(loc["id"]) or {}
            for year in bucket.get("years") or []:
                pair = (loc["id"], int(year))
                if pair in known_year_pairs:
                    continue
                known_year_pairs.add(pair)
                new_entities.append(
                    MyPolarisArhivaFacturiSensor(
                        coordinator, entry.entry_id, loc, int(year)
                    )
                )
                new_entities.append(
                    MyPolarisArhivaPlatiSensor(
                        coordinator, entry.entry_id, loc, int(year)
                    )
                )

        if new_entities:
            async_add_entities(new_entities, True)

    _add_dynamic_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_dynamic_sensors))


def _device_info(
    coordinator: MyPolarisCoordinator,
    entry_id: str,
    loc: dict[str, str],
) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{loc['id']}")},
        manufacturer="Polaris",
        name=f"MyPolaris — {loc.get('denumire') or loc['id']}",
        model=f"PdL {loc['id']}",
        configuration_url="https://my.polaris.ro",
    )


class MyPolarisLastAccessSensor(SensorEntity):
    """Timestamp sensor for the most recent MyPolaris endpoint call."""

    _attr_has_entity_name = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "MyPolaris Ultima Accesare"
    _attr_icon = "mdi:web-clock"

    def __init__(self, coordinator: MyPolarisCoordinator, entry_id: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.email}_last_access_call"
        self.entity_id = (
            f"sensor.mypolaris_{slug_for_entity_id(coordinator.email)}_last_access_call"
        )

        data = coordinator.data or {}
        locatii = data.get("locatii") or []
        primary = locatii[0] if locatii else {"id": "primary", "denumire": coordinator.email}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{primary['id']}")},
            manufacturer="Polaris",
            name=f"MyPolaris — {primary.get('denumire') or primary['id']}",
            configuration_url="https://my.polaris.ro",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.coordinator.async_add_access_listener(self._handle_access_update)
        )

    @callback
    def _handle_access_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.last_access_at is not None

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_access_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if self.coordinator.last_access_endpoint:
            attrs["endpoint"] = self.coordinator.last_access_endpoint
        if self.coordinator.last_access_method:
            attrs["metoda"] = self.coordinator.last_access_method
        if self.coordinator.last_access_source:
            attrs["sursa"] = localize_access_source(
                self.coordinator.last_access_source
            )
        if self.coordinator.last_access_status is not None:
            attrs["status"] = self.coordinator.last_access_status
        return attrs


class MyPolarisCapsolverCallsSensor(SensorEntity):
    """Diagnostic counter for CapSolver solve attempts since integration load."""

    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"
    _attr_name = "MyPolaris CapSolver Apeluri de la Restart"
    _attr_native_unit_of_measurement = "apeluri"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: MyPolarisCoordinator, entry_id: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.email}_capsolver_calls_since_restart"
        self.entity_id = (
            f"sensor.mypolaris_{slug_for_entity_id(coordinator.email)}_"
            "capsolver_calls_since_restart"
        )

        data = coordinator.data or {}
        locatii = data.get("locatii") or []
        primary = locatii[0] if locatii else {"id": "primary", "denumire": coordinator.email}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{primary['id']}")},
            manufacturer="Polaris",
            name=f"MyPolaris — {primary.get('denumire') or primary['id']}",
            configuration_url="https://my.polaris.ro",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.coordinator.async_add_capsolver_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.capsolver_calls_since_start

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "reset": "restart integrare",
            "tip_task": (
                "ReCaptchaV3Task"
                if self.coordinator.capsolver_proxy
                else "ReCaptchaV3TaskProxyLess"
            ),
            "proxy": bool(self.coordinator.capsolver_proxy),
        }


class _MyPolarisBase(CoordinatorEntity, SensorEntity):
    """Common base for MyPolaris sensors (one instance per location)."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: MyPolarisCoordinator,
        entry_id: str,
        loc: dict[str, str],
        key: str,
        name: str,
        icon: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._locatie_id = loc["id"]
        self._locatie_denumire = loc.get("denumire") or loc["id"]
        self._attr_name = f"{name} — {self._locatie_denumire}"
        self._attr_unique_id = f"{coordinator.email}_{loc['id']}_{key}"
        self.entity_id = f"sensor.mypolaris_{slug_for_entity_id(self._locatie_denumire)}_{key}"
        if icon:
            self._attr_icon = icon
        self._attr_device_info = _device_info(coordinator, entry_id, loc)

    @property
    def _bucket(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return ((data.get("by_locatie") or {}).get(self._locatie_id)) or {}

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._locatie_id in ((self.coordinator.data or {}).get("by_locatie") or {})
        )


class MyPolarisContractSensor(_MyPolarisBase):
    def __init__(self, coordinator, entry_id, loc):
        super().__init__(coordinator, entry_id, loc, "contract",
                         "MyPolaris Contract", "mdi:file-document-outline")

    @property
    def native_value(self) -> str | None:
        return self._bucket.get("denumire")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"pdl_id": self._locatie_id}


class MyPolarisSoldCurentSensor(_MyPolarisBase):
    _attr_native_unit_of_measurement = "RON"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry_id, loc):
        super().__init__(coordinator, entry_id, loc, "sold_curent",
                         "MyPolaris Sold Curent", "mdi:cash")

    @property
    def native_value(self) -> float | None:
        raw = self._bucket.get("sold_curent")
        return float(raw) if raw is not None else None


class MyPolarisSoldFacturaSensor(_MyPolarisBase):
    """Textual balance: '79.36 RON' or 'Nu' when zero."""

    def __init__(self, coordinator, entry_id, loc):
        super().__init__(coordinator, entry_id, loc, "sold_factura",
                         "MyPolaris Sold Factură", "mdi:cash-multiple")

    @property
    def native_value(self) -> str | None:
        return self._bucket.get("sold_factura")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        b = self._bucket
        return {
            "neplatite": b.get("facturi_neplatite") or [],
            "neplatite_count": b.get("facturi_neplatite_count"),
            "neplatite_total": b.get("facturi_neplatite_total"),
        }


class MyPolarisFacturiNeplatiteCountSensor(_MyPolarisBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "facturi"

    def __init__(self, coordinator, entry_id, loc):
        super().__init__(coordinator, entry_id, loc, "facturi_neplatite",
                         "MyPolaris Facturi Neplătite", "mdi:invoice-text-clock")

    @property
    def native_value(self) -> int | None:
        return self._bucket.get("facturi_neplatite_count")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"facturi": self._bucket.get("facturi_neplatite") or []}


class MyPolarisFacturiNeplatiteTotalSensor(_MyPolarisBase):
    _attr_native_unit_of_measurement = "RON"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry_id, loc):
        super().__init__(coordinator, entry_id, loc, "facturi_neplatite_total",
                         "MyPolaris Facturi Neplătite Total", "mdi:cash-remove")

    @property
    def native_value(self) -> float | None:
        return self._bucket.get("facturi_neplatite_total")


class MyPolarisLastUpdateSensor(_MyPolarisBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id, loc):
        super().__init__(coordinator, entry_id, loc, "ultima_actualizare",
                         "MyPolaris Ultima Actualizare", "mdi:update")

    @property
    def native_value(self) -> datetime | None:
        raw = (self.coordinator.data or {}).get("ultima_actualizare")
        if not isinstance(raw, str):
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").astimezone()
        except ValueError:
            return None


class MyPolarisArhivaFacturiSensor(_MyPolarisBase):
    """Yearly invoice archive — state is the count, each invoice is a flat attribute."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id, loc, year: int) -> None:
        super().__init__(
            coordinator, entry_id, loc, f"arhiva_facturi_{year}",
            f"{year} → Arhivă facturi", "mdi:invoice-list",
        )
        self._year = year

    def _entries(self) -> list[dict[str, Any]]:
        return (self._bucket.get("facturi_by_year") or {}).get(self._year) or []

    @property
    def native_value(self) -> int:
        return len(self._entries())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entries = self._entries()
        attrs: dict[str, Any] = {}
        if not entries:
            attrs["Date"] = "Nu sunt disponibile facturi"
            attrs["Facturi emise"] = 0
            attrs["Sumă totală"] = "0,00 RON"
            attrs["Rest de plată"] = "0,00 RON"
            return attrs

        total = 0.0
        rest_total = 0.0
        for idx, f in enumerate(_sort_by_dmy(entries, "DataDocument"), start=1):
            valoare = float(f.get("Valoare") or 0.0)
            rest = float(f.get("Rest") or 0.0)
            total += valoare
            rest_total += rest
            month_name = _month_name(f.get("DataDocument"))
            serie = f.get("SerieDocument") or ""
            nr = f.get("NrDocument") or ""
            doc = f"{serie} {nr}".strip() or "-"
            scadenta = f.get("DataScadenta") or ""
            scad_suffix = f" (scadent {scadenta})" if scadenta else ""
            attrs[f"Factură {idx} luna {month_name} — {doc}"] = (
                f"{_format_ron(valoare)} RON{scad_suffix}"
            )

        attrs["Facturi emise"] = len(entries)
        attrs["Sumă totală"] = f"{_format_ron(total)} RON"
        attrs["Rest de plată"] = f"{_format_ron(rest_total)} RON"
        return attrs


class MyPolarisArhivaPlatiSensor(_MyPolarisBase):
    """Yearly payments archive — state is the count, each payment is a flat attribute."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id, loc, year: int) -> None:
        super().__init__(
            coordinator, entry_id, loc, f"arhiva_plati_{year}",
            f"{year} → Arhivă plăți", "mdi:cash-register",
        )
        self._year = year

    def _entries(self) -> list[dict[str, Any]]:
        return (self._bucket.get("plati_by_year") or {}).get(self._year) or []

    @property
    def native_value(self) -> int:
        return len(self._entries())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entries = self._entries()
        attrs: dict[str, Any] = {}
        if not entries:
            attrs["Date"] = "Nu sunt disponibile plăți"
            attrs["Plăți efectuate"] = 0
            attrs["Sumă totală"] = "0,00 RON"
            return attrs

        total = 0.0
        for idx, p in enumerate(_sort_by_dmy(entries, "DataDoc"), start=1):
            suma = float(p.get("Suma") or 0.0)
            total += suma
            month_name = _month_name(p.get("DataDoc"))
            tip = p.get("TipDoc") or ""
            nr = p.get("NrDoc") or ""
            tip_suffix = f" ({tip})" if tip else ""
            doc_suffix = f" #{nr}" if nr else ""
            attrs[f"Plată {idx} luna {month_name}{tip_suffix}{doc_suffix}"] = (
                f"{_format_ron(suma)} RON"
            )

        attrs["Plăți efectuate"] = len(entries)
        attrs["Sumă totală"] = f"{_format_ron(total)} RON"
        return attrs
