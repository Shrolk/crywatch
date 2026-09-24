"""Config flow for the Crywatch integration."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CAMERAS,
    CONF_FULLY_KIOSK_DEVICE,
    CONF_KIOSK_URL,
    CONF_KIOSK_VOLUME,
    DEFAULT_HOST,
    DEFAULT_KIOSK_VOLUME,
    DEFAULT_PORT,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


def _cameras_schema(
    cameras: list[str] | None = None,
    kiosk_device: str | None = None,
    kiosk_url: str = "",
    kiosk_volume: int = DEFAULT_KIOSK_VOLUME,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_CAMERAS, default=cameras or []): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="camera", multiple=True)
            ),
            # Optional: wake a Fully Kiosk PLUS device and show the camera + sound
            # when a cry is detected. Left empty, no kiosk action is triggered.
            vol.Optional(CONF_FULLY_KIOSK_DEVICE, default=kiosk_device): selector.DeviceSelector(
                selector.DeviceSelectorConfig(integration="fully_kiosk")
            ),
            vol.Optional(CONF_KIOSK_URL, default=kiosk_url): selector.TextSelector(),
            vol.Optional(CONF_KIOSK_VOLUME, default=kiosk_volume): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=5, unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
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
    """Handle a config flow for Crywatch: connect to the add-on, then pick cameras."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST], user_input[CONF_PORT]
            if await _can_connect(self.hass, host, port):
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                self._host, self._port = host, port
                return await self.async_step_cameras()
            errors["base"] = "cannot_connect"

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_cameras(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Crywatch",
                data={CONF_HOST: self._host, CONF_PORT: self._port},
                options=user_input,
            )
        return self.async_show_form(step_id="cameras", data_schema=_cameras_schema())

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return CrywatchOptionsFlow(config_entry)


class CrywatchOptionsFlow(config_entries.OptionsFlow):
    """Lets you add/remove cameras after initial setup, without redoing the whole flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        opts = self.config_entry.options
        schema = _cameras_schema(
            cameras=opts.get(CONF_CAMERAS, []),
            kiosk_device=opts.get(CONF_FULLY_KIOSK_DEVICE),
            kiosk_url=opts.get(CONF_KIOSK_URL, ""),
            kiosk_volume=opts.get(CONF_KIOSK_VOLUME, DEFAULT_KIOSK_VOLUME),
        )
        return self.async_show_form(step_id="init", data_schema=schema)
