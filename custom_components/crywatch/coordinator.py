"""DataUpdateCoordinator for the Crywatch integration."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import aiohttp

from homeassistant.components.camera import async_get_stream_source
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_CAMERAS, DOMAIN, REPUSH_INTERVAL_SECONDS, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class CrywatchCoordinator(DataUpdateCoordinator[dict]):
    """Polls the crywatch_cry_detector add-on's /api/state, and keeps the
    add-on's camera list in sync with the configured cameras.

    The add-on only holds its camera list in memory, and a camera entity may
    not exist yet when this integration sets up (e.g. Frigate loads after us
    at Home Assistant startup). So a single push at setup isn't enough: every
    poll checks that each configured camera is present in the add-on's state,
    and re-resolves + re-pushes the list (throttled) when one is missing.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self._base = f"http://{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}"
        self.camera_keys: list[str] = list(entry.options.get(CONF_CAMERAS, []))
        self._last_push = 0.0
        # cameras we already warned about, so a camera that stays unresolvable
        # doesn't log a warning every REPUSH_INTERVAL_SECONDS
        self._warned: set[str] = set()
        # cameras whose cry state is forced ON by the "Simuler des pleurs"
        # button, with the timer that ends the simulation
        self._simulations: dict[str, CALLBACK_TYPE] = {}

    def is_simulating(self, key: str) -> bool:
        return key in self._simulations

    @callback
    def async_simulate_cry(self, key: str, seconds: float) -> None:
        """Hold `key`'s cry state ON for `seconds`, as if the add-on had detected
        a cry — lets automations triggered on the binary_sensor be tested without
        a real cry. Pressing again restarts the countdown."""
        if cancel := self._simulations.pop(key, None):
            cancel()

        @callback
        def _end(_now) -> None:
            self._simulations.pop(key, None)
            self.async_update_listeners()

        self._simulations[key] = async_call_later(self.hass, seconds, _end)
        self.async_update_listeners()

    @callback
    def async_cancel_simulations(self) -> None:
        for cancel in self._simulations.values():
            cancel()
        self._simulations.clear()

    async def async_push_cameras(self) -> None:
        """Resolve each configured camera entity's RTSP source and hand the list to the add-on."""
        self._last_push = time.monotonic()
        cameras = []
        for entity_id in self.camera_keys:
            try:
                url = await async_get_stream_source(self.hass, entity_id)
            except Exception as err:  # noqa: BLE001
                self._warn_once(entity_id, "could not get stream source for %s: %s", entity_id, err)
                continue
            if not url:
                self._warn_once(
                    entity_id,
                    "%s has no RTSP stream source (unsupported camera platform?), skipping",
                    entity_id,
                )
                continue
            if entity_id in self._warned:
                _LOGGER.info("stream source for %s resolved, handing it to the add-on", entity_id)
                self._warned.discard(entity_id)
            state = self.hass.states.get(entity_id)
            cameras.append({
                "key": entity_id,
                "name": state.name if state else entity_id,
                "rtsp_url": url,
            })

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                f"{self._base}/api/cameras",
                json={"cameras": cameras},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("could not push camera list to the add-on: %s", err)

    def _warn_once(self, key: str, msg: str, *args) -> None:
        level = logging.DEBUG if key in self._warned else logging.WARNING
        self._warned.add(key)
        _LOGGER.log(level, msg, *args)

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        url = f"{self._base}/api/state"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                resp.raise_for_status()
                payload = await resp.json()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"cannot reach crywatch add-on at {url}: {err}") from err
        cameras = payload.get("cameras", {})

        missing = [key for key in self.camera_keys if key not in cameras]
        if missing and time.monotonic() - self._last_push >= REPUSH_INTERVAL_SECONDS:
            _LOGGER.debug("add-on is not watching %s, re-pushing the camera list", missing)
            await self.async_push_cameras()
        return cameras
