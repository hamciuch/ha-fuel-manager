"""Sensory Fuel Manager."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from homeassistant.util import slugify

from .analytics import compute_analytics, compute_expense_analytics, compute_live_tank
from .const import (
    CONF_CURRENCY,
    CONF_DISTANCE_TODAY_ENTITY,
    CONF_FUEL_LEVEL_ENTITY,
    CONF_FUEL_LEVEL_UNIT,
    CONF_ODOMETER_ENTITY,
    CONF_TANK_CAPACITY,
    DEFAULT_CURRENCY,
    DEFAULT_FUEL_LEVEL_UNIT,
    DEFAULT_TANK_CAPACITY,
    DOMAIN,
    SIGNAL_UPDATE,
    fuel_type_name,
)
from .data import FuelData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    data: FuelData = store["data"]

    sensors: list[SensorEntity] = [
        FuelStatSensor(entry, data, "last_fueling", "Ostatnie tankowanie",
                       lambda d: (d.last or {}).get("timestamp"),
                       device_class=SensorDeviceClass.TIMESTAMP, icon="mdi:gas-station",
                       attrs=_last_attrs),
        FuelStatSensor(entry, data, "last_odometer", "Ostatni przebieg",
                       lambda d: (d.last or {}).get("odometer"),
                       unit="km", icon="mdi:counter",
                       state_class=SensorStateClass.TOTAL_INCREASING),
        FuelStatSensor(entry, data, "last_price", "Ostatnia cena/litr",
                       lambda d: (d.last or {}).get("price_per_liter"),
                       unit="zł/L", icon="mdi:cash"),
        FuelStatSensor(entry, data, "last_cost", "Ostatnia kwota",
                       lambda d: (d.last or {}).get("total_cost"),
                       unit="zł", icon="mdi:cash-multiple"),
        FuelStatSensor(entry, data, "last_consumption", "Ostatnie spalanie",
                       lambda d: (d.last or {}).get("consumption"),
                       unit="L/100km", icon="mdi:gas-station-outline"),
        FuelStatSensor(entry, data, "avg_consumption", "Średnie spalanie",
                       lambda d: d.stats()["avg_consumption"],
                       unit="L/100km", icon="mdi:chart-line"),
        FuelStatSensor(entry, data, "avg_price", "Średnia cena/litr",
                       lambda d: d.stats()["avg_price"],
                       unit="zł/L", icon="mdi:cash"),
        FuelStatSensor(entry, data, "total_cost", "Suma kosztów paliwa",
                       lambda d: d.stats()["total_cost"],
                       unit="zł", icon="mdi:cash-multiple",
                       state_class=SensorStateClass.TOTAL_INCREASING),
        FuelStatSensor(entry, data, "total_fuel", "Suma zatankowanego paliwa",
                       lambda d: d.stats()["total_fuel"],
                       unit="L", icon="mdi:fuel",
                       state_class=SensorStateClass.TOTAL_INCREASING),
        FuelStatSensor(entry, data, "fill_count", "Liczba tankowań",
                       lambda d: d.stats()["count"],
                       unit="szt.", icon="mdi:numeric"),
        FuelStatSensor(entry, data, "cost_per_km", "Koszt na km",
                       lambda d: d.stats()["cost_per_km"],
                       unit="zł/km", icon="mdi:road-variant"),
        NearestStationSensor(entry, data, store),
        HistorySensor(entry, data),
        AnalyticsSensor(entry, data),
        ExpensesSensor(entry, data),
        LiveTankSensor(entry, data),
    ]
    async_add_entities(sensors)


def _last_attrs(d: FuelData) -> dict[str, Any]:
    last = d.last
    if not last:
        return {}
    return {
        "odometer": last.get("odometer"),
        "fuel": last.get("fuel"),
        "price_per_liter": last.get("price_per_liter"),
        "total_cost": last.get("total_cost"),
        "full": last.get("full"),
        "fuel_type": fuel_type_name(last.get("fuel_type")),
        "station_name": last.get("station_name"),
        "latitude": last.get("latitude"),
        "longitude": last.get("longitude"),
        "notes": last.get("notes"),
        "id": last.get("id"),
    }


class _Base(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, data: FuelData) -> None:
        self._entry = entry
        self._data = data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Fuel Manager",
            model="Dziennik tankowań",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(entry_id=self._entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class FuelStatSensor(_Base):
    def __init__(
        self,
        entry: ConfigEntry,
        data: FuelData,
        key: str,
        name: str,
        value_fn: Callable[[FuelData], Any],
        unit: str | None = None,
        icon: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        attrs: Callable[[FuelData], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(entry, data)
        self._value_fn = value_fn
        self._attrs_fn = attrs
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def native_value(self) -> Any:
        val = self._value_fn(self._data)
        if self.device_class == SensorDeviceClass.TIMESTAMP and isinstance(val, str):
            from homeassistant.util import dt as dt_util

            parsed = dt_util.parse_datetime(val)
            if parsed is None:
                return None
            if parsed.tzinfo is None:
                parsed = dt_util.as_local(parsed)
            return parsed
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._attrs_fn(self._data) if self._attrs_fn else None


class NearestStationSensor(_Base):
    """Najbliższa stacja – stan = nazwa, atrybuty = lista stacji."""

    _attr_icon = "mdi:map-marker-radius"

    def __init__(self, entry: ConfigEntry, data: FuelData, store: dict) -> None:
        super().__init__(entry, data)
        self._store = store
        self._attr_unique_id = f"{entry.entry_id}_nearest_station"
        self._attr_name = "Najbliższa stacja"

    @property
    def native_value(self) -> Any:
        nearby = self._store.get("nearby") or []
        return nearby[0]["name"] if nearby else "—"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nearby = self._store.get("nearby") or []
        return {
            "stations": [
                {
                    "name": s["name"],
                    "distance_m": s.get("distance_m"),
                    "distance_km": s.get("distance_km"),
                    "latitude": s.get("latitude"),
                    "longitude": s.get("longitude"),
                }
                for s in nearby
            ],
            "options": [f"{s['name']} ({s.get('distance_m')} m)" for s in nearby],
        }


class HistorySensor(_Base):
    """Pełna historia tankowań w atrybutach (do tabel/wykresów w Lovelace)."""

    _attr_icon = "mdi:history"

    def __init__(self, entry: ConfigEntry, data: FuelData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_history"
        self._attr_name = "Historia tankowań"
        self._attr_native_unit_of_measurement = "szt."

    @property
    def native_value(self) -> int:
        return len(self._data.fuelings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rows = []
        for f in self._data.fuelings[:500]:
            rows.append(
                {
                    "id": f.get("id"),
                    "timestamp": f.get("timestamp"),
                    "odometer": f.get("odometer"),
                    "fuel": f.get("fuel"),
                    "price_per_liter": f.get("price_per_liter"),
                    "total_cost": f.get("total_cost"),
                    "fuel_type": fuel_type_name(f.get("fuel_type")),
                    "fuel_type_code": f.get("fuel_type"),
                    "station_name": f.get("station_name"),
                    "consumption": f.get("consumption"),
                    "full": f.get("full"),
                }
            )
        return {"fuelings": rows}


class AnalyticsSensor(_Base):
    """Zbiorczy sensor statystyk (koszty, dystans, paliwo) – dane w atrybutach."""

    _attr_icon = "mdi:chart-box"
    _attr_native_unit_of_measurement = "zł"

    def __init__(self, entry: ConfigEntry, data: FuelData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_analytics"
        self._attr_name = "Analiza"
        self.entity_id = f"sensor.{slugify(entry.title)}_analiza"
        self.entity_id = f"sensor.{slugify(entry.title)}_analiza"

    @property
    def native_value(self) -> Any:
        return compute_analytics(self._data.fuelings).get("total_spend", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return compute_analytics(self._data.fuelings)


class ExpensesSensor(_Base):
    """Koszty dodatkowe (przegląd/ubezpieczenie/serwis...) – dane w atrybutach."""

    _attr_icon = "mdi:wrench-clock"
    _attr_native_unit_of_measurement = "zł"

    def __init__(self, entry: ConfigEntry, data: FuelData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_expenses"
        self._attr_name = "Koszty dodatkowe"
        self.entity_id = f"sensor.{slugify(entry.title)}_koszty_dodatkowe"

    @property
    def native_value(self) -> Any:
        return compute_expense_analytics(self._data.expenses).get("total", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return compute_expense_analytics(self._data.expenses)


class LiveTankSensor(_Base):
    """Statystyki bieżącego baku z encji HA (licznik + stan baku).

    Stan = koszt 1 km przejechanego na obecnym baku (zł/km).
    Cała reszta (zużycie, wydane, realny zasięg, dni do tankowania itd.) w atrybutach.
    """

    _attr_icon = "mdi:fuel-cell"

    def __init__(self, entry: ConfigEntry, data: FuelData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_current_tank"
        self._attr_name = "Bieżące tankowanie"
        self.entity_id = f"sensor.{slugify(entry.title)}_biezace_tankowanie"
        self._attr_native_unit_of_measurement = self._opt(CONF_CURRENCY, DEFAULT_CURRENCY) + "/km"

    def _opt(self, key: str, default: Any = None) -> Any:
        return self._entry.options.get(key, self._entry.data.get(key, default))

    def _tracked_entities(self) -> list[str]:
        ids = [
            self._opt(CONF_ODOMETER_ENTITY),
            self._opt(CONF_FUEL_LEVEL_ENTITY),
            self._opt(CONF_DISTANCE_TODAY_ENTITY),
        ]
        return [e for e in ids if e]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        tracked = self._tracked_entities()
        if tracked:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, tracked, self._on_source_change
                )
            )

    @callback
    def _on_source_change(self, event: Any) -> None:
        self.async_write_ha_state()

    def _compute(self) -> dict[str, Any]:
        odo_ent = self._opt(CONF_ODOMETER_ENTITY)
        fuel_ent = self._opt(CONF_FUEL_LEVEL_ENTITY)
        unit = self._opt(CONF_FUEL_LEVEL_UNIT, DEFAULT_FUEL_LEVEL_UNIT)
        capacity = float(self._opt(CONF_TANK_CAPACITY, DEFAULT_TANK_CAPACITY) or 0)

        live_odo = self.hass.states.get(odo_ent).state if odo_ent and self.hass.states.get(odo_ent) else None
        live_fuel = self.hass.states.get(fuel_ent).state if fuel_ent and self.hass.states.get(fuel_ent) else None

        try:
            an = compute_analytics(self._data.fuelings)
        except Exception:  # noqa: BLE001
            an = {}
        avg_cons = self._data.stats().get("avg_consumption")
        return compute_live_tank(
            self._data.last,
            live_odo,
            live_fuel,
            unit,
            capacity,
            avg_cons,
            an.get("avg_daily_distance"),
            an.get("avg_daily_cost"),
            an.get("total_spend"),
        )

    @property
    def native_value(self) -> Any:
        try:
            return self._compute().get("cost_per_km_tank")
        except Exception:  # noqa: BLE001
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        try:
            return self._compute()
        except Exception:  # noqa: BLE001
            return {}
