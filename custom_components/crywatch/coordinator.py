"""DataUpdateCoordinator for the Crywatch integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class CrywatchCoordinator(DataUpdateCoordinator[dict]):
    """Polls the crywatch_cry_detector add-on's /api/state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self._url = f"http://{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}/api/state"

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                self._url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                resp.raise_for_status()
                payload = await resp.json()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"cannot reach crywatch add-on at {self._url}: {err}") from err
        return payload.get("cameras", {})
