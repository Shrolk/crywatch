"""Button platform for Crywatch — manually test the Fully Kiosk alert.

Only created when a Fully Kiosk device is actually configured (see
kiosk.py) — pressing it runs the exact same wake/show/volume sequence as a
real cry detection, then reverts a few seconds later, so you can verify the
device really wakes up without waiting for (or faking) an actual cry.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN
from .kiosk import KioskAlertManager

TEST_REVERT_DELAY_SECONDS = 10


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    manager: KioskAlertManager | None = getattr(coordinator, "kiosk_manager", None)
    if manager is None:
        return
    async_add_entities([CrywatchTestAlertButton(entry, manager)])


class CrywatchTestAlertButton(ButtonEntity):
    """Fires the Fully Kiosk alert sequence on demand, then reverts automatically."""

    _attr_has_entity_name = True
    _attr_name = "Tester l'alerte Fully Kiosk"
    _attr_icon = "mdi:bell-ring-outline"

    def __init__(self, entry: ConfigEntry, manager: KioskAlertManager) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_test_kiosk_alert"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Crywatch",
            manufacturer="crywatch",
        )

    async def async_press(self) -> None:
        await self._manager.async_alert()
        async_call_later(self.hass, TEST_REVERT_DELAY_SECONDS, self._async_revert)

    async def _async_revert(self, _now) -> None:
        await self._manager.async_revert()
