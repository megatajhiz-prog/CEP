"""Water-saving measures: database access, plant-specific estimates and plan economics.

The database (``measures_data``) holds 80 measures in 9 groups with screening ranges taken
from the supplied study. Ranges are engineering screening values, not guarantees; savings of
several measures on the same water are combined multiplicatively, never added.

Economics (study section 4-2), with ``Qs`` the annual saving divided by 365 (m3/day):

    I1  = CAPEX / Qs                                  [currency per (m3/day)]
    I2  = CAPEX / (Qs * 365 * N)                      [currency per m3 over the project life]
    LCC = (CRF * CAPEX + OPEX) / (Qs * 365)           [currency per m3, annualised]
    CRF = i (1+i)^N / ((1+i)^N - 1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import measures_data as data
from .model import PlanItem, Plant, Subsystem

CAPEX_LABEL = {
    1: {"fa": "کم", "en": "Low"}, 2: {"fa": "متوسط", "en": "Medium"},
    3: {"fa": "زیاد", "en": "High"}, 4: {"fa": "بسیار زیاد", "en": "Very high"},
}

CAUTION = {
    "reuse": {"fa": "آب بازیافتی باید مصرف‌کنندهٔ مشخص با کیفیت متناسب داشته باشد؛ ظرفیت تصفیه به‌تنهایی صرفه‌جویی نیست.",
              "en": "Reclaimed water needs a defined consumer of matching quality; treatment capacity alone is not a saving."},
    "alt_source": {"fa": "منبع جایگزین برداشت از منبع اصلی را کم می‌کند، نه لزوماً مصرف واقعی را.",
                   "en": "An alternative source cuts withdrawal from the main source, not necessarily real consumption."},
    "energy": {"fa": "ممکن است مصرف انرژی و هزینهٔ بهره‌برداری را افزایش دهد؛ در ارزیابی اقتصادی بیاورید.",
               "en": "May raise energy use and operating cost; include them in the economics."},
    "hygiene": {"fa": "بازاستفاده باید با الزامات بهداشتی و اعتبارسنجی فرایند سازگار باشد.",
                "en": "Reuse must comply with hygiene requirements and process validation."},
    "quality": {"fa": "کیفیت آب باید متناسب با کاربرد باشد.", "en": "Water quality must fit the application."},
    "incremental": {"fa": "اثر افزایشی است؛ نباید جدا از تجهیزات تحت کنترل جمع شود (دوباره‌شماری).",
                    "en": "Incremental effect; do not add it separately to the equipment it controls (double counting)."},
    "indirect": {"fa": "راهکار غیرمستقیم است و خودش عدد صرفه‌جویی ندارد.", "en": "Indirect measure; it has no saving figure of its own."},
    "depends": {"fa": "اثر وابسته به شرایط پروژه است و عدد ثابتی ندارد.", "en": "The effect depends on project conditions; no fixed figure."},
    "conditional": {"fa": "فقط در صورت وجود جریان‌های مناسب قابل اجراست.", "en": "Applicable only where suitable streams exist."},
}


@dataclass(frozen=True)
class Measure:
    id: int
    group: int
    fa: str
    en: str
    use: Optional[Tuple[float, float]]
    fresh: Optional[Tuple[float, float]]
    qual: str
    use_text: str
    fresh_text: str
    capex: Tuple[int, int]
    targets: Tuple[str, ...]
    water: str
    reuse: bool
    alt_source: bool
    energy: bool
    hygiene: bool
    quality: bool
    driver_fa: str
    driver_en: str
    note_fa: str
    note_en: str

    def name(self, lang: str) -> str:
        return self.fa if lang == "fa" else self.en

    def note(self, lang: str) -> str:
        return (self.note_fa if lang == "fa" else self.note_en) or ""

    def driver(self, lang: str) -> str:
        return (self.driver_fa if lang == "fa" else self.driver_en) or ""

    @property
    def estimable(self) -> bool:
        return self.use is not None

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.use[0] + self.use[1]) if self.use else 0.0

    def cautions(self, lang: str) -> List[str]:
        keys = [k for k in ("reuse", "alt_source", "energy", "hygiene", "quality") if getattr(self, k)]
        if self.qual:
            keys.append(self.qual)
        return [CAUTION[k]["fa" if lang == "fa" else "en"] for k in keys]


def _tuple(v):
    return None if v is None else (float(v[0]), float(v[1]))


_MEASURES: List[Measure] = [
    Measure(id=r["id"], group=r["group"], fa=r["fa"], en=r["en"], use=_tuple(r["use"]), fresh=_tuple(r["fresh"]),
            qual=r["qual"], use_text=r["use_text"], fresh_text=r["fresh_text"], capex=tuple(r["capex"]),
            targets=tuple(r["targets"]), water=r["water"], reuse=r["reuse"], alt_source=r["alt_source"],
            energy=r["energy"], hygiene=r["hygiene"], quality=r["quality"], driver_fa=r["driver_fa"],
            driver_en=r["driver_en"], note_fa=r["note_fa"], note_en=r["note_en"])
    for r in data.MEASURES
]
_BY_ID = {m.id: m for m in _MEASURES}

# measures that have an exact calculator on the Savings page
EXACT_CALCULATOR = {11: "cooling_tower", 23: "boiler", 25: "boiler", 26: "boiler", 5: "leak"}


def all_measures() -> List[Measure]:
    return list(_MEASURES)


def get(measure_id: int) -> Measure:
    return _BY_ID[measure_id]


def group_name(group: int, lang: str) -> str:
    return data.GROUPS["fa" if lang == "fa" else "en"][group - 1]


def group_priority(group: int, lang: str) -> str:
    return data.GROUPS["prio_fa" if lang == "fa" else "prio_en"][group - 1]


def capex_text(m: Measure, lang: str) -> str:
    lo, hi = m.capex
    a, b = CAPEX_LABEL[lo][lang], CAPEX_LABEL[hi][lang]
    if lo == hi:
        return a
    return f"{a} {'تا' if lang == 'fa' else 'to'} {b}"


def range_text(r: Optional[Tuple[float, float]], m: Measure, lang: str, fresh: bool = False) -> str:
    if r is None:
        txt = m.fresh_text if fresh else m.use_text
        if lang == "fa":
            return txt
        return {"indirect": "indirect", "depends": "depends on project"}.get(m.qual, "—")
    s = f"{r[0]:g}–{r[1]:g}%"
    if m.qual == "incremental":
        s += " " + ("افزایشی" if lang == "fa" else "(incremental)")
    return s


def search(text: str = "", group: Optional[int] = None, kind: Optional[str] = None,
           max_capex: Optional[int] = None, lang: str = "fa") -> List[Measure]:
    """Filter the database. ``kind``: subsystem kind or "plant"; ``max_capex``: 1..4 (lowest level of the measure)."""
    text = (text or "").strip().lower()
    out = []
    for m in _MEASURES:
        if group is not None and m.group != group:
            continue
        if kind is not None and kind not in m.targets:
            continue
        if max_capex is not None and m.capex[0] > max_capex:
            continue
        if text:
            hay = f"{m.id} {m.fa} {m.en} {m.note_fa} {m.note_en}".lower()
            if text not in hay:
                continue
        out.append(m)
    return out


# ------------------------------------------------------------------ plant-specific estimates
def _subs_for(plant: Plant, m: Measure) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    seen = set()
    for t in m.targets:
        if t == "plant":
            if "" not in seen:
                out.append(("", sum(s.total_intake for s in plant.subsystems)))
                seen.add("")
        else:
            for s in plant.subsystems:
                if s.kind == t and s.name not in seen:
                    out.append((s.name, s.total_intake))
                    seen.add(s.name)
    return out


def baseline_volume(plant: Plant, target: str) -> float:
    if not target:
        return sum(s.total_intake for s in plant.subsystems)
    for s in plant.subsystems:
        if s.name == target:
            return s.total_intake
    return 0.0


def value_per_m3(plant: Plant, target: str = "") -> float:
    """Currency per m3 of intake saved: source price plus water treatment (discharge price excluded)."""
    smap = {x.name: x for x in plant.sources}
    tmap = {x.name: x for x in plant.treatments}

    def one(s: Subsystem) -> float:
        vi = s.total_intake
        if vi <= 0:
            return 0.0
        water = sum(smap[k].unit_cost * v for k, v in s.intake.items() if k in smap) / vi
        treat = sum(tmap[k].unit_cost * f for k, f in s.water_treatments.items() if k in tmap)
        return water + treat

    if target:
        for s in plant.subsystems:
            if s.name == target:
                return one(s)
        return 0.0
    tot = sum(s.total_intake for s in plant.subsystems)
    return sum(one(s) * s.total_intake for s in plant.subsystems) / tot if tot > 0 else 0.0


@dataclass
class Estimate:
    measure: Measure
    target: str                 # subsystem name, "" = plant-wide
    baseline: float             # m3/year
    low: float
    high: float
    value_low: float = 0.0      # currency per year
    value_high: float = 0.0

    @property
    def mid(self) -> float:
        return 0.5 * (self.low + self.high)


def estimates(plant: Plant, m: Measure) -> List[Estimate]:
    """Screening estimate of one measure for each applicable part of the plant (empty if no numeric range)."""
    if not m.estimable:
        return []
    out = []
    for target, base in _subs_for(plant, m):
        if base <= 0:
            continue
        v = value_per_m3(plant, target)
        lo, hi = base * m.use[0] / 100.0, base * m.use[1] / 100.0
        out.append(Estimate(m, target, base, lo, hi, lo * v, hi * v))
    return out


def recommend(plant: Plant, include_plant_wide: bool = True, limit: Optional[int] = None) -> List[Estimate]:
    """Estimates for all measures, largest mid-point saving first. Indirect/undefined ones are left out."""
    rows: List[Estimate] = []
    for m in _MEASURES:
        for e in estimates(plant, m):
            if e.target == "" and not include_plant_wide:
                continue
            rows.append(e)
    rows.sort(key=lambda e: e.mid, reverse=True)
    return rows[:limit] if limit else rows


def new_plan_item(plant: Plant, m: Measure, target: Optional[str] = None) -> PlanItem:
    if target is None:
        es = estimates(plant, m)
        target = es[0].target if es else ""
    return PlanItem(measure_id=m.id, target=target, saving_pct=round(m.midpoint, 3))


# ------------------------------------------------------------------ economics
def crf(rate_pct: float, years: float) -> float:
    """Capital recovery factor; a zero rate gives 1/N."""
    if years <= 0:
        raise ValueError("project life must be > 0")
    i = rate_pct / 100.0
    if abs(i) < 1e-12:
        return 1.0 / years
    g = (1.0 + i) ** years
    return i * g / (g - 1.0)


def invest_per_daily_capacity(capex: float, saving_m3_year: float) -> Optional[float]:
    """I1 = CAPEX / Qs, Qs in m3/day."""
    return capex / (saving_m3_year / 365.0) if saving_m3_year > 0 else None


def invest_per_cumulative_m3(capex: float, saving_m3_year: float, years: float) -> Optional[float]:
    """I2 = CAPEX / (Qs * 365 * N)."""
    return capex / (saving_m3_year * years) if saving_m3_year > 0 and years > 0 else None


def levelized_cost(capex: float, opex: float, saving_m3_year: float, rate_pct: float, years: float) -> Optional[float]:
    """LCC = (CRF * CAPEX + OPEX) / (Qs * 365)."""
    if saving_m3_year <= 0 or years <= 0:
        return None
    return (crf(rate_pct, years) * capex + opex) / saving_m3_year


def payback_years(capex: float, annual_value: float, opex: float) -> Optional[float]:
    net = annual_value - opex
    return capex / net if net > 0 and capex >= 0 else None


# ------------------------------------------------------------------ plan evaluation
@dataclass
class PlanLine:
    item: PlanItem
    measure: Measure
    baseline: float
    standalone: float           # saving if applied alone, m3/year
    saving: float               # share of the combined saving of its target, m3/year
    annual_value: float
    i1: Optional[float]
    i2: Optional[float]
    lcc: Optional[float]
    payback: Optional[float]
    flags: List[str] = field(default_factory=list)


@dataclass
class PlanResult:
    lines: List[PlanLine]
    intake: float
    saving: float               # combined, m3/year
    saving_pct: float
    annual_value: float
    capex: float
    opex: float
    payback: Optional[float]
    lcc: Optional[float]
    warnings: List[str]         # codes: overlap:<target>, missing:<id>, range:<id>, no_number:<id>, plant_wide_over


def evaluate_plan(plant: Plant) -> PlanResult:
    """Combine the plan's measures without double counting.

    Measures on the same target combine as 1 - prod(1 - p_i); the combined saving of a target is shared
    among its measures in proportion to their stand-alone savings. Plant-wide measures then act on the
    intake that remains after all subsystem-level savings.
    """
    items = [i for i in plant.plan if i.measure_id in _BY_ID]
    total_in = sum(s.total_intake for s in plant.subsystems)
    warnings: List[str] = []
    groups: Dict[str, List[PlanItem]] = {}
    for it in items:
        groups.setdefault(it.target, []).append(it)

    combined: Dict[str, float] = {}
    sub_saved = 0.0
    for tgt, its in groups.items():
        if not tgt:
            continue
        base = baseline_volume(plant, tgt)
        keep = 1.0
        for it in its:
            keep *= 1.0 - min(max(it.saving_pct, 0.0), 100.0) / 100.0
        combined[tgt] = base * (1.0 - keep)
        sub_saved += combined[tgt]
        if len(its) > 1:
            warnings.append("overlap:" + tgt)
    if "" in groups:
        base = max(total_in - sub_saved, 0.0)
        keep = 1.0
        for it in groups[""]:
            keep *= 1.0 - min(max(it.saving_pct, 0.0), 100.0) / 100.0
        combined[""] = base * (1.0 - keep)
        if len(groups[""]) > 1:
            warnings.append("overlap:")

    lines: List[PlanLine] = []
    for it in items:
        m = _BY_ID[it.measure_id]
        base = baseline_volume(plant, it.target) if it.target else total_in
        stand = base * min(max(it.saving_pct, 0.0), 100.0) / 100.0
        stand_sum = sum((baseline_volume(plant, x.target) if x.target else total_in) *
                        min(max(x.saving_pct, 0.0), 100.0) / 100.0 for x in groups[it.target])
        share = combined.get(it.target, 0.0) * (stand / stand_sum) if stand_sum > 0 else 0.0
        val = share * value_per_m3(plant, it.target)
        flags: List[str] = []
        if it.target and base <= 0:
            flags.append("missing")
        if m.use is not None and not (m.use[0] - 1e-9 <= it.saving_pct <= m.use[1] + 1e-9):
            flags.append("range")
        if m.use is None:
            flags.append("no_number")
        lines.append(PlanLine(
            it, m, base, stand, share, val,
            invest_per_daily_capacity(it.capex, share),
            invest_per_cumulative_m3(it.capex, share, it.life_years),
            levelized_cost(it.capex, it.opex, share, it.rate_pct, it.life_years),
            payback_years(it.capex, val, it.opex), flags))
    saving = sum(combined.values())
    value = sum(l.annual_value for l in lines)
    capex = sum(i.capex for i in items)
    opex = sum(i.opex for i in items)
    life = (sum(i.life_years * i.capex for i in items) / capex) if capex > 0 else (items[0].life_years if items else 0)
    rate = (sum(i.rate_pct * i.capex for i in items) / capex) if capex > 0 else (items[0].rate_pct if items else 0)
    lcc = levelized_cost(capex, opex, saving, rate, life) if items and life > 0 else None
    return PlanResult(lines, total_in, saving, 100.0 * saving / total_in if total_in > 0 else 0.0, value,
                      capex, opex, payback_years(capex, value, opex), lcc, warnings)
