"""Obliczenia statystyk (koszty, dystans, paliwo) dla dashboardu."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

PL_MONTHS = ["sty", "lut", "mar", "kwi", "maj", "cze",
             "lip", "sie", "wrz", "paź", "lis", "gru"]


def _parse(ts: Any) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _r(x: float, n: int = 2) -> float:
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return 0.0


def _empty() -> dict[str, Any]:
    keys0 = [
        "total_spend", "spend_this_year", "spend_prev_year",
        "min_price", "max_price", "min_bill", "max_bill",
        "avg_cost_per_km", "min_cost_per_km", "max_cost_per_km",
        "avg_daily_cost", "cost_this_year",
        "total_distance", "distance_this_year", "distance_prev_year",
        "min_segment_distance", "max_segment_distance", "avg_segment_distance",
        "avg_daily_distance",
        "total_fuel", "fuel_this_year", "fuel_prev_year",
        "min_fill", "max_fill", "avg_fill", "avg_daily_fuel",
        "fill_count", "days_span",
    ]
    d: dict[str, Any] = {k: 0 for k in keys0}
    d.update({
        "this_year": datetime.now().year,
        "prev_year": datetime.now().year - 1,
        "spend_by_year": {}, "distance_by_year": {}, "fuel_by_year": {},
        "monthly": [],
    })
    return d


def compute_analytics(fuelings: list[dict[str, Any]]) -> dict[str, Any]:
    """Policz komplet statystyk z listy tankowań."""
    fs = [f for f in fuelings if f.get("odometer") is not None]
    if not fs:
        return _empty()

    now = datetime.now()
    cur_year, prev_year = now.year, now.year - 1

    # uporządkowane chronologicznie (po czasie, a brak czasu -> po przebiegu)
    fs_t = sorted(
        fs,
        key=lambda f: (_parse(f.get("timestamp")) or datetime.min, f.get("odometer") or 0),
    )

    total_spend = sum(f.get("total_cost") or 0 for f in fs)
    total_fuel = sum(f.get("fuel") or 0 for f in fs)
    odos = [f["odometer"] for f in fs if f.get("odometer") is not None]
    total_distance = (max(odos) - min(odos)) if len(odos) >= 2 else 0
    prices = [f["price_per_liter"] for f in fs if f.get("price_per_liter")]
    bills = [f["total_cost"] for f in fs if f.get("total_cost")]
    fills = [f["fuel"] for f in fs if f.get("fuel")]

    # segmenty (po kolejnych tankowaniach chronologicznie)
    seg_dist: list[float] = []
    seg_costkm: list[float] = []
    for i in range(1, len(fs_t)):
        d = (fs_t[i].get("odometer") or 0) - (fs_t[i - 1].get("odometer") or 0)
        if d > 0:
            seg_dist.append(d)
            c = fs_t[i].get("total_cost") or 0
            if c > 0:
                seg_costkm.append(c / d)

    # agregaty roczne
    spend_year: dict[int, float] = defaultdict(float)
    fuel_year: dict[int, float] = defaultdict(float)
    dist_year: dict[int, float] = defaultdict(float)
    for f in fs_t:
        dt = _parse(f.get("timestamp"))
        if dt:
            spend_year[dt.year] += f.get("total_cost") or 0
            fuel_year[dt.year] += f.get("fuel") or 0
    for i in range(1, len(fs_t)):
        dt = _parse(fs_t[i].get("timestamp"))
        d = (fs_t[i].get("odometer") or 0) - (fs_t[i - 1].get("odometer") or 0)
        if dt and d > 0:
            dist_year[dt.year] += d

    # zakres dni
    dates = [dt for dt in (_parse(f.get("timestamp")) for f in fs_t) if dt]
    days_span = max((dates[-1] - dates[0]).days, 1) if len(dates) >= 2 else 1

    # miesięcznie (klucz YYYY-MM)
    m_spend: dict[str, float] = defaultdict(float)
    m_fuel: dict[str, float] = defaultdict(float)
    m_dist: dict[str, float] = defaultdict(float)
    for f in fs_t:
        dt = _parse(f.get("timestamp"))
        if dt:
            k = f"{dt.year}-{dt.month:02d}"
            m_spend[k] += f.get("total_cost") or 0
            m_fuel[k] += f.get("fuel") or 0
    for i in range(1, len(fs_t)):
        dt = _parse(fs_t[i].get("timestamp"))
        d = (fs_t[i].get("odometer") or 0) - (fs_t[i - 1].get("odometer") or 0)
        if dt and d > 0:
            m_dist[f"{dt.year}-{dt.month:02d}"] += d

    # ostatnie 14 miesięcy (do porównań rok do roku)
    seq: list[tuple[int, int]] = []
    for k in range(13, -1, -1):
        yy, mm = now.year, now.month - k
        while mm <= 0:
            mm += 12
            yy -= 1
        seq.append((yy, mm))
    monthly = []
    for yy, mm in seq:
        key = f"{yy}-{mm:02d}"
        ts = int(datetime(yy, mm, 1).timestamp() * 1000)
        monthly.append({
            "key": key,
            "label": f"{PL_MONTHS[mm - 1]} {yy}",
            "ts": ts,
            "spend": _r(m_spend.get(key, 0)),
            "fuel": _r(m_fuel.get(key, 0)),
            "dist": _r(m_dist.get(key, 0), 0),
        })

    return {
        "this_year": cur_year,
        "prev_year": prev_year,
        "fill_count": len(fs),
        "days_span": days_span,
        # KOSZTY
        "total_spend": _r(total_spend),
        "spend_this_year": _r(spend_year.get(cur_year, 0)),
        "spend_prev_year": _r(spend_year.get(prev_year, 0)),
        "spend_by_year": {str(k): _r(v) for k, v in sorted(spend_year.items())},
        "min_price": _r(min(prices), 3) if prices else 0,
        "max_price": _r(max(prices), 3) if prices else 0,
        "min_bill": _r(min(bills)) if bills else 0,
        "max_bill": _r(max(bills)) if bills else 0,
        "avg_cost_per_km": _r(total_spend / total_distance, 3) if total_distance else 0,
        "min_cost_per_km": _r(min(seg_costkm), 3) if seg_costkm else 0,
        "max_cost_per_km": _r(max(seg_costkm), 3) if seg_costkm else 0,
        "avg_daily_cost": _r(total_spend / days_span),
        "cost_this_year": _r(spend_year.get(cur_year, 0)),
        # ODLEGŁOŚĆ
        "total_distance": _r(total_distance, 0),
        "distance_this_year": _r(dist_year.get(cur_year, 0), 0),
        "distance_prev_year": _r(dist_year.get(prev_year, 0), 0),
        "distance_by_year": {str(k): _r(v, 0) for k, v in sorted(dist_year.items())},
        "min_segment_distance": _r(min(seg_dist), 0) if seg_dist else 0,
        "max_segment_distance": _r(max(seg_dist), 0) if seg_dist else 0,
        "avg_segment_distance": _r(sum(seg_dist) / len(seg_dist), 0) if seg_dist else 0,
        "avg_daily_distance": _r(total_distance / days_span, 1),
        # PALIWO
        "total_fuel": _r(total_fuel),
        "fuel_this_year": _r(fuel_year.get(cur_year, 0)),
        "fuel_prev_year": _r(fuel_year.get(prev_year, 0)),
        "fuel_by_year": {str(k): _r(v) for k, v in sorted(fuel_year.items())},
        "min_fill": _r(min(fills)) if fills else 0,
        "max_fill": _r(max(fills)) if fills else 0,
        "avg_fill": _r(total_fuel / len(fills)) if fills else 0,
        "avg_daily_fuel": _r(total_fuel / days_span),
        # WYKRES
        "monthly": monthly,
    }


def compute_expense_analytics(expenses: list[dict[str, Any]]) -> dict[str, Any]:
    """Statystyki kosztów dodatkowych (przegląd/ubezpieczenie/serwis...)."""
    now = datetime.now()
    cur_year, prev_year = now.year, now.year - 1
    es = [e for e in (expenses or []) if e.get("amount") is not None]
    if not es:
        return {
            "this_year": cur_year, "prev_year": prev_year,
            "total": 0, "this_year_total": 0, "prev_year_total": 0,
            "count": 0, "by_category": {}, "by_year": {}, "items": [],
        }
    by_cat: dict[str, float] = defaultdict(float)
    by_year: dict[int, float] = defaultdict(float)
    total = 0.0
    for e in es:
        amt = float(e.get("amount") or 0)
        total += amt
        by_cat[e.get("category") or "Inne"] += amt
        dt = _parse(e.get("timestamp"))
        if dt:
            by_year[dt.year] += amt
    items = []
    for e in sorted(es, key=lambda x: x.get("timestamp") or "", reverse=True)[:200]:
        dt = _parse(e.get("timestamp"))
        items.append({
            "id": e.get("id"),
            "timestamp": e.get("timestamp"),
            "date": dt.strftime("%Y-%m-%d") if dt else "",
            "category": e.get("category") or "Inne",
            "amount": _r(e.get("amount") or 0),
            "odometer": e.get("odometer"),
            "description": e.get("description") or "",
        })
    return {
        "this_year": cur_year, "prev_year": prev_year,
        "total": _r(total),
        "this_year_total": _r(by_year.get(cur_year, 0)),
        "prev_year_total": _r(by_year.get(prev_year, 0)),
        "count": len(es),
        "by_category": {k: _r(v) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])},
        "by_year": {str(k): _r(v) for k, v in sorted(by_year.items())},
        "items": items,
    }
