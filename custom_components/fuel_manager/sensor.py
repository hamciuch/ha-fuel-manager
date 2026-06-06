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

from .const import DOMAIN, SIGNAL_UPDATE, fuel_type_name
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
                    "station_name": f.get("station_name"),
                    "consumption": f.get("consumption"),
                    "full": f.get("full"),
                }
            )
        return {"fuelings": rows}
