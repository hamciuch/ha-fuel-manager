"""Wyszukiwanie najbliższych stacji paliw.

Dwa źródła:
1) Historia tankowań – buduje rejestr znanych stacji (z nazwą, współrzędnymi,
   StationID z Fuelio). Pozwala "snapować" nowe tankowanie do znanej stacji.
2) OpenStreetMap (Overpass API) – opcjonalne wyszukiwanie nowych stacji
   w promieniu wokół bieżącej pozycji auta. Nie wymaga klucza API.
"""
from __future__ import annotations

import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any

_LOGGER = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Odległość w metrach między dwoma punktami GPS."""
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def build_station_registry(fuelings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Buduje listę unikalnych stacji z historii tankowań.

    Klucz unikalności: StationID (jeśli != 0), w innym wypadku zaokrąglone GPS.
    """
    registry: dict[str, dict[str, Any]] = {}
    for f in fuelings:
        lat = f.get("latitude")
        lon = f.get("longitude")
        sid = f.get("station_id") or 0
        name = (f.get("station_name") or "").strip()
        if lat is None or lon is None:
            continue
        if sid:
            key = f"sid:{sid}"
        else:
            key = f"geo:{round(lat, 4)}:{round(lon, 4)}"

        entry = registry.get(key)
        if entry is None:
            registry[key] = {
                "key": key,
                "name": name or "Stacja",
                "latitude": lat,
                "longitude": lon,
                "station_id": sid,
                "count": 1,
                "last_used": f.get("timestamp"),
            }
        else:
            entry["count"] += 1
            if name and entry["name"] in ("", "Stacja"):
                entry["name"] = name
            if f.get("timestamp", "") > (entry.get("last_used") or ""):
                entry["last_used"] = f.get("timestamp")
                entry["latitude"] = lat
                entry["longitude"] = lon
    return list(registry.values())


def nearest_known(
    lat: float, lon: float, registry: list[dict[str, Any]], limit: int = 8
) -> list[dict[str, Any]]:
    """Sortuje znane stacje wg odległości od podanego punktu."""
    scored = []
    for st in registry:
        dist = haversine(lat, lon, st["latitude"], st["longitude"])
        item = dict(st)
        item["distance_m"] = round(dist)
        item["distance_km"] = round(dist / 1000, 2)
        scored.append(item)
    scored.sort(key=lambda x: x["distance_m"])
    return scored[:limit]


async def find_overpass_stations(
    session, lat: float, lon: float, radius: int = 1500, limit: int = 10
) -> list[dict[str, Any]]:
    """Wyszukuje stacje paliw w OSM (Overpass) w promieniu `radius` metrów.

    `session` to aiohttp ClientSession z HA (async_get_clientsession).
    """
    query = (
        "[out:json][timeout:25];"
        f"(node[\"amenity\"=\"fuel\"](around:{radius},{lat},{lon});"
        f"way[\"amenity\"=\"fuel\"](around:{radius},{lat},{lon}););"
        "out center tags;"
    )
    try:
        async with session.post(OVERPASS_URL, data={"data": query}, timeout=30) as resp:
            if resp.status != 200:
                _LOGGER.warning("Overpass zwrócił status %s", resp.status)
                return []
            data = await resp.json()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Błąd zapytania Overpass: %s", err)
        return []

    results: list[dict[str, Any]] = []
    for el in data.get("elements", []):
        if el["type"] == "node":
            slat, slon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            slat, slon = center.get("lat"), center.get("lon")
        if slat is None or slon is None:
            continue
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("brand") or "Stacja paliw"
        dist = haversine(lat, lon, slat, slon)
        results.append(
            {
                "name": name,
                "brand": tags.get("brand", ""),
                "latitude": slat,
                "longitude": slon,
                "station_id": 0,
                "distance_m": round(dist),
                "distance_km": round(dist / 1000, 2),
                "osm_id": f"{el['type']}/{el['id']}",
            }
        )
    results.sort(key=lambda x: x["distance_m"])
    return results[:limit]
