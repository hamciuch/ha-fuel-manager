"""Integracja Fuel Manager – zarządzanie tankowaniami w Home Assistant."""
from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DEVICE_TRACKER,
    CONF_PHONE_TRACKER,
    CONF_STATION_RADIUS,
    CONF_USE_OVERPASS,
    DEFAULT_OVERPASS_RADIUS,
    DEFAULT_STATION_RADIUS,
    DOMAIN,
    SERVICE_ADD_FUELING,
    SERVICE_DELETE_FUELING,
    SERVICE_EDIT_FUELING,
    SERVICE_EXPORT_FUELIO,
    SERVICE_FIND_STATIONS,
    SERVICE_IMPORT_FUELIO,
    SIGNAL_UPDATE,
)
from .data import FuelData
from .fuelio import export_fuelio, parse_fuelio
from .stations import find_overpass_stations, haversine

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

# ---- Schematy serwisów ----------------------------------------------------

_VEHICLE = {vol.Optional("vehicle"): cv.string}

ADD_SCHEMA = vol.Schema(
    {
        **_VEHICLE,
        vol.Required("odometer"): vol.Coerce(float),
        vol.Required("fuel"): vol.Coerce(float),
        vol.Optional("price_per_liter"): vol.Coerce(float),
        vol.Optional("total_cost"): vol.Coerce(float),
        vol.Optional("full", default=True): cv.boolean,
        vol.Optional("fuel_type", default=110): vol.Coerce(int),
        vol.Optional("tank_number", default=1): vol.Coerce(int),
        vol.Optional("timestamp"): cv.string,
        vol.Optional("station_name"): cv.string,
        vol.Optional("station_id"): vol.Coerce(int),
        vol.Optional("latitude"): vol.Coerce(float),
        vol.Optional("longitude"): vol.Coerce(float),
        vol.Optional("location_entity"): cv.entity_id,
        vol.Optional("notes"): cv.string,
        vol.Optional("use_phone_location", default=True): cv.boolean,
        vol.Optional("use_car_location", default=False): cv.boolean,
    }
)

EDIT_SCHEMA = vol.Schema(
    {
        **_VEHICLE,
        vol.Required("id"): cv.string,
        vol.Optional("odometer"): vol.Coerce(float),
        vol.Optional("fuel"): vol.Coerce(float),
        vol.Optional("price_per_liter"): vol.Coerce(float),
        vol.Optional("total_cost"): vol.Coerce(float),
        vol.Optional("full"): cv.boolean,
        vol.Optional("fuel_type"): vol.Coerce(int),
        vol.Optional("station_name"): cv.string,
        vol.Optional("notes"): cv.string,
    }
)

DELETE_SCHEMA = vol.Schema({**_VEHICLE, vol.Required("id"): cv.string})

IMPORT_SCHEMA = vol.Schema(
    {
        **_VEHICLE,
        vol.Exclusive("file_path", "src"): cv.string,
        vol.Exclusive("content", "src"): cv.string,
    }
)

EXPORT_SCHEMA = vol.Schema({**_VEHICLE, vol.Required("file_path"): cv.string})

FIND_SCHEMA = vol.Schema(
    {
        **_VEHICLE,
        vol.Optional("latitude"): vol.Coerce(float),
        vol.Optional("longitude"): vol.Coerce(float),
        vol.Optional("location_entity"): cv.entity_id,
        vol.Optional("use_phone_location", default=True): cv.boolean,
        vol.Optional("use_car_location", default=False): cv.boolean,
        vol.Optional("radius", default=DEFAULT_OVERPASS_RADIUS): vol.Coerce(int),
        vol.Optional("target_input_select"): cv.entity_id,
    }
)


# ---- Setup ----------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = FuelData(hass, entry.entry_id)
    await data.async_load()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "data": data,
        "entry": entry,
        "nearby": [],  # ostatni wynik wyszukiwania stacji (Overpass)
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ---- Pomocnicze -----------------------------------------------------------


def _resolve_entry(hass: HomeAssistant, vehicle: str | None) -> dict[str, Any]:
    """Zwraca słownik danych pojazdu na podstawie nazwy (lub jedynego wpisu)."""
    entries = {
        eid: d
        for eid, d in hass.data.get(DOMAIN, {}).items()
        if isinstance(d, dict) and "data" in d
    }
    if not entries:
        raise HomeAssistantError("Brak skonfigurowanego pojazdu Fuel Manager.")
    if vehicle:
        for d in entries.values():
            if d["entry"].title.lower() == vehicle.lower():
                return d
        raise HomeAssistantError(f"Nie znaleziono pojazdu '{vehicle}'.")
    if len(entries) == 1:
        return next(iter(entries.values()))
    names = ", ".join(d["entry"].title for d in entries.values())
    raise HomeAssistantError(
        f"Wiele pojazdów – podaj parametr 'vehicle' (dostępne: {names})."
    )


