"""The Crywatch integration — native HA sensors for the crywatch_cry_detector add-on.

Cameras are picked from existing HA `camera.*` entities (config/options flow)
rather than typed in as raw RTSP URLs: we resolve each entity's actual stream
source via HA's own camera component and hand that list to the add-on, which
does the actual audio sampling + YAMNet inference. The coordinator keeps
that list in sync (re-pushes it if the add-on restarts or a camera entity
wasn't loaded yet at setup).
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import CrywatchCoordinator
from .kiosk import async_setup_kiosk_alert

PLATFORMS: list[str] = ["binary_sensor", "sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = CrywatchCoordinator(hass, entry)
    await coordinator.async_push_cameras()
    await coordinator.async_config_entry_first_refresh()

    coordinator.kiosk_manager = async_setup_kiosk_alert(hass, entry, coordinator)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed (cameras added/removed) — reload to re-push and refresh entities."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
