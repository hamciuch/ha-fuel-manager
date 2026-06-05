"""Parser/eksporter formatu CSV aplikacji Fuelio.

Plik Fuelio ma kilka sekcji rozdzielonych nagłówkami `## NazwaSekcji`:
    ## Vehicle      – metadane pojazdu (1 wiersz danych)
    ## Log          – dziennik tankowań (interesuje nas najbardziej)
    ## CostCategories / ## Costs / ## Category – koszty i kategorie

Czytamy sekcję `## Log`. Każdy wiersz to jedno tankowanie.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Kolejność kolumn w nagłówku sekcji Log (Fuelio):
# Data, Odo (km), Fuel (litres), Full, Price (optional), l/100km (optional),
# latitude (optional), longitude (optional), City (optional), Notes (optional),
# Missed, TankNumber, FuelType, VolumePrice, StationID (optional),
# ExcludeDistance, UniqueId, TankCalc, Weather, guid, lastupdated


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", ".")
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str | None, default: int = 0) -> int:
    f = _to_float(value)
    return default if f is None else int(f)


def _parse_dt(value: str) -> str:
    """Fuelio: 'YYYY-MM-DD HH:MM' lub 'YYYY-MM-DD'. Zwraca ISO 8601 (lokalny->UTC naive ISO)."""
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    # awaryjnie – teraz
    return datetime.now().isoformat()


def parse_fuelio(content: str) -> dict[str, Any]:
    """Parsuje treść pliku Fuelio CSV.

    Zwraca: {"vehicle": {...}|None, "fuelings": [ {...}, ... ]}
    """
    lines = content.splitlines()
    section: str | None = None
    header: list[str] | None = None

    vehicle: dict[str, Any] | None = None
    fuelings: list[dict[str, Any]] = []

    for raw in lines:
        if raw.strip() == "":
            continue
        # Nagłówek sekcji, np. "## Log"
        stripped = raw.strip().strip('"')
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            header = None
            continue
        # Pierwszy wiersz po nagłówku sekcji to nagłówek kolumn
        row = next(csv.reader(io.StringIO(raw)))
        if header is None:
            header = [c.strip() for c in row]
            continue

        if section == "Vehicle":
            vehicle = dict(zip(header, row))
        elif section == "Log":
            ts = _parse_dt(row[0])
            odo = _to_float(row[1]) or 0.0
            fuel = _to_float(row[2]) or 0.0
            full = _to_int(row[3], 1)
            total = _to_float(row[4])
            cons = _to_float(row[5])
            lat = _to_float(row[6])
            lon = _to_float(row[7])
            city = (row[8] or "").strip() if len(row) > 8 else ""
            notes = (row[9] or "").strip() if len(row) > 9 else ""
            tank = _to_int(row[11], 1) if len(row) > 11 else 1
            ftype = _to_int(row[12], 0) if len(row) > 12 else 0
            vprice = _to_float(row[13]) if len(row) > 13 else None
            station_id = _to_int(row[14], 0) if len(row) > 14 else 0
            src_guid = row[19].strip() if len(row) > 19 else ""

            # cena/litr: użyj VolumePrice; jeśli brak – policz total/fuel
            if vprice is None and total and fuel:
                vprice = round(total / fuel, 3)

            # współrzędne 0.0/0.0 traktujemy jak brak lokalizacji
            if lat == 0.0 and lon == 0.0:
                lat = lon = None

            fuelings.append(
                {
                    "id": src_guid or str(uuid.uuid4()),
                    "timestamp": ts,
                    "odometer": odo,
                    "fuel": fuel,
                    "price_per_liter": vprice,
                    "total_cost": total,
                    "full": bool(full),
                    "fuel_type": ftype,
                    "latitude": lat,
                    "longitude": lon,
                    "station_name": city,
                    "station_id": station_id,
                    "notes": notes,
                    "tank_number": tank,
                    "consumption": cons,
                }
            )

    return {"vehicle": vehicle, "fuelings": fuelings}


def export_fuelio(vehicle_name: str, fuelings: list[dict[str, Any]]) -> str:
    """Buduje plik CSV w formacie Fuelio (sekcja Log) z listy tankowań."""
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL)

    writer.writerow(["## Vehicle"])
    writer.writerow(
        ["Name", "Description", "DistUnit", "FuelUnit", "ConsumptionUnit",
         "ImportCSVDateFormat", "VIN", "Insurance", "Plate", "Make", "Model",
         "Year", "TankCount", "Tank1Type", "Tank2Type", "Active"]
    )
    writer.writerow([vehicle_name, "", "0", "0", "0", "yyyy-MM-dd",
                     "", "", "", "", "", "", "1", "0", "0", "1"])

    writer.writerow(["## Log"])
    writer.writerow(
        ["Data", "Odo (km)", "Fuel (litres)", "Full", "Price (optional)",
         "l/100km (optional)", "latitude (optional)", "longitude (optional)",
         "City (optional)", "Notes (optional)", "Missed", "TankNumber",
         "FuelType", "VolumePrice", "StationID (optional)", "ExcludeDistance",
         "UniqueId", "TankCalc", "Weather", "guid", "lastupdated"]
    )

    # od najstarszego
    for i, f in enumerate(sorted(fuelings, key=lambda x: x["timestamp"]), start=1):
        try:
            dt = datetime.fromisoformat(f["timestamp"])
            ts = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, KeyError):
            ts = f.get("timestamp", "")
        last_upd = int(datetime.now(timezone.utc).timestamp() * 1000)
        writer.writerow(
            [
                ts,
                f.get("odometer") or 0.0,
                f.get("fuel") or 0.0,
                "1" if f.get("full") else "0",
                f.get("total_cost") or "",
                f.get("consumption") or "",
                f.get("latitude") or "0.0",
                f.get("longitude") or "0.0",
                f.get("station_name") or "",
                f.get("notes") or "",
                "0",
                f.get("tank_number") or 1,
                f.get("fuel_type") or 0,
                f.get("price_per_liter") or "",
                f.get("station_id") or 0,
                "0.0",
                str(i),
                "0.0",
                "",
                f.get("id") or str(uuid.uuid4()),
                str(last_upd),
            ]
        )
    return out.getvalue()
