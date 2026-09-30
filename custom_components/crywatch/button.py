"""Button platform for Crywatch — simulate a cry, one button per camera.

Pressing it holds that camera's "Pleurs détectés" binary_sensor ON for
SIMULATED_CRY_SECONDS, exactly as a real detection would, then lets it fall
back to the add-on's actual state. Whatever automation is triggered by the
binary_sensor (screen wake, camera view, notification…) runs for real, so it
can be checked without waiting for, or faking, an actual cry.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIMULATED_CRY_SECONDS
from .coordinator import CrywatchCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CrywatchCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrywatchSimulateCryButton(coordinator, entry, key) for key in coordinator.camera_keys
    )


class CrywatchSimulateCryButton(ButtonEntity):
    """Forces the camera's cry binary_sensor ON for a short while."""

    _attr_has_entity_name = True
    _attr_name = "Simuler des pleurs"
    _attr_icon = "mdi:emoticon-cry-outline"

    def __init__(self, coordinator: CrywatchCoordinator, entry: ConfigEntry, key: str) -> None:
        self._coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}_simulate_cry"
        # same device as the camera's binary_sensor/sensor
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"{entry.entry_id}_{key}")})

    async def async_press(self) -> None:
        self._coordinator.async_simulate_cry(self._key, SIMULATED_CRY_SECONDS)
