"""Time series of the plant: variables, aggregation over any period, applying a period to the annual model, and
time-based indicators (peaking, trend, base load, intensity, anomalies).

A series is a list of non-overlapping intervals (ISO start/end dates, inclusive) with one value each. Two kinds of
variables exist:

* ``sum``  - an amount per interval (m3, kWh, product units, currency, ...). Spread evenly over the days of the
  interval when a different slicing is asked for.
* ``mean`` - a level (temperature, price, concentration, head count). Averaged by days.

Nothing is ever invented: a slice without data is "no value", and annualising a partly covered period is flagged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from . import jcalendar as cal
from .model import Plant, Point

# ---------------------------------------------------------------------------------------------- variables
SUB_FIELDS = (("intake", "برداشت", "intake"), ("discharge", "تخلیه", "discharge"), ("evaporation", "تبخیر", "evaporation"),
              ("product", "آب در محصول", "water in product"), ("recirc", "بازچرخانی داخلی", "internal recirculation"))

# profile fields fed by a series: key -> (attribute, aggregation)
PROFILE_MAP = {
    "site:revenue": ("revenue", "sum"), "site:value_added": ("value_added", "sum"),
    "site:production_cost": ("production_cost", "sum"), "site:steam_t": ("steam_t", "sum"),
    "site:outage_hours": ("outage_hours", "sum"), "site:employees": ("employees", "mean"),
    "quality:cod_raw": ("cod_raw", "mean"), "quality:cod_out": ("cod_out", "mean"),
    "quality:tds_intake": ("tds_intake", "mean"), "quality:tds_discharge": ("tds_discharge", "mean"),
}

GROUP_TITLE = {
    "production": ("تولید", "Production"), "source": ("برداشت از منابع", "Source intake"),
    "loss": ("تلفات آب", "Water losses"),
    "outlet": ("تخلیه به مقاصد", "Discharge to outlets"), "subsystem": ("جریان زیرسیستم‌ها", "Subsystem flows"),
    "energy": ("انرژی", "Energy"), "price": ("قیمت و تعرفه", "Prices and tariffs"),
    "env": ("اقلیم", "Climate"), "site": ("سایت و اقتصاد", "Site and economics"),
    "quality": ("کیفیت آب و پساب", "Water quality"),
}

# unit code -> (fa, en); "units" and "cur" are filled from the plant
SERIES_UNITS = {
    "m3": ("m³", "m³"), "kwh": ("kWh", "kWh"), "c": ("°C", "°C"), "mm": ("mm", "mm"), "t": ("t", "t"),
    "count": ("نفر", "persons"), "h": ("ساعت", "h"), "mg_l": ("mg/L", "mg/L"), "cur_m3": ("{cur}/m³", "{cur}/m³"),
    "cur_kwh": ("{cur}/kWh", "{cur}/kWh"), "units": ("{u}", "{u}"), "cur": ("{cur}", "{cur}"),
}


@dataclass(frozen=True)
class VarSpec:
    key: str
    group: str
    fa: str
    en: str
    unit: str
    agg: str                       # "sum" | "mean"

    def label(self, lang: str) -> str:
        return self.fa if lang == "fa" else self.en


def unit_text(code: str, lang: str, plant: Plant) -> str:
    fa, en, = SERIES_UNITS[code]
    return (fa if lang == "fa" else en).format(cur=plant.currency, u=plant.production_unit)


def catalog(plant: Plant) -> List[VarSpec]:
    """Every variable that can carry a time series for this plant (built from its sources, outlets, subsystems ...)."""
    v: List[VarSpec] = []       # the total production is not a variable: it is the sum of the products
    for p in plant.site.products:
        v.append(VarSpec(f"production:{p.name}", "production", f"تولید «{p.name}»", f"Production of {p.name}", "units", "sum"))
    for s in plant.subsystems:
        v.append(VarSpec(f"sub:{s.name}:production", "production", f"تولید واحد «{s.name}»", f"Production of unit {s.name}",
                         "units", "sum"))
    for s in plant.sources:
        v.append(VarSpec(f"source:{s.name}", "source", f"برداشت از «{s.name}»", f"Intake from {s.name}", "m3", "sum"))
    for o in plant.outlets:
        v.append(VarSpec(f"outlet:{o.name}", "outlet", f"تخلیه به «{o.name}»", f"Discharge to {o.name}", "m3", "sum"))
    v.append(VarSpec("loss:measured", "loss", "تلفات اندازه‌گیری‌شده (نشت / آب بدون درآمد)",
                     "Measured losses (leaks / non-revenue water)", "m3", "sum"))
    for s in plant.sources:
        v.append(VarSpec(f"price:source:{s.name}", "price", f"قیمت آب «{s.name}»", f"Water price of {s.name}", "cur_m3", "mean"))
    for o in plant.outlets:
        v.append(VarSpec(f"price:outlet:{o.name}", "price", f"تعرفهٔ تخلیه به «{o.name}»", f"Discharge tariff of {o.name}", "cur_m3", "mean"))
    v += [VarSpec("price:electricity", "price", "قیمت برق", "Electricity price", "cur_kwh", "mean"),
          VarSpec("price:fuel", "price", "قیمت انرژی حرارتی", "Thermal energy price", "cur_kwh", "mean")]
    for s in plant.subsystems:
        for f, fa, en in SUB_FIELDS:
            v.append(VarSpec(f"sub:{s.name}:{f}", "subsystem", f"{s.name} — {fa}", f"{s.name} — {en}", "m3", "sum"))
    v += [VarSpec("energy:el", "energy", "برق مصرفی", "Electricity", "kwh", "sum"),
          VarSpec("energy:th", "energy", "انرژی حرارتی (سوخت)", "Thermal energy (fuel)", "kwh", "sum")]
    v += [VarSpec("env:temp", "env", "دمای هوا (میانگین)", "Air temperature (mean)", "c", "mean"),
          VarSpec("env:rain", "env", "بارندگی", "Rainfall", "mm", "sum"),
          VarSpec("site:employees", "site", "تعداد پرسنل", "Employees", "count", "mean"),
          VarSpec("site:steam_t", "site", "بخار تولیدی", "Steam produced", "t", "sum"),
          VarSpec("site:revenue", "site", "درآمد", "Revenue", "cur", "sum"),
          VarSpec("site:value_added", "site", "ارزش افزوده", "Value added", "cur", "sum"),
          VarSpec("site:production_cost", "site", "هزینهٔ تولید", "Production cost", "cur", "sum"),
          VarSpec("site:outage_hours", "site", "ساعات قطعی تأمین آب", "Water supply outage hours", "h", "sum"),
          VarSpec("quality:cod_raw", "quality", "COD پساب خام", "Raw wastewater COD", "mg_l", "mean"),
          VarSpec("quality:cod_out", "quality", "COD پساب تخلیه‌شده", "Discharged COD", "mg_l", "mean"),
          VarSpec("quality:tds_intake", "quality", "TDS آب ورودی", "Intake TDS", "mg_l", "mean"),
          VarSpec("quality:tds_discharge", "quality", "TDS پساب", "Discharge TDS", "mg_l", "mean")]
    return v


def spec_of(plant: Plant, key: str) -> Optional[VarSpec]:
    for s in catalog(plant):
        if s.key == key:
            return s
    return None


# ------------------------------------------------------------------------------------------ interval maths
def _d(s: str) -> date:
    return date.fromisoformat(s)


def _len(p: Point) -> int:
    return (_d(p.end) - _d(p.start)).days + 1


def _overlap(p: Point, s: date, e: date) -> int:
    lo, hi = max(_d(p.start), s), min(_d(p.end), e)
    return max(0, (hi - lo).days + 1)


def value_in(points: Sequence[Point], s: date, e: date, agg: str) -> Tuple[Optional[float], float]:
    """Value observed inside [s, e] and the share of its days that have data (0..1).

    ``sum`` series return the amount that falls inside (an interval's value is spread evenly over its days);
    ``mean`` series return the day-weighted mean."""
    span = (e - s).days + 1
    tot = cov = 0.0
    for p in points:
        o = _overlap(p, s, e)
        if o <= 0:
            continue
        cov += o
        tot += p.value * o / _len(p) if agg == "sum" else p.value * o
    if cov <= 0:
        return None, 0.0
    return (tot if agg == "sum" else tot / cov), min(1.0, cov / span)


def set_value(points: Sequence[Point], s: date, e: date, value: Optional[float], agg: str) -> List[Point]:
    """Replace the data of [s, e] by one value (None clears it). Intervals that stick out are trimmed, and the
    part outside keeps its share of the value, so no data outside [s, e] is lost or changed."""
    out: List[Point] = []
    one = timedelta(days=1)
    for p in points:
        ps, pe = _d(p.start), _d(p.end)
        if pe < s or ps > e:
            out.append(p)
            continue
        n = _len(p)
        if ps < s:
            k = (s - ps).days
            out.append(Point(p.start, (s - one).isoformat(), p.value * k / n if agg == "sum" else p.value))
        if pe > e:
            k = (pe - e).days
            out.append(Point((e + one).isoformat(), p.end, p.value * k / n if agg == "sum" else p.value))
    if value is not None:
        out.append(Point(s.isoformat(), e.isoformat(), float(value)))
    out.sort(key=lambda q: q.start)
    return out


def put(plant: Plant, key: str, s: date, e: date, value: Optional[float]) -> None:
    sp = spec_of(plant, key)
    agg = sp.agg if sp else "sum"
    pts = set_value(plant.series.get(key, []), s, e, value, agg)
    if pts:
        plant.series[key] = pts
    else:
        plant.series.pop(key, None)


def data_span(plant: Plant) -> Optional[Tuple[date, date]]:
    lo = hi = None
    for pts in plant.series.values():
        for p in pts:
            a, b = _d(p.start), _d(p.end)
            lo = a if lo is None or a < lo else lo
            hi = b if hi is None or b > hi else hi
    return (lo, hi) if lo else None


def window_of(plant: Plant) -> Optional[Tuple[date, date]]:
    w = plant.window
    if w.get("start") and w.get("end"):
        try:
            a, b = _d(w["start"]), _d(w["end"])
            if a <= b:
                return a, b
        except ValueError:
            pass
    return data_span(plant)


def slice_values(plant: Plant, key: str, sl: Sequence[cal.Slice], min_cov: float = 0.5) -> List[Optional[float]]:
    """One value per slice; amounts are scaled to the whole slice when coverage is partial (needs >= min_cov)."""
    sp = spec_of(plant, key)
    pts = plant.series.get(key, [])
    if sp is None or not pts:
        return [None] * len(sl)
    out: List[Optional[float]] = []
    for x in sl:
        v, c = value_in(pts, x.start, x.end, sp.agg)
        if v is None or c < min_cov:
            out.append(None)
        else:
            out.append(v / c if sp.agg == "sum" else v)
    return out


def _sum_keys(plant: Plant, keys: Sequence[str], sl: Sequence[cal.Slice]) -> List[Optional[float]]:
    keys = [k for k in keys if plant.series.get(k)]
    if not keys:
        return [None] * len(sl)
    cols = [slice_values(plant, k, sl) for k in keys]
    return [None if any(c[i] is None for c in cols) else sum(c[i] for c in cols) for i in range(len(sl))]


def total_production_slices(plant: Plant, sl: Sequence[cal.Slice]) -> List[Optional[float]]:
    """Total production per slice = sum of the products' series (a slice where a product has no value has no total)."""
    return _sum_keys(plant, [f"production:{p.name}" for p in plant.site.products], sl)


def total_intake_slices(plant: Plant, sl: Sequence[cal.Slice]) -> List[Optional[float]]:
    src = _sum_keys(plant, [f"source:{s.name}" for s in plant.sources], sl)
    if any(v is not None for v in src):
        return src
    return _sum_keys(plant, [f"sub:{s.name}:intake" for s in plant.subsystems], sl)


# ------------------------------------------------------------------- applying a period to the annual model
@dataclass
class Change:
    key: str
    where: str                      # human-readable target, e.g. "source Well · metered"
    old: Optional[float]
    new: Optional[float]            # None: not applied
    coverage: float                 # share of the window's days with data
    note: str = ""                  # "" | "extrapolated" | "low_coverage" | "split"


def annualise(spec_agg: str, observed: float, coverage: float, days: int) -> float:
    """Amount per 365 days from what was observed on ``coverage * days`` days (levels stay as they are)."""
    if spec_agg == "mean":
        return observed
    return observed / (coverage * days) * 365.0


def plan_changes(plant: Plant, start: date, end: date, min_cov: float = 0.5) -> List[Change]:
    """What the annual model would become if the period start..end were taken as its basis."""
    days = (end - start).days + 1
    out: List[Change] = []
    specs = {s.key: s for s in catalog(plant)}

    def get(key: str) -> Optional[Tuple[float, float]]:
        sp = specs.get(key)
        pts = plant.series.get(key)
        if sp is None or not pts:
            return None
        v, c = value_in(pts, start, end, sp.agg)
        if v is None:
            return None
        return annualise(sp.agg, v, c, days), c

    def add(key: str, where: str, old: Optional[float], got: Tuple[float, float], note_ok: str = "") -> None:
        val, c = got
        note = "low_coverage" if c < min_cov else ("extrapolated" if c < 0.999 else note_ok)
        out.append(Change(key, where, old, None if c < min_cov else val, c, note))

    for p in plant.site.products:
        if (g := get(f"production:{p.name}")):
            add(f"production:{p.name}", f"product:{p.name}:per_year", p.per_year, g)
    for s in plant.sources:
        if (g := get(f"source:{s.name}")):
            add(f"source:{s.name}", f"source:{s.name}:metered", s.metered_m3, g)
        if (g := get(f"price:source:{s.name}")):
            add(f"price:source:{s.name}", f"source:{s.name}:unit_cost", s.unit_cost, g)
    for o in plant.outlets:
        if (g := get(f"outlet:{o.name}")):
            add(f"outlet:{o.name}", f"outlet:{o.name}:metered", o.metered_m3, g)
        if (g := get(f"price:outlet:{o.name}")):
            add(f"price:outlet:{o.name}", f"outlet:{o.name}:unit_cost", o.unit_cost, g)
    for sub in plant.subsystems:
        for f, _fa, _en in SUB_FIELDS:
            g = get(f"sub:{sub.name}:{f}")
            if g is None:
                continue
            old = _sub_get(sub, f)
            ch = Change(f"sub:{sub.name}:{f}", f"sub:{sub.name}:{f}", old, g[0], g[1],
                        "low_coverage" if g[1] < min_cov else ("extrapolated" if g[1] < 0.999 else ""))
            if g[1] < min_cov:
                ch.new = None
            elif f in ("intake", "discharge") and not (old and old > 0):
                names = [x.name for x in (plant.sources if f == "intake" else plant.outlets)]
                if len(names) != 1:
                    ch.new, ch.note = None, "split"
            out.append(ch)
    for key, label in (("price:electricity", "costs:electricity_per_kwh"), ("price:fuel", "costs:fuel_per_kwh_thermal")):
        if (g := get(key)):
            old = plant.costs.electricity_per_kwh if key.endswith("electricity") else plant.costs.fuel_per_kwh_thermal
            add(key, label, old, g)
    for key, (attr, _agg) in PROFILE_MAP.items():
        if (g := get(key)):
            add(key, f"profile:{attr}", getattr(plant.profile, attr), g)
    for sub in plant.subsystems:
        if (g := get(f"sub:{sub.name}:production")):
            add(f"sub:{sub.name}:production", "subprod:" + sub.name, plant.profile.sub_production.get(sub.name), g)
    return out


def driven(plant: Plant, min_cov: float = 0.5) -> Dict[str, str]:
    """Model fields that currently take their value from the time series: ``where`` -> series key.

    ``where`` is the target used by ``commit`` ("product:<n>:per_year", "source:<n>:metered", "costs:<attr>", "profile:<attr>",
    "subprod:<name>", "sub:<n>:<flow>" ...). A field is driven when its variable has enough data in the reference window
    (the window of the time-series page, or the whole data span). Such fields are not entered anywhere else.
    """
    w = window_of(plant)
    if not w:
        return {}
    return {c.where: c.key for c in plan_changes(plant, w[0], w[1], min_cov) if c.new is not None}


def sync(plant: Plant, min_cov: float = 0.5) -> int:
    """Write the series-driven values into the model; returns how many fields actually changed (idempotent)."""
    w = window_of(plant)
    if not w:
        return 0
    ch = [c for c in plan_changes(plant, w[0], w[1], min_cov) if c.new is not None]
    moved = sum(1 for c in ch if c.old is None or abs(c.old - c.new) > 1e-9 * max(1.0, abs(c.new)))
    commit(plant, ch)
    return moved


def _sub_get(sub, f: str) -> float:
    return {"intake": sub.total_intake, "discharge": sub.total_discharge, "evaporation": sub.evaporation,
            "product": sub.product, "recirc": sub.recirculated}[f]


def _scale_dict(d: Dict[str, float], new_total: float, fallback: List[str]) -> bool:
    tot = sum(d.values())
    if tot > 0:
        k = new_total / tot
        for n in list(d):
            d[n] *= k
        return True
    if len(fallback) == 1:
        d[fallback[0]] = new_total
        return True
    return False


def commit(plant: Plant, changes: Sequence[Change]) -> int:
    """Write the applicable changes into the model; returns how many were written."""
    n = 0
    for ch in changes:
        if ch.new is None:
            continue
        parts = ch.where.split(":")
        if ch.where.startswith("subprod:"):
            plant.profile.sub_production[ch.where[len("subprod:"):]] = ch.new
        elif ch.where.startswith("product:"):
            name = ch.where[len("product:"):-len(":per_year")]
            for p in plant.site.products:
                if p.name == name:
                    p.per_year = ch.new
        elif parts[0] == "source":
            s = plant.source(parts[1])
            if parts[2] == "metered":
                s.metered_m3 = ch.new
            else:
                s.unit_cost = ch.new
        elif parts[0] == "outlet":
            o = plant.outlet(parts[1])
            if parts[2] == "metered":
                o.metered_m3 = ch.new
            else:
                o.unit_cost = ch.new
        elif parts[0] == "costs":
            setattr(plant.costs, parts[1], ch.new)
        elif parts[0] == "profile":
            setattr(plant.profile, parts[1], ch.new)
        elif parts[0] == "sub":
            sub = next(x for x in plant.subsystems if x.name == parts[1])
            f = parts[2]
            if f == "intake":
                if not _scale_dict(sub.intake, ch.new, [x.name for x in plant.sources]):
                    continue
            elif f == "discharge":
                if not _scale_dict(sub.discharge, ch.new, [x.name for x in plant.outlets]):
                    continue
            elif f == "evaporation":
                sub.evaporation = ch.new
            elif f == "product":
                sub.product = ch.new
            elif f == "recirc":
                sub.recirculated = ch.new
        n += 1
    plant.sync_production()
    return n


# ---------------------------------------------------------------------------------------- time indicators
def _mean(x: Sequence[float]) -> float:
    return sum(x) / len(x)


def _ols(x: Sequence[float], y: Sequence[float]) -> Optional[Tuple[float, float, float, float]]:
    """Intercept, slope, R2, residual standard deviation; None if x has no spread or fewer than 3 points."""
    n = len(x)
    if n < 3:
        return None
    mx, my = _mean(x), _mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx <= 0:
        return None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    a0 = my - b * mx
    sse = sum((c - (a0 + b * a)) ** 2 for a, c in zip(x, y))
    sst = sum((c - my) ** 2 for c in y)
    return a0, b, (1 - sse / sst) if sst > 0 else 1.0, math.sqrt(sse / (n - 2)) if n > 2 else 0.0


def _corr(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < 3:
        return None
    mx, my = _mean(x), _mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((c - my) ** 2 for c in y))
    if sx <= 0 or sy <= 0:
        return None
    return sum((a - mx) * (c - my) for a, c in zip(x, y)) / (sx * sy)


MIN_MONTHS = 6


def monthly_slices(plant: Plant) -> List[cal.Slice]:
    w = window_of(plant)
    if w is None:
        return []
    sl = cal.slices(w[0], w[1], "month", plant.site.calendar if plant.site.calendar in cal.CALENDARS else "jalali", "en")
    return [x for x in sl if not x.partial]       # clipped first / last months would look like a drop in use


def time_indicators(plant: Plant) -> List[Tuple[str, str, Optional[float], str]]:
    """(id, unit, value, reason) for the time-based indicators; reason is "" | "series" (no data) | "data" (too little)."""
    sl = monthly_slices(plant)
    res: List[Tuple[str, str, Optional[float], str]] = []

    def out(i: str, unit: str, v: Optional[float], reason: str = "") -> None:
        res.append((i, unit, v, reason if v is None else ""))

    intake = total_intake_slices(plant, sl)
    have = [i for i, v in enumerate(intake) if v is not None]
    if not have:
        for i, u in (("ts_months", "n"), ("ts_coverage", "pct"), ("ts_intake_mean", "m3_mo"), ("ts_peak_factor", "x"),
                     ("ts_min_ratio", "x"), ("ts_cv", "pct"), ("ts_trend", "pct"), ("ts_yoy", "pct"),
                     ("ts_intensity", "m3_unit"), ("ts_intensity_max", "m3_unit"), ("ts_intensity_min", "m3_unit"),
                     ("ts_base_load", "m3_mo"), ("ts_base_share", "pct"), ("ts_slope", "m3_unit"), ("ts_r2", "x"),
                     ("ts_anomalies", "n"), ("ts_energy_per_m3", "kwh_m3"), ("ts_temp_corr", "x"),
                     ("ts_loss_measured", "pct"), ("ts_loss_balance", "pct"), ("ts_price_mean", "cur_m3"),
                     ("ts_price_change", "pct")):
            out(i, u, None, "series")
        return res
    vals = [intake[i] for i in have]
    n = len(vals)
    mean = _mean(vals)
    out("ts_months", "n", float(n))
    out("ts_coverage", "pct", 100.0 * n / len(sl))
    out("ts_intake_mean", "m3_mo", mean)
    enough = n >= MIN_MONTHS and mean > 0
    out("ts_peak_factor", "x", max(vals) / mean if enough else None, "data")
    out("ts_min_ratio", "x", min(vals) / mean if enough else None, "data")
    out("ts_cv", "pct", 100.0 * math.sqrt(_mean([(v - mean) ** 2 for v in vals])) / mean if enough else None, "data")
    # trend: slope of intake against the month index, in % of the mean per year (needs a full year to avoid seasonality)
    tr = _ols([float(i) for i in have], vals) if n >= 12 and mean > 0 else None
    out("ts_trend", "pct", 100.0 * tr[1] * 12 / mean if tr else None, "data")
    yoy = None
    if len(sl) >= 24:
        last, prev = intake[-12:], intake[-24:-12]
        if all(v is not None for v in last) and all(v is not None for v in prev) and sum(prev) > 0:
            yoy = 100.0 * (sum(last) / sum(prev) - 1.0)
    out("ts_yoy", "pct", yoy, "data")

    prod = total_production_slices(plant, sl)
    pair = [(intake[i], prod[i]) for i in range(len(sl)) if intake[i] is not None and prod[i] is not None and prod[i] > 0]
    if pair:
        ints = [a / b for a, b in pair]
        out("ts_intensity", "m3_unit", sum(a for a, _ in pair) / sum(b for _, b in pair))
        out("ts_intensity_max", "m3_unit", max(ints))
        out("ts_intensity_min", "m3_unit", min(ints))
    else:
        for i in ("ts_intensity", "ts_intensity_max", "ts_intensity_min"):
            out(i, "m3_unit", None, "series")
    fit = _ols([b for _, b in pair], [a for a, _ in pair]) if len(pair) >= MIN_MONTHS else None
    if fit:
        a0, b0, r2, sd = fit
        out("ts_base_load", "m3_mo", a0)
        out("ts_base_share", "pct", 100.0 * a0 / mean if mean > 0 else None, "data")
        out("ts_slope", "m3_unit", b0)
        out("ts_r2", "x", r2)
        res_ = [a - (a0 + b0 * b) for a, b in pair]
        out("ts_anomalies", "n", float(sum(1 for r in res_ if sd > 0 and abs(r) > 2 * sd)))
    else:
        reason = "series" if not pair else "data"
        for i, u in (("ts_base_load", "m3_mo"), ("ts_base_share", "pct"), ("ts_slope", "m3_unit"), ("ts_r2", "x"), ("ts_anomalies", "n")):
            out(i, u, None, reason)

    el = slice_values(plant, "energy:el", sl)
    both = [(el[i], intake[i]) for i in range(len(sl)) if el[i] is not None and intake[i] is not None]
    out("ts_energy_per_m3", "kwh_m3", sum(a for a, _ in both) / sum(b for _, b in both) if both and sum(b for _, b in both) > 0 else None,
        "series")
    tmp = slice_values(plant, "env:temp", sl)
    pr = [(tmp[i], intake[i]) for i in range(len(sl)) if tmp[i] is not None and intake[i] is not None]
    out("ts_temp_corr", "x", _corr([a for a, _ in pr], [b for _, b in pr]) if len(pr) >= MIN_MONTHS else None,
        "series" if not pr else "data")

    # losses: measured series, and the balance residual of the series (E + P from the annual model, per day)
    ls = slice_values(plant, "loss:measured", sl)
    lp = [(ls[i], intake[i]) for i in range(len(sl)) if ls[i] is not None and intake[i] is not None]
    out("ts_loss_measured", "pct", 100.0 * sum(a for a, _ in lp) / sum(b for _, b in lp) if lp and sum(b for _, b in lp) > 0 else None,
        "series")
    od = _sum_keys(plant, [f"outlet:{o.name}" for o in plant.outlets], sl)
    ep_year = sum(x.evaporation + x.product for x in plant.subsystems)
    bal = [(intake[i] - od[i] - ep_year * sl[i].days / 365.0, intake[i]) for i in range(len(sl))
           if intake[i] is not None and od[i] is not None]
    out("ts_loss_balance", "pct", 100.0 * sum(a for a, _ in bal) / sum(b for _, b in bal) if bal and sum(b for _, b in bal) > 0 else None,
        "series")
    # water price: source tariffs weighted by the volume taken from each source
    wp: List[Optional[float]] = []
    for i in range(len(sl)):
        num = den = 0.0
        for src in plant.sources:
            t_ = slice_values(plant, f"price:source:{src.name}", sl)[i] if plant.series.get(f"price:source:{src.name}") else None
            q_ = slice_values(plant, f"source:{src.name}", sl)[i] if plant.series.get(f"source:{src.name}") else None
            if t_ is not None and q_ is not None and q_ > 0:
                num += t_ * q_
                den += q_
        wp.append(num / den if den > 0 else None)
    got = [v for v in wp if v is not None]
    out("ts_price_mean", "cur_m3", sum(got) / len(got) if got else None, "series")
    out("ts_price_change", "pct", 100.0 * (got[-1] / got[0] - 1.0) if len(got) >= 2 and got[0] > 0 else None,
        "series" if not got else "data")
    return res


# ---------------------------------------------------------------------------------------- import / export
CSV_HEADER = ("key", "start", "end", "value")


def to_rows(plant: Plant) -> List[Tuple[str, str, str, float]]:
    return [(k, p.start, p.end, p.value) for k in sorted(plant.series) for p in plant.series[k]]


def from_rows(plant: Plant, rows: Sequence[Sequence[str]]) -> Tuple[int, List[str]]:
    """Merge long-format rows (key, start, end, value) into the plant. Returns (rows read, problems)."""
    ok, bad = 0, []
    for i, r in enumerate(rows, 1):
        try:
            key, a, b, v = str(r[0]).strip(), _d(str(r[1]).strip()), _d(str(r[2]).strip()), float(str(r[3]).replace(",", ""))
            if b < a or spec_of(plant, key) is None:
                raise ValueError
        except (ValueError, IndexError, TypeError):
            bad.append(f"{i}: {list(r)}")
            continue
        put(plant, key, a, b, v)
        ok += 1
    return ok, bad
