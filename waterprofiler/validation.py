"""Plausibility checks of the entered time series and of the annual model.

Nothing here changes data: each problem is reported with where it is and what to look at.

* a single value: negative amounts, load factors above 1, temperatures out of range, more pump hours than the period has;
* a series: stretches of 10 days or more missing *between* its first and last data (a gap);
* a period: a subsystem that sends out (discharge + evaporation + product) clearly more water than it takes in, or the
  outlets of the plant discharging more than its sources supply;
* the annual model: the same two balance checks on the fixed totals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Sequence

from . import jcalendar as cal
from . import timeseries as TS
from .model import Plant

TOLERANCE = 0.05            # a balance may be off by 5 % (meters, evaporation) before it is reported


@dataclass
class Issue:
    level: str              # "error" | "warn"
    key: str                # the series key ("" for the annual model)
    when: str               # period label ("" if not about a period)
    fa: str
    en: str

    def text(self, lang: str) -> str:
        return self.fa if lang == "fa" else self.en


def bad_value(key: str, value: Optional[float], days: int = 365) -> Optional[tuple]:
    """(fa, en) message when one value is impossible, else None. ``days`` is the length of the period it belongs to."""
    if value is None:
        return None
    if key.endswith(":load") and value > 1.0 + 1e-9:
        return ("ضریب بار پمپ نمی‌تواند بیش از ۱ باشد", "A pump load factor cannot exceed 1")
    if key.endswith(":hours") and value > 24.0 * max(days, 1) + 1e-9:
        return ("ساعت کارکرد پمپ از ساعت‌های آن دوره بیشتر است", "Pump hours exceed the hours of the period")
    if key.endswith(":t_in") or key.endswith(":t_ww") or key == "env:temp":
        if not -30.0 <= value <= 90.0:
            return ("دما خارج از بازهٔ معقول (۳۰- تا ۹۰ درجه) است", "Temperature outside the plausible range (-30 to 90 °C)")
        return None
    if value < 0 and key != "env:temp":
        return ("مقدار منفی ممکن نیست", "A negative value is not possible")
    return None


GAP_DAYS = 10               # a hole in a series shorter than this is not reported


def gaps(plant: Plant, key: str) -> List[tuple]:
    """Holes (start, end) of at least ``GAP_DAYS`` days between the first and the last point of a series."""
    pts = plant.series.get(key, [])
    if len(pts) < 2:
        return []
    iv = sorted((date.fromisoformat(p.start), date.fromisoformat(p.end)) for p in pts)
    out, reach = [], iv[0][1]
    for a, b in iv[1:]:
        if (a - reach).days - 1 >= GAP_DAYS:
            out.append((reach + timedelta(days=1), a - timedelta(days=1)))
        reach = max(reach, b)
    return out


def check(plant: Plant, slices: Sequence[cal.Slice], calendar: str = "jalali") -> List[Issue]:
    issues: List[Issue] = []
    specs = {s.key: s for s in TS.catalog(plant)}

    # -- single values
    for key, pts in plant.series.items():
        sp = specs.get(key)
        if sp is None:
            continue
        for p in pts:
            d = (date.fromisoformat(p.end) - date.fromisoformat(p.start)).days + 1
            msg = bad_value(key, p.value, d if sp.agg == "sum" or key.endswith(":hours") else 1)
            if msg:
                issues.append(Issue("error", key, f"{p.start} → {p.end}", f"{sp.fa}: {msg[0]}", f"{sp.en}: {msg[1]}"))

    # -- gaps inside a series
    for key in plant.series:
        sp = specs.get(key)
        g = gaps(plant, key) if sp else []
        if g:
            shown = "، ".join(f"{a} تا {b}" for a, b in g[:3]) + (" …" if len(g) > 3 else "")
            shown_en = ", ".join(f"{a} to {b}" for a, b in g[:3]) + (" …" if len(g) > 3 else "")
            issues.append(Issue("warn", key, "", f"{sp.fa}: {len(g)} بازهٔ خالی بین اولین و آخرین داده ({shown})",
                                f"{sp.en}: {len(g)} empty stretch(es) between the first and the last data ({shown_en})"))

    # -- balance per period
    def per(key: str) -> List[Optional[float]]:
        return TS.slice_values(plant, key, slices)

    for sub in plant.subsystems:
        i, d, e, pr = (per(f"sub:{sub.name}:{f}") for f in ("intake", "discharge", "evaporation", "product"))
        for k, sl in enumerate(slices):
            if i[k] is None or d[k] is None:
                continue
            out = d[k] + (e[k] or 0.0) + (pr[k] or 0.0)
            if i[k] > 0 and out > i[k] * (1 + TOLERANCE) + 1e-9:
                issues.append(Issue("warn", f"sub:{sub.name}:discharge", sl.label,
                                    f"{sub.name}: خروجی ({out:,.0f}) بیش از برداشت ({i[k]:,.0f}) متر مکعب است",
                                    f"{sub.name}: outflow ({out:,.0f}) exceeds intake ({i[k]:,.0f}) m³"))
    src = [per(f"source:{s.name}") for s in plant.sources]
    out_ = [per(f"outlet:{o.name}") for o in plant.outlets]
    for k, sl in enumerate(slices):
        a = [x[k] for x in src if x and x[k] is not None]
        b = [x[k] for x in out_ if x and x[k] is not None]
        if a and b and len(a) == len(plant.sources) and len(b) == len(plant.outlets):
            sa, sb = sum(a), sum(b)
            if sa > 0 and sb > sa * (1 + TOLERANCE) + 1e-9:
                issues.append(Issue("warn", "", sl.label,
                                    f"تخلیه به مقاصد ({sb:,.0f}) بیش از برداشت از منابع ({sa:,.0f}) متر مکعب است",
                                    f"Discharge to outlets ({sb:,.0f}) exceeds withdrawal from sources ({sa:,.0f}) m³"))

    # -- the annual model
    for sub in plant.subsystems:
        out = sub.total_discharge + sub.evaporation + sub.product
        if sub.total_intake > 0 and out > sub.total_intake * (1 + TOLERANCE) + 1e-9:
            issues.append(Issue("warn", "", "", f"{sub.name}: مدل سالانه — خروجی بیش از برداشت است",
                                f"{sub.name}: annual model — outflow exceeds intake"))
    sa = sum(s.metered_m3 or 0.0 for s in plant.sources)
    sb = sum(o.metered_m3 or 0.0 for o in plant.outlets)
    if sa > 0 and sb > sa * (1 + TOLERANCE):
        issues.append(Issue("warn", "", "", "مدل سالانه — تخلیهٔ کنتورها بیش از برداشت کنتورهاست",
                            "Annual model — metered discharge exceeds metered withdrawal"))
    return issues


def completeness(plant: Plant, slices: Sequence[cal.Slice]):
    """[(spec, [bool per slice])] for every variable that holds data: which periods are filled."""
    out = []
    for sp in TS.catalog(plant):
        pts = plant.series.get(sp.key)
        if pts:
            out.append((sp, [TS.value_in(pts, s.start, s.end, sp.agg)[0] is not None for s in slices]))
    return out
