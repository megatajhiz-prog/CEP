"""Overview of the industrial complex: descriptive data, areas with their water figures, products, meters.

One engine used by the complex page, the Excel workbook and the HTML/PDF report, so all three show the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from .model import Plant


@dataclass
class AreaRow:
    name: str
    kind: str
    subsystems: List[str]
    intake: float = 0.0
    discharge: float = 0.0
    evaporation: float = 0.0
    product: float = 0.0
    share: Optional[float] = None         # % of the plant's total intake


@dataclass
class MeterRow:
    name: str
    tag: str
    kind: str
    unit: str
    accuracy_pct: float
    calibrated: str
    days_since: Optional[int]             # None: no valid calibration date
    due: bool


def meter_due(calibrated: str, today: Optional[date] = None, max_days: int = 365):
    """(days since the last calibration or None, overdue?) A missing / invalid date counts as overdue."""
    today = today or date.today()
    try:
        d = (today - date.fromisoformat(calibrated)).days
    except (TypeError, ValueError):
        return None, True
    return d, d > max_days


def area_rows(plant: Plant) -> List[AreaRow]:
    """Every area of the site plus the subsystems that belong to none (kind ``""``, name ``""``)."""
    total = sum(s.total_intake for s in plant.leaves())
    units = plant.units()
    names = [a.name for a in plant.site.areas]
    kinds = {a.name: a.kind for a in plant.site.areas}
    for s in units:
        if s.area and s.area not in names:
            names.append(s.area)
    groups = [(n, [s for s in units if s.area == n]) for n in names]
    free = [s for s in units if not s.area or s.area not in names]
    if free:
        groups.append(("", free))
    out = []
    for n, subs in groups:
        r = AreaRow(n, kinds.get(n, ""), [s.name for s in subs],
                    sum(s.total_intake for s in subs), sum(s.total_discharge for s in subs),
                    sum(s.evaporation for s in subs), sum(s.product for s in subs))
        r.share = 100.0 * r.intake / total if total > 0 else None
        out.append(r)
    return out


def meter_rows(plant: Plant, today: Optional[date] = None) -> List[MeterRow]:
    rows = []
    for m in plant.site.meters:
        days, due = meter_due(m.calibrated, today)
        rows.append(MeterRow(m.name, m.tag, m.kind, m.unit, m.accuracy_pct, m.calibrated, days, due))
    return rows


def info_rows(plant: Plant) -> List[tuple]:
    """(label key, value) of the descriptive data that has a value; labels are i18n keys."""
    s, pf = plant.site, plant.profile
    cand = [("plant_name", plant.name), ("site_owner", s.owner), ("site_sector", s.sector), ("site_province", s.province),
            ("site_city", s.city), ("site_address", s.address), ("site_lat", s.latitude or ""), ("site_lon", s.longitude or ""),
            ("site_land", s.land_area_m2 or ""), ("site_year", s.commissioning_year or ""), ("site_shifts", s.shifts_per_day or ""),
            ("pf_working_days", pf.working_days or ""), ("production", plant.production_per_year or ""),
            ("production_unit", plant.production_unit), ("currency", plant.currency), ("site_note", s.note)]
    return [(k, v) for k, v in cand if v not in ("", None)]
