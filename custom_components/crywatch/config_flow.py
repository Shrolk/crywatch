"""Config flow for the Crywatch integration."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_HOST, DEFAULT_PORT, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def _can_connect(hass, host: str, port: int) -> bool:
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"http://{host}:{port}/api/state",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 - any connect/timeout error means "can't connect"
        return False


class CrywatchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crywatch."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST], user_input[CONF_PORT]
            if await _can_connect(self.hass, host, port):
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Crywatch", data=user_input)
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
