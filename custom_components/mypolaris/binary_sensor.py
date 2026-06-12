from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTEGRATION_AUTHOR


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MyPolarisOnlineSensor(coordinator, entry.entry_id)])


class MyPolarisOnlineSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "MyPolaris Online"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.email}_online"
        # Attach to the primary location's device so it shows up grouped
        # with the rest of the sensors (per-PdL devices).
        data = coordinator.data or {}
        locatii = data.get("locatii") or []
        primary = locatii[0] if locatii else {"id": "primary", "denumire": coordinator.email}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{primary['id']}")},
            manufacturer=INTEGRATION_AUTHOR,
            name=f"MyPolaris — {primary.get('denumire') or primary['id']}",
            configuration_url="https://my.polaris.ro",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data is not None