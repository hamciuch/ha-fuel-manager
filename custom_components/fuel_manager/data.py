"""Menedżer danych Fuel Manager – trwałe składowanie i statystyki."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_TPL, STORAGE_VERSION
from .stations import build_station_registry, nearest_known

_LOGGER = logging.getLogger(__name__)


class FuelData:
    """Przechowuje listę tankowań jednego pojazdu i wylicza statystyki."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store: Store = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_TPL.format(entry_id=entry_id)
        )
        self.fuelings: list[dict[str, Any]] = []
        self.expenses: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data and isinstance(data.get("fuelings"), list):
            self.fuelings = data["fuelings"]
        if data and isinstance(data.get("expenses"), list):
            self.expenses = data["expenses"]
        self._sort()

    async def async_save(self) -> None:
        await self._store.async_save(
            {"fuelings": self.fuelings, "expenses": self.expenses}
        )

    def _sort(self) -> None:
        # od najnowszego do najstarszego
        self.fuelings.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        self.expenses.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # ---- KOSZTY DODATKOWE (przegląd/ubezpieczenie/serwis...) -------------

    async def async_add_expense(self, expense: dict[str, Any]) -> str:
        if not expense.get("id"):
            expense["id"] = str(uuid.uuid4())
        if not expense.get("timestamp"):
            expense["timestamp"] = datetime.now().isoformat()
        self.expenses.append(expense)
        self._sort()
        await self.async_save()
        return expense["id"]

    async def async_edit_expense(self, expense_id: str, changes: dict[str, Any]) -> bool:
        for e in self.expenses:
            if e["id"] == expense_id:
                e.update({k: v for k, v in changes.items() if v is not None})
                self._sort()
                await self.async_save()
                return True
        return False

    async def async_delete_expense(self, expense_id: str) -> bool:
        before = len(self.expenses)
        self.expenses = [e for e in self.expenses if e["id"] != expense_id]
        if len(self.expenses) != before:
            await self.async_save()
            return True
        return False

    # ---- CRUD -----------------------------------------------------------

    async def async_add(self, fueling: dict[str, Any]) -> str:
        if not fueling.get("id"):
            fueling["id"] = str(uuid.uuid4())
        if not fueling.get("timestamp"):
            fueling["timestamp"] = datetime.now().isoformat()
        # przelicz brakujące pola
        self._fill_derived(fueling)
        self.fuelings.append(fueling)
        self._sort()
        self._recalc_consumption()
        await self.async_save()
        return fueling["id"]

    async def async_edit(self, fueling_id: str, changes: dict[str, Any]) -> bool:
        for f in self.fuelings:
            if f["id"] == fueling_id:
                f.update({k: v for k, v in changes.items() if v is not None})
                self._fill_derived(f)
                self._sort()
                self._recalc_consumption()
                await self.async_save()
                return True
        return False

    async def async_delete(self, fueling_id: str) -> bool:
        before = len(self.fuelings)
        self.fuelings = [f for f in self.fuelings if f["id"] != fueling_id]
        if len(self.fuelings) != before:
            self._recalc_consumption()
            await self.async_save()
            return True
        return False

    async def async_import(self, new_fuelings: list[dict[str, Any]]) -> int:
        """Import z deduplikacją po id (guid Fuelio) oraz po sygnaturze
        (data+przebieg+litry) – chroni przed duplikatami także gdy brak guid."""
        existing = {f["id"] for f in self.fuelings}

        def _sig(f: dict[str, Any]) -> tuple:
            return (
                (f.get("timestamp") or "")[:16],
                round(f.get("odometer") or 0.0, 1),
                round(f.get("fuel") or 0.0, 2),
            )

        existing_sig = {_sig(f) for f in self.fuelings}
        added = 0
        for f in new_fuelings:
            if f.get("id") in existing or _sig(f) in existing_sig:
                continue
            self._fill_derived(f)
            self.fuelings.append(f)
            existing.add(f["id"])
            existing_sig.add(_sig(f))
            added += 1
        self._sort()
        self._recalc_consumption()
        await self.async_save()
        return added

    async def async_import_expenses(self, new_expenses: list[dict[str, Any]]) -> int:
        """Import kosztów dodatkowych z deduplikacją po id (guid Fuelio)."""
        existing = {e["id"] for e in self.expenses}
        added = 0
        for e in new_expenses:
            if not e.get("id"):
                e["id"] = str(uuid.uuid4())
            if e["id"] in existing:
                continue
            self.expenses.append(e)
            existing.add(e["id"])
            added += 1
        self._sort()
        await self.async_save()
        return added

    # ---- pola pochodne i zużycie ---------------------------------------

    @staticmethod
    def _fill_derived(f: dict[str, Any]) -> None:
        fuel = f.get("fuel")
        total = f.get("total_cost")
        ppl = f.get("price_per_liter")
        if ppl is None and total and fuel:
            f["price_per_liter"] = round(total / fuel, 3)
        elif total is None and ppl and fuel:
            f["total_cost"] = round(ppl * fuel, 2)

    def _recalc_consumption(self) -> None:
        """Liczy l/100km dla pełnych tankowań (różnica przebiegu)."""
        chrono = sorted(self.fuelings, key=lambda x: x.get("odometer") or 0)
        prev_full_odo: float | None = None
        liters_since: float = 0.0
        for f in chrono:
            odo = f.get("odometer")
            fuel = f.get("fuel") or 0.0
            liters_since += fuel
            if f.get("full") and odo is not None:
                if prev_full_odo is not None and odo > prev_full_odo:
                    dist = odo - prev_full_odo
                    f["consumption"] = round(liters_since / dist * 100, 2)
                    liters_since = 0.0
                prev_full_odo = odo

    # ---- stacje ---------------------------------------------------------

    def station_registry(self) -> list[dict[str, Any]]:
        return build_station_registry(self.fuelings)

    def nearest_stations(self, lat: float, lon: float, limit: int = 8):
        return nearest_known(lat, lon, self.station_registry(), limit)

    # ---- statystyki -----------------------------------------------------

    @property
    def last(self) -> dict[str, Any] | None:
        return self.fuelings[0] if self.fuelings else None

    def stats(self) -> dict[str, Any]:
        if not self.fuelings:
            return {
                "count": 0,
                "total_fuel": 0.0,
                "total_cost": 0.0,
                "avg_price": None,
                "avg_consumption": None,
                "total_distance": 0.0,
                "cost_per_km": None,
            }
        total_fuel = sum(f.get("fuel") or 0.0 for f in self.fuelings)
        total_cost = sum(f.get("total_cost") or 0.0 for f in self.fuelings)
        odos = [f["odometer"] for f in self.fuelings if f.get("odometer")]
        total_distance = (max(odos) - min(odos)) if len(odos) >= 2 else 0.0
        avg_cons = self._avg_consumption()
        return {
            "count": len(self.fuelings),
            "total_fuel": round(total_fuel, 2),
            "total_cost": round(total_cost, 2),
            "avg_price": round(total_cost / total_fuel, 3) if total_fuel else None,
            "avg_consumption": avg_cons,
            "total_distance": round(total_distance, 1),
            "cost_per_km": round(total_cost / total_distance, 3) if total_distance else None,
        }

    def _avg_consumption(self) -> float | None:
        """Średnia ważona dystansem (jak Fuelio): całe zużyte paliwo / cały
        dystans między pełnymi bakami × 100. Pomija paliwo sprzed 1. pełnego baku
        (nieznany stan początkowy)."""
        chrono = sorted(self.fuelings, key=lambda x: x.get("odometer") or 0)
        prev_full: float | None = None
        liters_since = 0.0
        total_fuel = 0.0
        total_dist = 0.0
        for f in chrono:
            odo = f.get("odometer")
            full = f.get("full")
            if full and odo is not None and prev_full is None:
                # pierwszy pełny bak: punkt startowy, odrzuć paliwo sprzed niego
                prev_full = odo
                liters_since = 0.0
                continue
            liters_since += f.get("fuel") or 0.0
            if full and odo is not None and prev_full is not None and odo > prev_full:
                total_dist += odo - prev_full
                total_fuel += liters_since
                liters_since = 0.0
                prev_full = odo
        if total_dist <= 0:
            return None
        return round(total_fuel / total_dist * 100, 2)
