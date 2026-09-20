"""Binary sensor platform for Crywatch — one 'cry detected' per camera."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CrywatchCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CrywatchCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrywatchCryBinarySensor(coordinator, entry, key) for key in coordinator.data
    )


class CrywatchCryBinarySensor(CoordinatorEntity[CrywatchCoordinator], BinarySensorEntity):
    """ON while the add-on considers a real cry to be in progress."""

    _attr_device_class = BinarySensorDeviceClass.SOUND
    _attr_has_entity_name = True
    _attr_name = "Pleurs détectés"

    def __init__(self, coordinator: CrywatchCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}_cry"
        label = (coordinator.data.get(key) or {}).get("label", key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{key}")},
            name=label,
            manufacturer="crywatch",
            model="YAMNet cry detector",
        )

    @property
    def is_on(self) -> bool | None:
        cam = self.coordinator.data.get(self._key)
        return cam.get("crying") if cam else None

    @property
    def available(self) -> bool:
        return super().available and self._key in self.coordinator.data
