"""Sensor platform for Crywatch — cry-confidence % per camera."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
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
        CrywatchScoreSensor(coordinator, entry, key) for key in coordinator.data
    )


class CrywatchScoreSensor(CoordinatorEntity[CrywatchCoordinator], SensorEntity):
    """Peak cry-classifier confidence (%) of the last triggered sample."""

    _attr_has_entity_name = True
    _attr_name = "Confiance pleurs"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CrywatchCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}_score"
        label = (coordinator.data.get(key) or {}).get("label", key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{key}")},
            name=label,
        )

    @property
    def native_value(self) -> int | None:
        cam = self.coordinator.data.get(self._key)
        return cam.get("score_pct") if cam else None

    @property
    def available(self) -> bool:
        return super().available and self._key in self.coordinator.data
