"""The Crywatch integration — native HA sensors for the crywatch_cry_detector add-on.

Cameras are picked from existing HA `camera.*` entities (config/options flow)
rather than typed in as raw RTSP URLs: we resolve each entity's actual stream
source via HA's own camera component and hand that list to the add-on, which
does the actual audio sampling + YAMNet inference.
"""
from __future__ import annotations

import logging

import aiohttp

from homeassistant.components.camera import async_get_stream_source
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CAMERAS, DOMAIN
from .coordinator import CrywatchCoordinator
from .kiosk import async_setup_kiosk_alert

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["binary_sensor", "sensor"]


async def _push_cameras(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Resolve each selected camera entity's RTSP source and hand the list to the add-on."""
    cameras = []
    for entity_id in entry.options.get(CONF_CAMERAS, []):
        try:
            url = await async_get_stream_source(hass, entity_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("could not get stream source for %s: %s", entity_id, err)
            continue
        if not url:
            _LOGGER.warning(
                "%s has no RTSP stream source (unsupported camera platform?), skipping",
                entity_id,
            )
            continue
        state = hass.states.get(entity_id)
        cameras.append({
            "key": entity_id,
            "name": state.name if state else entity_id,
            "rtsp_url": url,
        })

    session = async_get_clientsession(hass)
    base = f"http://{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}"
    try:
        async with session.post(
            f"{base}/api/cameras",
            json={"cameras": cameras},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("could not push camera list to the add-on: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _push_cameras(hass, entry)

    coordinator = CrywatchCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_kiosk_alert(hass, entry, coordinator)
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
