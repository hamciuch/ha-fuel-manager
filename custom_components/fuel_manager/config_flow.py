"""Config flow dla Fuel Manager."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CURRENCY,
    CONF_DEFAULT_FUEL_TYPE,
    CONF_DEVICE_TRACKER,
    CONF_PHONE_TRACKER,
    CONF_STATION_RADIUS,
    CONF_TANK_CAPACITY,
    CONF_USE_OVERPASS,
    DEFAULT_CURRENCY,
    DEFAULT_FUEL_TYPE,
    DEFAULT_NAME,
    DEFAULT_STATION_RADIUS,
    DEFAULT_TANK_CAPACITY,
    DOMAIN,
    FUEL_TYPES,
)

_FUEL_OPTIONS = [
    selector.SelectOptionDict(value=str(code), label=name)
    for code, name in FUEL_TYPES.items()
]


class FuelManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Kreator dodawania pojazdu."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input["name"].lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input["name"],
                data={"name": user_input["name"]},
                options={
                    CONF_CURRENCY: user_input.get(CONF_CURRENCY, DEFAULT_CURRENCY),
                    CONF_TANK_CAPACITY: user_input.get(
                        CONF_TANK_CAPACITY, DEFAULT_TANK_CAPACITY
                    ),
                    CONF_DEFAULT_FUEL_TYPE: int(
                        user_input.get(CONF_DEFAULT_FUEL_TYPE, DEFAULT_FUEL_TYPE)
                    ),
                    CONF_PHONE_TRACKER: user_input.get(CONF_PHONE_TRACKER),
                    CONF_DEVICE_TRACKER: user_input.get(CONF_DEVICE_TRACKER),
                    CONF_STATION_RADIUS: user_input.get(
                        CONF_STATION_RADIUS, DEFAULT_STATION_RADIUS
                    ),
                    CONF_USE_OVERPASS: user_input.get(CONF_USE_OVERPASS, True),
                },
            )

        schema = vol.Schema(
            {
                vol.Required("name", default=DEFAULT_NAME): str,
                vol.Optional(CONF_CURRENCY, default=DEFAULT_CURRENCY): str,
                vol.Optional(
                    CONF_TANK_CAPACITY, default=DEFAULT_TANK_CAPACITY
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_DEFAULT_FUEL_TYPE, default=str(DEFAULT_FUEL_TYPE)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_FUEL_OPTIONS)
                ),
                vol.Optional(CONF_PHONE_TRACKER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                ),
                vol.Optional(CONF_DEVICE_TRACKER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["device_tracker", "person"])
                ),
                vol.Optional(
                    CONF_STATION_RADIUS, default=DEFAULT_STATION_RADIUS
                ): vol.Coerce(int),
                vol.Optional(CONF_USE_OVERPASS, default=True): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return FuelManagerOptionsFlow(entry)


class FuelManagerOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if user_input.get(CONF_DEFAULT_FUEL_TYPE):
                user_input[CONF_DEFAULT_FUEL_TYPE] = int(
                    user_input[CONF_DEFAULT_FUEL_TYPE]
                )
            return self.async_create_entry(title="", data=user_input)

        o = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CURRENCY, default=o.get(CONF_CURRENCY, DEFAULT_CURRENCY)
                ): str,
                vol.Optional(
                    CONF_TANK_CAPACITY,
                    default=o.get(CONF_TANK_CAPACITY, DEFAULT_TANK_CAPACITY),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_DEFAULT_FUEL_TYPE,
                    default=str(o.get(CONF_DEFAULT_FUEL_TYPE, DEFAULT_FUEL_TYPE)),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_FUEL_OPTIONS)
                ),
                vol.Optional(
                    CONF_PHONE_TRACKER,
                    description={"suggested_value": o.get(CONF_PHONE_TRACKER)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                ),
                vol.Optional(
                    CONF_DEVICE_TRACKER,
                    description={
                        "suggested_value": o.get(CONF_DEVICE_TRACKER)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["device_tracker", "person"])
                ),
                vol.Optional(
                    CONF_STATION_RADIUS,
                    default=o.get(CONF_STATION_RADIUS, DEFAULT_STATION_RADIUS),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_USE_OVERPASS, default=o.get(CONF_USE_OVERPASS, True)
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
