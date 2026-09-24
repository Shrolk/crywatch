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
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_FULLY_KIOSK_DEVICE, CONF_KIOSK_URL, CONF_KIOSK_VOLUME, DEFAULT_KIOSK_VOLUME
from .coordinator import CrywatchCoordinator

_LOGGER = logging.getLogger(__name__)


def _find_entity(hass: HomeAssistant, device_id: str, unique_id_suffix: str) -> str | None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_device(registry, device_id):
        if entity.platform == "fully_kiosk" and entity.unique_id.endswith(unique_id_suffix):
            return entity.entity_id
    return None


def _resolve_kiosk_url(hass: HomeAssistant, value: str | None) -> str | None:
    """Build the full URL to load on the kiosk from a dashboard path (e.g.
    "dashboard-test/simon"), using HA's own configured base URL — so it keeps
    working if the LAN IP/port ever changes. A full http(s):// value is used
    as-is (e.g. to point at something outside this HA instance)."""
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    try:
        base = get_url(hass, allow_cloud=False, prefer_external=False)
    except NoURLAvailableError:
        _LOGGER.warning(
            "Crywatch: no usable Home Assistant URL found (check Settings > System > "
            "Network) — can't turn kiosk path %r into a URL", value,
        )
        return None
    full_url = f"{base}/{value.lstrip('/')}"
    _LOGGER.info(
        "Crywatch: resolved kiosk path %r to %r — must be reachable from the kiosk "
        "device itself, not just from Home Assistant", value, full_url,
    )
    return full_url


class KioskAlertManager:
    """Wakes/reverts a Fully Kiosk device — shared by the cry listener and the test button."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        url: str | None,
        volume_pct: float,
        foreground: str,
        background: str | None,
        start_url_button: str | None,
        media_player: str | None,
        screen_switch: str | None,
    ) -> None:
        self.hass = hass
        self.device_id = device_id
        self._url = url
        self._volume_pct = volume_pct
        self._foreground = foreground
        self._background = background
        self._start_url_button = start_url_button
        self._media_player = media_player
        self._screen_switch = screen_switch

    async def async_alert(self) -> None:
        # Screen must be woken FIRST — "to foreground" and load_url are no-ops
        # on a sleeping device (nothing to show until the screen is on).
        # "to foreground" resets/reloads the app — must run BEFORE load_url,
        # not after, or it wipes out the page load_url just set (confirmed by
        # testing load_url alone vs. in this sequence against a real device).
        try:
            if self._screen_switch:
                await self.hass.services.async_call(
                    "switch", "turn_on", {"entity_id": self._screen_switch}
                )
            await self.hass.services.async_call("button", "press", {"entity_id": self._foreground})
            if self._media_player:
                await self.hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": self._media_player, "volume_level": self._volume_pct / 100},
                )
                await self.hass.services.async_call(
                    "media_player",
                    "volume_mute",
                    {"entity_id": self._media_player, "is_volume_muted": False},
                )
            if self._url:
                await self.hass.services.async_call(
                    "fully_kiosk", "load_url", {"device_id": self.device_id, "url": self._url},
                )
        except Exception:  # noqa: BLE001 - device offline shouldn't break the caller
            _LOGGER.exception("Crywatch: fully_kiosk alert failed for device %s", self.device_id)

    async def async_revert(self) -> None:
        try:
            if self._start_url_button:
                await self.hass.services.async_call(
                    "button", "press", {"entity_id": self._start_url_button}
                )
            if self._background:
                await self.hass.services.async_call(
                    "button", "press", {"entity_id": self._background}
                )
        except Exception:  # noqa: BLE001 - device offline shouldn't break the caller
            _LOGGER.exception("Crywatch: fully_kiosk revert failed for device %s", self.device_id)


def build_kiosk_alert_manager(hass: HomeAssistant, entry: ConfigEntry) -> KioskAlertManager | None:
    """Resolve the configured Fully Kiosk device's entities. None if unconfigured/incomplete."""
    device_id = entry.options.get(CONF_FULLY_KIOSK_DEVICE)
    if not device_id:
        return None

    foreground = _find_entity(hass, device_id, "-toForeground")
    if not foreground:
        _LOGGER.warning(
            "Crywatch: fully_kiosk device %s has no 'to foreground' button — "
            "kiosk alert disabled for this entry", device_id,
        )
        return None

    return KioskAlertManager(
        hass,
        device_id=device_id,
        url=_resolve_kiosk_url(hass, entry.options.get(CONF_KIOSK_URL)),
        volume_pct=entry.options.get(CONF_KIOSK_VOLUME, DEFAULT_KIOSK_VOLUME),
        foreground=foreground,
        background=_find_entity(hass, device_id, "-toBackground"),
        start_url_button=_find_entity(hass, device_id, "-loadStartUrl"),
        media_player=_find_entity(hass, device_id, "-mediaplayer"),
        screen_switch=_find_entity(hass, device_id, "-screenOn"),
    )


def async_setup_kiosk_alert(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: CrywatchCoordinator
) -> KioskAlertManager | None:
    """Build the manager and wire it to the coordinator's cry-state transitions."""
    manager = build_kiosk_alert_manager(hass, entry)
    if manager is None:
        return None

    # crying state per camera key, as of the last coordinator refresh — to
    # detect ON/OFF transitions rather than re-firing on every 5s poll.
    previous: dict[str, bool] = {}

    @callback
    def _on_update() -> None:
        for key, cam in coordinator.data.items():
            was = previous.get(key, False)
            now = bool(cam.get("crying"))
            previous[key] = now
            if now and not was:
                hass.async_create_task(manager.async_alert())
            elif was and not now:
                hass.async_create_task(manager.async_revert())

    entry.async_on_unload(coordinator.async_add_listener(_on_update))
    return manager
