"""Backfill statystyk długoterminowych z historii tankowań.

Importuje statystyki zewnętrzne (external statistics) z oryginalnymi datami
z pliku Fuelio, dzięki czemu dane widać na osi czasu w Narzędziach
deweloperskich → Statystyki oraz na kartach typu "statistics graph".
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _hour(ts: str):
    dt = dt_util.parse_datetime(ts)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt_util.as_local(dt)
    # statystyki HA są godzinowe – wyrównaj do pełnej godziny
    return dt.replace(minute=0, second=0, microsecond=0)


async def async_rebuild_statistics(
    hass: HomeAssistant,
    slug: str,
    vehicle_name: str,
    currency: str,
    fuelings: list[dict[str, Any]],
) -> None:
    """Buduje i importuje statystyki zewnętrzne dla pojazdu."""
    try:
        from homeassistant.components.recorder.models import (
            StatisticData,
            StatisticMetaData,
        )
        from homeassistant.components.recorder.statistics import (
            async_add_external_statistics,
        )
    except ImportError:
        _LOGGER.warning("Recorder niedostępny – pomijam import statystyk.")
        return

    chrono = sorted(
        (f for f in fuelings if f.get("timestamp")), key=lambda x: x["timestamp"]
    )
    if not chrono:
        return

    # definicje serii: klucz -> (nazwa, jednostka, czy_suma, pole)
    series = {
        "price": (f"{vehicle_name} – cena/litr", f"{currency}/L", False, "price_per_liter"),
        "consumption": (f"{vehicle_name} – spalanie", "L/100km", False, "consumption"),
        "fill_cost": (f"{vehicle_name} – kwota tankowania", currency, False, "total_cost"),
        "odometer": (f"{vehicle_name} – przebieg", "km", False, "odometer"),
        "spend": (f"{vehicle_name} – wydatki (skum.)", currency, True, "total_cost"),
        "volume": (f"{vehicle_name} – litry (skum.)", "L", True, "fuel"),
    }

    for sid, (name, unit, is_sum, key) in series.items():
        statistic_id = f"{DOMAIN}:{slug}_{sid}"
        metadata = StatisticMetaData(
            has_mean=not is_sum,
            has_sum=is_sum,
            name=name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=unit,
        )

        rows: dict[Any, StatisticData] = {}
        running = 0.0
        for f in chrono:
            start = _hour(f["timestamp"])
            if start is None:
                continue
            val = f.get(key)
            if val is None:
                continue
            val = float(val)
            if is_sum:
                running += val
                rows[start] = StatisticData(start=start, sum=running, state=val)
            else:
                rows[start] = StatisticData(
                    start=start, mean=val, min=val, max=val
                )

        if rows:
            ordered = [rows[k] for k in sorted(rows)]
            async_add_external_statistics(hass, metadata, ordered)

    _LOGGER.info("Zaimportowano statystyki czasowe dla %s (%d tankowań)",
                 vehicle_name, len(chrono))