def _entity_coords(hass: HomeAssistant, entity_id: str | None) -> tuple[float, float] | None:
    """Czyta współrzędne (latitude/longitude) z encji device_tracker/person."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    lat = state.attributes.get("latitude")
    lon = state.attributes.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _resolve_location(
    hass: HomeAssistant, entry: ConfigEntry, data: dict[str, Any]
) -> tuple[float, float] | None:
    """Ustala lokalizację wg priorytetu.

    1) jawne latitude/longitude w wywołaniu,
    2) jawna encja `location_entity` (np. konkretny telefon),
    3) TELEFON wprowadzający tankowanie (phone_tracker) – źródło główne,
    4) AUTO (device_tracker) – opcjonalny zapas (use_car_location=true).
    """
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is not None and lon is not None:
        return float(lat), float(lon)

    if data.get("location_entity"):
        coords = _entity_coords(hass, data["location_entity"])
        if coords:
            return coords

    if data.get("use_phone_location", True):
        phone = entry.options.get(CONF_PHONE_TRACKER) or entry.data.get(
            CONF_PHONE_TRACKER
        )
        coords = _entity_coords(hass, phone)
        if coords:
            return coords

    if data.get("use_car_location", False):
        car = entry.options.get(CONF_DEVICE_TRACKER) or entry.data.get(
            CONF_DEVICE_TRACKER
        )
        coords = _entity_coords(hass, car)
        if coords:
            return coords

    return None


def _notify_update(hass: HomeAssistant, entry_id: str) -> None:
    async_dispatcher_send(hass, SIGNAL_UPDATE.format(entry_id=entry_id))


def _path_allowed(hass: HomeAssistant, path: str) -> bool:
    """Czy ścieżka jest dozwolona do odczytu/zapisu.

    Dozwolone:
      * allowlist_external_dirs (standardowe is_allowed_path),
      * katalog konfiguracyjny HA (/config, na HAOS też /homeassistant),
      * katalogi media (/media) – wygodne na HAOS (upload z panelu Media).
    Symlinki są rozwiązywane (realpath), więc działa niezależnie od montowań HAOS.
    """
    if hass.config.is_allowed_path(path):
        return True
    real = os.path.realpath(path)
    roots: list[str] = [hass.config.config_dir]
    try:
        roots.extend(hass.config.media_dirs.values())
    except AttributeError:
        pass
    for root in roots:
        if not root:
            continue
        root_real = os.path.realpath(root)
        try:
            if os.path.commonpath([real, root_real]) == root_real:
                return True
        except ValueError:
            continue
    return False


# ---- Handlery serwisów ----------------------------------------------------


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ADD_FUELING):
        return

    async def handle_add(call: ServiceCall) -> ServiceResponse:
        d = _resolve_entry(hass, call.data.get("vehicle"))
        data: FuelData = d["data"]
        entry: ConfigEntry = d["entry"]

        lat = call.data.get("latitude")
        lon = call.data.get("longitude")
        station_name = call.data.get("station_name")
        station_id = call.data.get("station_id", 0)

        # 1) ustal lokalizację: jawna -> encja -> telefon -> auto
        if lat is None or lon is None:
            coords = _resolve_location(hass, entry, call.data)
            if coords:
                lat, lon = coords

        # 2) jeśli mamy współrzędne i brak jawnej nazwy stacji -> snap do znanej
        radius = entry.options.get(CONF_STATION_RADIUS, DEFAULT_STATION_RADIUS)
        if lat is not None and lon is not None and not station_name:
            near = data.nearest_stations(lat, lon, limit=1)
            if near and near[0]["distance_m"] <= radius:
                station_name = near[0]["name"]
                station_id = near[0]["station_id"] or station_id
                lat = near[0]["latitude"]
                lon = near[0]["longitude"]

        fueling = {
            "odometer": call.data["odometer"],
            "fuel": call.data["fuel"],
            "price_per_liter": call.data.get("price_per_liter"),
            "total_cost": call.data.get("total_cost"),
            "full": call.data.get("full", True),
            "fuel_type": call.data.get("fuel_type", 110),
            "tank_number": call.data.get("tank_number", 1),
            "timestamp": call.data.get("timestamp"),
            "station_name": station_name or "",
            "station_id": station_id or 0,
            "latitude": lat,
            "longitude": lon,
            "notes": call.data.get("notes", ""),
        }
        new_id = await data.async_add(fueling)
        _notify_update(hass, entry.entry_id)
        _LOGGER.info("Dodano tankowanie %s (%s)", new_id, entry.title)
        return {"id": new_id, "station": station_name or "", "fueling": fueling}

    async def handle_edit(call: ServiceCall) -> None:
        d = _resolve_entry(hass, call.data.get("vehicle"))
        changes = {k: v for k, v in call.data.items() if k not in ("vehicle", "id")}
        ok = await d["data"].async_edit(call.data["id"], changes)
        if not ok:
            raise HomeAssistantError(f"Nie znaleziono tankowania id={call.data['id']}")
        _notify_update(hass, d["entry"].entry_id)

    async def handle_delete(call: ServiceCall) -> None:
        d = _resolve_entry(hass, call.data.get("vehicle"))
        ok = await d["data"].async_delete(call.data["id"])
        if not ok:
            raise HomeAssistantError(f"Nie znaleziono tankowania id={call.data['id']}")
        _notify_update(hass, d["entry"].entry_id)

    async def handle_import(call: ServiceCall) -> ServiceResponse:
        d = _resolve_entry(hass, call.data.get("vehicle"))
        content = call.data.get("content")
        if content is None:
            path = call.data.get("file_path")
            if not path:
                raise HomeAssistantError("Podaj 'file_path' lub 'content'.")
            if not _path_allowed(hass, path):
                raise HomeAssistantError(
                    f"Ścieżka '{path}' nie jest dozwolona. Użyj pliku w /config "
                    "lub /media, albo dodaj katalog do allowlist_external_dirs."
                )

            def _read() -> str:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()

            content = await hass.async_add_executor_job(_read)

        parsed = await hass.async_add_executor_job(parse_fuelio, content)
        added = await d["data"].async_import(parsed["fuelings"])
        _notify_update(hass, d["entry"].entry_id)
        _LOGGER.info("Zaimportowano %s tankowań do %s", added, d["entry"].title)
        return {"imported": added, "total": len(d["data"].fuelings)}

    async def handle_export(call: ServiceCall) -> ServiceResponse:
        d = _resolve_entry(hass, call.data.get("vehicle"))
        path = call.data["file_path"]
        if not _path_allowed(hass, path):
            raise HomeAssistantError(
                "Ścieżka zapisu nie jest dozwolona. Użyj katalogu /config "
                "albo dodaj go do allowlist_external_dirs."
            )
        csv_text = export_fuelio(d["entry"].title, d["data"].fuelings)

        def _write() -> None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(csv_text)

        await hass.async_add_executor_job(_write)
        return {"file": path, "count": len(d["data"].fuelings)}

    async def handle_find(call: ServiceCall) -> ServiceResponse:
        d = _resolve_entry(hass, call.data.get("vehicle"))
        entry: ConfigEntry = d["entry"]
        lat = call.data.get("latitude")
        lon = call.data.get("longitude")
        if lat is None or lon is None:
            coords = _resolve_location(hass, entry, call.data)
            if not coords:
                raise HomeAssistantError(
                    "Brak lokalizacji – podaj latitude/longitude, location_entity "
                    "lub skonfiguruj telefon/auto."
                )
            lat, lon = coords

        radius = call.data.get("radius", DEFAULT_OVERPASS_RADIUS)
        use_overpass = entry.options.get(CONF_USE_OVERPASS, True)

        stations: list[dict[str, Any]] = []
        if use_overpass:
            session = async_get_clientsession(hass)
            stations = await find_overpass_stations(session, lat, lon, radius)

        # dołącz też znane stacje z historii (mogą być bliżej / mieć ceny)
        known = d["data"].nearest_stations(lat, lon, limit=5)
        seen = {(round(s["latitude"], 4), round(s["longitude"], 4)) for s in stations}
        for k in known:
            key = (round(k["latitude"], 4), round(k["longitude"], 4))
            if key not in seen and k["distance_m"] <= radius:
                stations.append(k)
        stations.sort(key=lambda x: x["distance_m"])

        d["nearby"] = stations
        _notify_update(hass, entry.entry_id)

        # opcjonalnie wypełnij input_select nazwami stacji
        target = call.data.get("target_input_select")
        if target and stations:
            options = [
                f"{s['name']} ({s['distance_m']} m)" for s in stations
            ]
            await hass.services.async_call(
                "input_select",
                "set_options",
                {"entity_id": target, "options": options},
                blocking=True,
            )
        return {"stations": stations, "count": len(stations)}

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_FUELING, handle_add, ADD_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_EDIT_FUELING, handle_edit, EDIT_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_FUELING, handle_delete, DELETE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT_FUELIO, handle_import, IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_FUELIO, handle_export, EXPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FIND_STATIONS, handle_find, FIND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
