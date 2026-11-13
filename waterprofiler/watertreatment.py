"""Supply-side water treatment: pre-treatment, demineralised-water production and similar units.

Convention (like the wastewater plants, see wastewater.py): a treatment unit is a subsystem of kind ``"wtp"``. Raw water enters
it as ordinary intake from a source, or as a transfer from another treatment unit; treated water leaves it by transfers to
the next stage or to the consumers (boiler make-up, process, cooling tower ...). What it rejects leaves as its discharge
(back-wash, reject / concentrate, regeneration waste), its ``product`` (water in sludge) and its ``evaporation`` (losses).

Per unit:  closure = inflow - to consumers - to next stage - waste - sludge - losses - dS  (should be ~ 0),
yield = (to consumers + to next stage) / inflow, waste share = (waste + sludge + losses) / inflow.

Cost of the treated water per m3 follows the chain: the cost entering a unit (raw water at the source price, or the treated
water of the unit before it at *its* cost) plus running cost, electricity, capital annuity and the discharge fee of the waste,
divided by the water that leaves it as product. Optional data are in ``Subsystem.params`` (``PARAM_KEYS``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .model import Plant, Subsystem

PARAM_KEYS = ("tds_in", "tds_out", "capacity", "opex_m3", "kwh_m3", "capex", "life", "min_yield")

# indicative maximum salinity (TDS, mg/L) of the treated water by the kind of consumer; None = no guideline
TDS_NEED: Dict[str, Optional[float]] = {"boiler": 20.0}       # low-pressure boiler make-up: conductivity of the order of 20 uS/cm


@dataclass
class UnitRow:
    name: str
    inflow: float
    raw_in: float              # intake from sources
    from_other: float          # received from other subsystems / units
    to_users: float
    to_next: float
    waste: float               # discharge (back-wash, reject, regeneration)
    sludge: float
    losses: float
    storage_change: float
    closure: float
    closure_pct: float
    yield_: Optional[float]
    waste_share: Optional[float]
    utilisation: Optional[float]
    tds_in: Optional[float]
    tds_out: Optional[float]
    tds_removal: Optional[float]
    cost_per_m3: Optional[float]       # cost of one m3 of treated water leaving the unit (whole chain)
    treatment_cost: float              # own running cost + electricity + capital annuity, currency/year
    waste_fee: float                   # discharge fee of the waste, currency/year
    energy_kwh: float


@dataclass
class ConsumerRow:
    name: str
    kind: str
    volume: float
    tds: Optional[float]
    need: Optional[float]
    suitable: Optional[bool]
    cost_per_m3: Optional[float]
    fresh_price: float


@dataclass
class WaterTreatmentReport:
    units: List[UnitRow]
    consumers: List[ConsumerRow]
    raw_in: float
    delivered: float                   # treated water delivered to consumers
    waste: float                       # water rejected by all units (waste + sludge + losses)
    waste_share_of_intake: Optional[float]    # waste / plant intake
    overall_yield: Optional[float]     # delivered / raw water entering the treatment chain
    total_cost: float                  # treatment cost of all units, currency/year
    warnings: List[str] = field(default_factory=list)

    @property
    def has_system(self) -> bool:
        return bool(self.units)


def is_unit(s: Subsystem) -> bool:
    return s.kind == "wtp"


def _opt(p: Dict[str, float], k: str) -> Optional[float]:
    v = p.get(k)
    return v if v not in (None, 0, 0.0) else None


def _is_wt(plant: Plant, name: str) -> bool:
    n = plant.node(name)
    if n is None:
        return False
    if n.kind == "wtp":
        return True
    par = plant.node(n.parent) if n.parent else None
    return par is not None and par.kind == "wtp"


def analyse_water_treatment(plant: Plant) -> WaterTreatmentReport:
    plant.rollup()
    warn: List[str] = []
    units = [u for u in plant.units() if is_unit(u)]
    price_src = {x.name: x.unit_cost for x in plant.sources}
    price_out = {x.name: x.unit_cost for x in plant.outlets}
    el = plant.costs.electricity_per_kwh
    owner: Dict[str, str] = {}
    for u in units:
        for c in plant.children(u.name):
            owner[c.name] = u.name
        owner[u.name] = u.name
    members = {u.name: {c.name for c in plant.children(u.name)} | {u.name} for u in units}

    base: Dict[str, dict] = {}
    for u in units:
        p = u.params or {}
        m = members[u.name]
        users = nxt = from_wt = from_gen = 0.0
        for x in plant.links:
            s_in, d_in = x.src in m, x.dst in m
            if s_in and not d_in:
                if _is_wt(plant, x.dst):
                    nxt += x.volume
                else:
                    users += x.volume
            if d_in and not s_in:
                if _is_wt(plant, x.src):
                    from_wt += x.volume
                else:
                    from_gen += x.volume
        raw = u.total_intake
        inflow = raw + from_wt + from_gen
        waste, sludge, loss, ds = u.total_discharge, u.product, u.evaporation, u.storage_change
        closure = inflow - users - nxt - waste - sludge - loss - ds
        out = users + nxt
        base[u.name] = dict(u=u, p=p, users=users, nxt=nxt, raw=raw, from_other=from_wt + from_gen, inflow=inflow,
                            waste=waste, sludge=sludge, loss=loss, ds=ds, closure=closure, out=out)

    # ---- cost chain: iterate until the cost of a unit's product no longer changes (the chain has no loop)
    cost_in: Dict[str, float] = {}
    prod_cost: Dict[str, Optional[float]] = {u.name: None for u in units}
    energy: Dict[str, float] = {}
    own: Dict[str, float] = {}
    fee: Dict[str, float] = {}
    for _ in range(len(units) + 2):
        for u in units:
            b = base[u.name]
            p = b["p"]
            raw_cost = sum(v * price_src.get(k, 0.0) for k, v in u.intake.items())
            up = 0.0
            for x in plant.links:
                if x.dst in members[u.name] and x.src not in members[u.name]:
                    so = owner.get(x.src)
                    up += x.volume * (prod_cost.get(so) or 0.0) if so else 0.0     # treated water of an earlier unit
            kwh = (p.get("kwh_m3") or 0.0) * b["inflow"]
            capex, life = p.get("capex") or 0.0, p.get("life") or 15.0
            own[u.name] = (p.get("opex_m3") or 0.0) * b["inflow"] + kwh * el + capex / life
            energy[u.name] = kwh
            fee[u.name] = sum(v * price_out.get(k, 0.0) for k, v in u.discharge.items())
            tot = raw_cost + up + own[u.name] + fee[u.name]
            prod_cost[u.name] = tot / b["out"] if b["out"] > 0 else None

    rows: List[UnitRow] = []
    for u in units:
        b = base[u.name]
        p = b["p"]
        inflow = b["inflow"]
        cap = _opt(p, "capacity")
        tin, tout = _opt(p, "tds_in"), _opt(p, "tds_out")
        y = b["out"] / inflow if inflow > 0 else None
        ws = (b["waste"] + b["sludge"] + b["loss"]) / inflow if inflow > 0 else None
        rows.append(UnitRow(
            u.name, inflow, b["raw"], b["from_other"], b["users"], b["nxt"], b["waste"], b["sludge"], b["loss"], b["ds"],
            b["closure"], 100.0 * b["closure"] / inflow if inflow > 0 else 0.0, y, ws,
            inflow / cap if cap and inflow > 0 else None, tin, tout,
            1 - tout / tin if tin and tout is not None else None, prod_cost[u.name], own[u.name], fee[u.name], energy[u.name]))
        if inflow > 0 and abs(rows[-1].closure_pct) > 5.0:
            warn.append(f"wt_closure:{u.name}:{rows[-1].closure_pct:.1f}")
        if cap and inflow > cap * 1.0001:
            warn.append(f"wt_overload:{u.name}:{100 * inflow / cap:.0f}")
        elif cap and 0 < inflow < 0.4 * cap:
            warn.append(f"wt_underused:{u.name}:{100 * inflow / cap:.0f}")
        my = _opt(p, "min_yield")
        if my and y is not None and y < my / 100.0:
            warn.append(f"wt_lowyield:{u.name}:{100 * y:.0f}:{my:.0f}")
        if inflow > 0 and tout is None:
            warn.append(f"wt_noquality:{u.name}")
        if inflow > 0 and b["out"] >= inflow * 0.9999 and (b["waste"] + b["sludge"] + b["loss"]) <= 0:
            warn.append(f"wt_nowaste:{u.name}")

    # ---- consumers
    cons: List[ConsumerRow] = []
    fresh = sum(price_src.get(k, 0.0) * v for s in plant.leaves() for k, v in s.intake.items())
    fv = sum(v for s in plant.leaves() for v in s.intake.values())
    fresh_price = fresh / fv if fv > 0 else 0.0
    for s in plant.leaves():
        if s.name in owner:
            continue
        feeds = [(x.volume, owner[x.src]) for x in plant.links if x.dst == s.name and x.src in owner and x.volume > 0]
        vol = sum(v for v, _ in feeds)
        if vol <= 0:
            continue
        tv = sum(v for v, o in feeds if _opt(base[o]["p"], "tds_out") is not None)
        tds = sum(v * _opt(base[o]["p"], "tds_out") for v, o in feeds if _opt(base[o]["p"], "tds_out") is not None) / tv if tv > 0 else None
        cc = [(v, prod_cost[o]) for v, o in feeds if prod_cost[o] is not None]
        cpm = sum(v * c for v, c in cc) / sum(v for v, _ in cc) if cc else None
        need = TDS_NEED.get(s.kind)
        suitable = None if need is None or tds is None else tds <= need
        cons.append(ConsumerRow(s.name, s.kind, vol, tds, need, suitable, cpm, fresh_price))
        if suitable is False:
            warn.append(f"wt_unsuitable:{s.name}:{tds:.0f}:{need:.0f}")

    total_in = sum(s.total_intake for s in plant.leaves())
    raw_chain = sum(r.raw_in for r in rows)
    delivered = sum(r.to_users for r in rows)
    waste = sum(r.waste + r.sludge + r.losses for r in rows)
    return WaterTreatmentReport(
        rows, sorted(cons, key=lambda c: -c.volume), raw_chain, delivered, waste,
        waste / total_in if total_in > 0 else None, delivered / raw_chain if raw_chain > 0 else None,
        sum(own.values()) + sum(fee.values()), warn)


_MSG = {
    "wt_closure": ("بیلان واحد «{0}» نمی‌بندد: اختلاف {1}٪ از آب ورودی (نشتی، کنتور یا جریان ثبت‌نشده).",
                   "Treatment unit '{0}' does not close: gap {1} % of its inflow (leak, meter error or an unrecorded stream)."),
    "wt_overload": ("واحد «{0}» بیش از ظرفیت بارگذاری شده است ({1}٪ ظرفیت).", "Unit '{0}' is loaded above its capacity ({1} % of capacity)."),
    "wt_underused": ("واحد «{0}» کم‌بار است ({1}٪ ظرفیت).", "Unit '{0}' is under-used ({1} % of capacity)."),
    "wt_lowyield": ("بازده «{0}» ({1}٪) از حداقل تعیین‌شده ({2}٪) کمتر است؛ آب زیادی به‌صورت پساب یا شست‌وشوی معکوس هدر می‌رود.",
                    "Yield of '{0}' ({1} %) is below the set minimum ({2} %); too much water goes to waste or back-wash."),
    "wt_noquality": ("برای «{0}» شوری (TDS) خروجی وارد نشده است؛ مناسب‌بودن برای مصرف‌کننده‌ها ارزیابی نمی‌شود.",
                     "No outlet salinity (TDS) for '{0}': suitability for the consumers cannot be judged."),
    "wt_nowaste": ("«{0}» هیچ پساب، لجن یا تلفاتی ثبت نکرده؛ هر واحد تصفیه مقداری آب دور می‌ریزد (شست‌وشوی معکوس، پساب غلیظ، احیا).",
                   "'{0}' records no waste, sludge or loss; every treatment unit rejects some water (back-wash, reject, regeneration)."),
    "wt_unsuitable": ("آب دریافتی «{0}» (TDS {1} mg/L) از حد توصیه‌شده برای آن مصرف ({2} mg/L) شورتر است.",
                      "The water received by '{0}' (TDS {1} mg/L) is saltier than the guideline for that use ({2} mg/L)."),
}


def message(code: str, lang: str = "fa") -> str:
    key, *args = code.split(":")
    fa, en = _MSG[key]
    return (fa if lang == "fa" else en).format(*args)
