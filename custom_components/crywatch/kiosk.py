"""Fully Kiosk alert: wake a kiosk device, show the camera, ensure volume, on cry.

The official `fully_kiosk` integration only registers 3 custom services
(load_url, start_application, set_config) — everything else (foreground/
background, volume, brightness) is exposed as regular button/media_player/
number entities on the device. We find the right entity for a given action
by its (stable, English, locale-independent) unique_id suffix rather than by
its (translated) friendly name — e.g. "-toForeground", not "Mettre au
premier plan". Confirmed against a real Fully Kiosk PLUS device (see
FORK_NOTES.md) via Home Assistant's entity registry.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_FULLY_KIOSK_DEVICE, CONF_KIOSK_URL, CONF_KIOSK_VOLUME, DEFAULT_KIOSK_VOLUME
from .coordinator import CrywatchCoordinator

_LOGGER = logging.getLogger(__name__)


def _find_entity(hass: HomeAssistant, device_id: str, unique_id_suffix: str) -> str | None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_device(registry, device_id):
        if entity.platform == "fully_kiosk" and entity.unique_id.endswith(unique_id_suffix):
            return entity.entity_id
    return None


def async_setup_kiosk_alert(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: CrywatchCoordinator
) -> None:
    """Wire the coordinator's cry state to Fully Kiosk actions, if configured."""
    device_id = entry.options.get(CONF_FULLY_KIOSK_DEVICE)
    if not device_id:
        return

    url = entry.options.get(CONF_KIOSK_URL) or None
    volume_pct = entry.options.get(CONF_KIOSK_VOLUME, DEFAULT_KIOSK_VOLUME)

    foreground = _find_entity(hass, device_id, "-toForeground")
    background = _find_entity(hass, device_id, "-toBackground")
    start_url_button = _find_entity(hass, device_id, "-loadStartUrl")
    media_player = _find_entity(hass, device_id, "-mediaplayer")

    if not foreground:
        _LOGGER.warning(
            "Crywatch: fully_kiosk device %s has no 'to foreground' button — "
            "kiosk alert disabled for this entry", device_id,
        )
        return

    # crying state per camera key, as of the last coordinator refresh — to
    # detect ON/OFF transitions rather than re-firing on every 5s poll.
    previous: dict[str, bool] = {}

    async def _alert() -> None:
        try:
            if url:
                await hass.services.async_call(
                    "fully_kiosk", "load_url", {"device_id": device_id, "url": url},
                )
            if media_player:
                await hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": media_player, "volume_level": volume_pct / 100},
                )
                await hass.services.async_call(
                    "media_player",
                    "volume_mute",
                    {"entity_id": media_player, "is_volume_muted": False},
                )
            await hass.services.async_call("button", "press", {"entity_id": foreground})
        except Exception:  # noqa: BLE001 - device offline shouldn't break the listener
            _LOGGER.exception("Crywatch: fully_kiosk alert failed for device %s", device_id)

    async def _revert() -> None:
        try:
            if start_url_button:
                await hass.services.async_call("button", "press", {"entity_id": start_url_button})
            if background:
                await hass.services.async_call("button", "press", {"entity_id": background})
        except Exception:  # noqa: BLE001 - device offline shouldn't break the listener
            _LOGGER.exception("Crywatch: fully_kiosk revert failed for device %s", device_id)

    @callback
    def _on_update() -> None:
        for key, cam in coordinator.data.items():
            was = previous.get(key, False)
            now = bool(cam.get("crying"))
            previous[key] = now
            if now and not was:
                hass.async_create_task(_alert())
            elif was and not now:
                hass.async_create_task(_revert())

    entry.async_on_unload(coordinator.async_add_listener(_on_update))
