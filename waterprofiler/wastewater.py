"""Wastewater collection, treatment and reuse (analysis of the water-reuse system of a plant).

Modelling convention
--------------------
A treatment / recovery plant (effluent plant, membrane unit, softener, recycling station ...) is a subsystem of kind
``"wwtp"``. It is connected to the rest of the plant by the ordinary inter-subsystem transfers (``Plant.links``), so the
mass balance, the flow diagram and the PFD need no special case:

  * wastewater collected    = transfers  generator -> treatment plant              (R'_in of the plant)
  * treated water reused    = transfers  treatment plant -> consuming subsystem    (R'_out of the plant)
  * effluent to environment = its discharge to outlets (W)
  * sludge / concentrate    = its ``product`` (water leaving with the sludge cake or the brine, P)
  * evaporation / loss      = its evaporation (E)

For every treatment unit the closure  inflow - reuse - effluent - sludge - evaporation - dS  must be ~0.

Optional quality and cost data of a treatment unit are kept in ``Subsystem.params`` (``QUALITY_KEYS``). Concentrations are
in mg/L (= g/m3), loads in kg/year, money per m3 or per year in the plant currency.

Everything here is an indicative engineering check, not a design: the reuse limits below are common guideline values and
must be confirmed with the process owner and the applicable standard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .model import Plant, Subsystem

# parameter names kept in Subsystem.params of a "wwtp" node
QUALITY_KEYS = ("cod_in", "cod_out", "tds_in", "tds_out", "cod_limit", "tds_limit",
                "capacity", "opex_m3", "capex", "life", "required")

# guideline maximum quality of reclaimed water by consuming subsystem kind: (TDS mg/L, COD mg/L); None = no limit known
REUSE_LIMITS: Dict[str, Tuple[Optional[float], Optional[float]]] = {
    "cooling_tower": (1000.0, 75.0),     # make-up: fouling / scaling / biological growth
    "boiler": (50.0, 10.0),              # make-up after demineralisation only
    "irrigation": (2000.0, 100.0),
    "sanitary": (2000.0, 60.0),          # toilet flushing, floor washing
    "process": (None, None),             # depends on the process: not assumed suitable
    "other": (None, None),
}

# share of the use of a subsystem kind that can take reclaimed water (toilet flushing is only part of sanitary use)
REUSE_SHARE = {"sanitary": 0.3}

CLASS_OF_KIND = {"wtp": "blowdown", "sanitary": "domestic", "cooling_tower": "blowdown", "boiler": "blowdown",
                 "irrigation": "other", "process": "industrial", "other": "industrial"}


@dataclass
class StreamRow:
    name: str
    kind: str
    cls: str                 # domestic | industrial | blowdown | other
    generated: float         # liquid leaving the subsystem: discharge + transfers out, m3/year
    to_treatment: float      # transferred to a treatment plant
    direct_reuse: float      # transferred to another (non-treatment) subsystem: cascade reuse
    to_outlet: float         # discharged without treatment inside the plant
    collection_rate: Optional[float]   # to_treatment / generated


@dataclass
class TreatmentRow:
    name: str
    inflow: float
    from_generators: float
    reuse_to_users: float    # delivered to non-treatment subsystems
    to_next_stage: float     # delivered to other treatment units
    effluent: float
    sludge: float
    evaporation: float
    storage_change: float
    closure: float           # inflow - outflows (should be ~0)
    closure_pct: float
    recovery: Optional[float]          # (reuse + next stage) / inflow
    utilisation: Optional[float]       # inflow / capacity
    cod_removal: Optional[float]
    tds_removal: Optional[float]
    cod_load_removed: Optional[float]  # kg/year
    cod_load_discharged: Optional[float]
    compliant: Optional[bool]          # effluent quality within the discharge limits (None: not assessed)
    opex: float                        # currency/year (total running cost of the unit)
    required: bool                     # needed anyway for discharge compliance: not charged to reuse
    capex: float
    reclaimed_cost: Optional[float]    # (opex + capex/life) per m3 delivered to users
    benefit: float                     # value of the fresh water and discharge fee avoided, currency/year
    net_benefit: float
    payback_years: Optional[float]
    quality_known: bool


@dataclass
class UserRow:
    name: str
    kind: str
    reclaimed: float         # reclaimed water received from treatment plants
    fresh_demand: float      # conventional fresh intake
    allowed: Optional[bool]  # reclaimed quality within the guideline for this use (None: not assessed)
    potential: float         # additional fresh water that could be replaced
    note: str = ""


@dataclass
class WastewaterReport:
    streams: List[StreamRow]
    treatments: List[TreatmentRow]
    users: List[UserRow]
    generated: float
    collected: float
    collection_rate: Optional[float]
    direct_reuse: float
    direct_discharge: float
    reuse_treated: float          # treated water delivered to consumers
    effluent: float
    sludge: float
    reuse_rate: Optional[float]   # (reuse_treated + direct_reuse) / generated
    fresh_saving_pct: Optional[float]   # reuse_treated / (fresh intake + reuse_treated)
    internal_recirc: float
    fresh_price: float
    discharge_price: float
    benefit: float
    opex: float
    net_benefit: float
    potential_volume: float
    potential_benefit: float
    surplus_effluent: float       # treated effluent discharged and still reusable, m3/year
    warnings: List[str] = field(default_factory=list)

    @property
    def has_system(self) -> bool:
        return bool(self.treatments)


# ------------------------------------------------------------------------------------------------ helpers
def _is_ww(plant: Plant, name: str) -> bool:
    n = plant.node(name)
    if n is None:
        return False
    if n.kind == "wwtp":
        return True
    return bool(n.parent) and (plant.node(n.parent) is not None) and plant.node(n.parent).kind == "wwtp"


def is_treatment(s: Subsystem) -> bool:
    return s.kind == "wwtp"


def _weighted(pairs: List[Tuple[float, float]]) -> float:
    """Volume-weighted mean price; plain mean of the positive prices when no volume is known."""
    tot = sum(w for _, w in pairs)
    if tot > 0:
        return sum(p * w for p, w in pairs) / tot
    ps = [p for p, _ in pairs if p > 0]
    return sum(ps) / len(ps) if ps else 0.0


def prices(plant: Plant, intake_by_source: Optional[Dict[str, float]] = None) -> Tuple[float, float]:
    """(fresh water price, discharge price) in currency/m3: weighted over the conventional sources and the outlets."""
    ib = intake_by_source or {}
    fresh = _weighted([(x.unit_cost, ib.get(x.name, x.metered_m3 or 0.0)) for x in plant.sources if not x.alternative])
    disch = _weighted([(x.unit_cost, x.metered_m3 or 0.0) for x in plant.outlets])
    return fresh, disch


def _unit_flows(plant: Plant, u: Subsystem) -> Tuple[float, float, float]:
    """(water from generators, water to consumers, water to the next treatment unit) of a top-level treatment unit."""
    members = {c.name for c in plant.children(u.name)} | {u.name}
    gen = users = nxt = 0.0
    for x in plant.links:
        s_in, d_in = x.src in members, x.dst in members
        if d_in and not s_in and not _is_ww(plant, x.src):
            gen += x.volume
        if s_in and not d_in:
            if _is_ww(plant, x.dst):
                nxt += x.volume
            else:
                users += x.volume
    return gen, users, nxt


def _opt(p: Dict[str, float], k: str) -> Optional[float]:
    v = p.get(k)
    return v if v not in (None, 0, 0.0) else None


# ------------------------------------------------------------------------------------------------ main
def analyse_wastewater(plant: Plant) -> WastewaterReport:
    plant.rollup()
    warn: List[str] = []
    leaves = plant.leaves()
    fresh_by_src: Dict[str, float] = {}
    for s in leaves:
        for k, v in s.intake.items():
            fresh_by_src[k] = fresh_by_src.get(k, 0.0) + v
    fresh_price, disch_price = prices(plant, fresh_by_src)
    alt = {x.name for x in plant.sources if x.alternative}
    sum_fresh = sum(v for k, v in fresh_by_src.items() if k not in alt)

    # ------------------------------------------------------------- generators
    streams: List[StreamRow] = []
    for s in leaves:
        if _is_ww(plant, s.name):
            continue
        to_tr = sum(x.volume for x in plant.links if x.src == s.name and _is_ww(plant, x.dst))
        cas = sum(x.volume for x in plant.links if x.src == s.name and not _is_ww(plant, x.dst) and x.dst != s.name)
        to_out = s.total_discharge
        gen = to_out + to_tr + cas
        if gen <= 0:
            continue
        streams.append(StreamRow(s.name, s.kind, CLASS_OF_KIND.get(s.kind, "industrial"), gen, to_tr, cas, to_out,
                                 to_tr / gen if gen > 0 else None))
    generated = sum(r.generated for r in streams)
    collected = sum(r.to_treatment for r in streams)
    direct_reuse = sum(r.direct_reuse for r in streams)
    direct_discharge = sum(r.to_outlet for r in streams)

    # ------------------------------------------------------------- treatment units
    units = [u for u in plant.units() if is_treatment(u)]
    rows: List[TreatmentRow] = []
    qual: Dict[str, Tuple[Optional[float], Optional[float], float]] = {}    # unit -> (tds_out, cod_out, volume to users)
    for u in units:
        p = u.params or {}
        gen, users, nxt = _unit_flows(plant, u)
        members = {c.name for c in plant.children(u.name)} | {u.name}
        from_ww = sum(x.volume for x in plant.links if x.dst in members and x.src not in members and _is_ww(plant, x.src))
        inflow = u.total_intake + gen + from_ww
        effluent, sludge, evap, ds = u.total_discharge, u.product, u.evaporation, u.storage_change
        closure = inflow - users - nxt - effluent - sludge - evap - ds
        cl_pct = 100.0 * closure / inflow if inflow > 0 else 0.0
        cap = _opt(p, "capacity")
        cod_in, cod_out, tds_in, tds_out = (_opt(p, k) for k in ("cod_in", "cod_out", "tds_in", "tds_out"))
        cod_lim, tds_lim = _opt(p, "cod_limit"), _opt(p, "tds_limit")
        cod_rem = 1 - cod_out / cod_in if cod_in and cod_out is not None and cod_in > 0 else None
        tds_rem = 1 - tds_out / tds_in if tds_in and tds_out is not None and tds_in > 0 else None
        removed = (cod_in - cod_out) * inflow / 1000.0 if cod_in is not None and cod_out is not None else None
        disc_load = cod_out * effluent / 1000.0 if cod_out is not None else None
        checks = []
        if cod_lim is not None and cod_out is not None:
            checks.append(cod_out <= cod_lim)
        if tds_lim is not None and tds_out is not None:
            checks.append(tds_out <= tds_lim)
        compliant = all(checks) if checks else None
        opex = (p.get("opex_m3") or 0.0) * inflow
        required = bool(p.get("required"))       # needed anyway to meet the discharge standard: its cost is not charged to reuse
        opex_attr = 0.0 if required else opex
        capex, life = p.get("capex") or 0.0, p.get("life") or 15.0
        delivered = users
        rec_cost = ((opex_attr + (0.0 if required else capex / life)) / delivered) if delivered > 0 else None
        benefit = delivered * (fresh_price + disch_price)
        net = benefit - opex_attr
        payback = capex / net if capex > 0 and net > 0 and not required else None
        rows.append(TreatmentRow(
            u.name, inflow, gen, users, nxt, effluent, sludge, evap, ds, closure, cl_pct,
            (users + nxt) / inflow if inflow > 0 else None, inflow / cap if cap and inflow > 0 else None,
            cod_rem, tds_rem, removed, disc_load, compliant, opex, required, capex, rec_cost, benefit, net, payback,
            any(v is not None for v in (cod_out, tds_out))))
        qual[u.name] = (tds_out, cod_out, users)
        if abs(cl_pct) > 5.0 and inflow > 0:
            warn.append(f"ww_closure:{u.name}:{cl_pct:.1f}")
        if cap and inflow > cap * 1.0001:
            warn.append(f"ww_overload:{u.name}:{100 * inflow / cap:.0f}")
        elif cap and inflow > 0 and inflow < 0.4 * cap:
            warn.append(f"ww_underused:{u.name}:{100 * inflow / cap:.0f}")
        if compliant is False:
            warn.append(f"ww_noncompliant:{u.name}")
        if inflow > 0 and not rows[-1].quality_known:
            warn.append(f"ww_noquality:{u.name}")
        if inflow > 0 and sludge <= 0 and (cod_rem or 0.0) > 0.3 and (tds_rem or 0.0) < 0.5:
            warn.append(f"ww_nosludge:{u.name}")

    if generated > 0 and collected / generated < 0.9 and units:
        warn.append(f"ww_collect:{100 * collected / generated:.0f}")
    if units and collected <= 0:
        warn.append("ww_nocollect")
    # high-TDS blowdown going to a treatment plant that has no TDS removal
    for r in rows:
        bl = sum(x.volume for x in plant.links if (x.dst == r.name or plant.root_of(x.dst) == r.name)
                 and plant.node(x.src) is not None and CLASS_OF_KIND.get(plant.node(x.src).kind) == "blowdown")
        if r.inflow > 0 and bl / r.inflow > 0.2 and (r.tds_removal is None or r.tds_removal < 0.2):
            warn.append(f"ww_blowdown:{r.name}:{100 * bl / r.inflow:.0f}")

    # ------------------------------------------------------------- consumers of reclaimed water
    tr_names = {u.name for u in units}
    tr_members = tr_names | {c.name for u in units for c in plant.children(u.name)}
    owner = {m: u.name for u in units for m in ({c.name for c in plant.children(u.name)} | {u.name})}
    by_unit = {r.name: r for r in rows}

    def judge(kind: str, tds: Optional[float], cod: Optional[float]) -> Tuple[Optional[bool], str]:
        lim_tds, lim_cod = REUSE_LIMITS.get(kind, (None, None))
        if lim_tds is None and lim_cod is None:
            return None, "no_limit"
        tests = []
        if lim_tds is not None and tds is not None:
            tests.append(tds <= lim_tds)
        if lim_cod is not None and cod is not None:
            tests.append(cod <= lim_cod)
        return (all(tests), "") if tests else (None, "no_quality")

    # treated effluent that is discharged and could still be reused. The discharge of a desalting unit (>= 50 % salt
    # removal) is its concentrate and is not reusable; the quality parameters describe the treated (product) water.
    surplus_src = [(by_unit[u.name].effluent, qual[u.name][0], qual[u.name][1]) for u in units
                   if by_unit[u.name].effluent > 0 and (by_unit[u.name].tds_removal or 0.0) < 0.5]
    surplus = sum(v for v, _, _ in surplus_src)

    def wq(xs, i):
        pairs = [(x[i], x[0]) for x in xs if x[i] is not None]
        tv = sum(w for _, w in pairs)
        return sum(a * w for a, w in pairs) / tv if tv > 0 else None
    sur_tds, sur_cod = wq(surplus_src, 1), wq(surplus_src, 2)

    cand: List[UserRow] = []
    for s in leaves:
        if s.name in tr_members:
            continue
        feeds = [(x.volume, qual[owner[x.src]][0], qual[owner[x.src]][1]) for x in plant.links
                 if x.dst == s.name and x.src in owner and x.volume > 0]
        got = sum(v for v, _, _ in feeds)
        fresh = sum(v for k, v in s.intake.items() if k not in alt)
        if (got <= 0 and fresh <= 0) or (s.kind == "wtp" and got <= 0):
            continue
        if got > 0:
            allowed, note = judge(s.kind, wq(feeds, 1), wq(feeds, 2))
            if allowed is False:
                warn.append(f"ww_unsuitable:{s.name}")
        else:
            allowed, note = judge(s.kind, sur_tds, sur_cod)
        cand.append(UserRow(s.name, s.kind, got, fresh, allowed, 0.0, note))

    # additional potential: treated effluent now discharged, to consumers whose guideline it meets (largest demand first);
    # a consumer that fails the guideline only for salt could be served after a polishing step
    avail, pot_total = surplus, 0.0
    for r in sorted(cand, key=lambda r: -r.fresh_demand):
        if r.fresh_demand <= 0:
            continue
        ok, _ = judge(r.kind, sur_tds, sur_cod)
        if ok:
            take = min(avail, r.fresh_demand * REUSE_SHARE.get(r.kind, 1.0))
            r.potential, avail, pot_total = take, avail - take, pot_total + take
        elif ok is False and surplus > 0:
            r.note = "polish"
    users = sorted(cand, key=lambda r: (-r.reclaimed, -r.potential, r.name))

    benefit = sum(r.benefit for r in rows)
    opex = sum(r.opex for r in rows)
    reuse_t = sum(r.reuse_to_users for r in rows)
    internal = sum(s.recirculated for s in leaves)
    return WastewaterReport(
        streams=streams, treatments=rows, users=users, generated=generated, collected=collected,
        collection_rate=collected / generated if generated > 0 else None, direct_reuse=direct_reuse,
        direct_discharge=direct_discharge, reuse_treated=reuse_t, effluent=sum(r.effluent for r in rows),
        sludge=sum(r.sludge for r in rows),
        reuse_rate=(reuse_t + direct_reuse) / generated if generated > 0 else None,
        fresh_saving_pct=reuse_t / (sum_fresh + reuse_t) if (sum_fresh + reuse_t) > 0 else None,
        internal_recirc=internal, fresh_price=fresh_price, discharge_price=disch_price, benefit=benefit, opex=sum(r.opex for r in rows if not r.required),
        net_benefit=sum(r.net_benefit for r in rows), potential_volume=pot_total, potential_benefit=pot_total * (fresh_price + disch_price),
        surplus_effluent=surplus, warnings=warn)


# ------------------------------------------------------------------------------------------------ messages
_MSG = {
    "ww_closure": ("بیلان واحد «{0}» نمی‌بندد: اختلاف {1}٪ از آب ورودی (نشتی، کنتور یا جریان ثبت‌نشده).",
                   "Treatment unit '{0}' does not close: gap {1} % of its inflow (leak, meter error or an unrecorded stream)."),
    "ww_overload": ("واحد «{0}» بیش از ظرفیت بارگذاری شده است ({1}٪ ظرفیت).",
                    "Unit '{0}' is loaded above its capacity ({1} % of capacity)."),
    "ww_underused": ("واحد «{0}» کم‌بار است ({1}٪ ظرفیت)؛ هزینهٔ ثابت هر مترمکعب بالا می‌رود.",
                     "Unit '{0}' is under-used ({1} % of capacity); the fixed cost per m3 rises."),
    "ww_noncompliant": ("کیفیت پساب خروجی «{0}» از حد مجاز تخلیه بیشتر است.",
                        "Effluent quality of '{0}' exceeds the discharge limit."),
    "ww_noquality": ("برای «{0}» کیفیت (COD/TDS) وارد نشده است؛ ارزیابی مجاز بودن بازچرخانی ممکن نیست.",
                     "No quality data (COD/TDS) for '{0}': the suitability of reuse cannot be judged."),
    "ww_nosludge": ("«{0}» لجن یا پساب غلیظ ثبت نکرده است؛ هر تصفیه‌ای مقداری لجن دارد.",
                    "'{0}' records no sludge or concentrate; every treatment produces some."),
    "ww_collect": ("فقط {0}٪ پساب تولیدی به تصفیه می‌رسد؛ بقیه بدون تصفیه تخلیه می‌شود.",
                   "Only {0} % of the generated wastewater reaches treatment; the rest is discharged untreated."),
    "ww_nocollect": ("هیچ پسابی به واحد تصفیه منتقل نشده است؛ در صفحهٔ «جریان آب» انتقال تولیدکننده ← تصفیه را ثبت کنید.",
                     "No wastewater is sent to treatment; add the generator -> treatment transfers on the flow page."),
    "ww_blowdown": ("{1}٪ ورودی «{0}» پساب پرنمک (بلودان) است و حذف نمک ندارد؛ جداسازی یا غشا لازم است.",
                    "{1} % of the inflow of '{0}' is salty blowdown and the unit removes no salt; segregate it or add membranes."),
    "ww_unsuitable": ("آب بازیافتی دریافتی «{0}» از حد توصیه‌شدهٔ کیفیت آن مصرف بیشتر است.",
                      "The reclaimed water received by '{0}' is worse than the guideline for that use."),
}


def message(code: str, lang: str = "fa") -> str:
    key, *args = code.split(":")
    fa, en = _MSG[key]
    return (fa if lang == "fa" else en).format(*args)
