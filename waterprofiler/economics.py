"""Economic evaluation of a water-saving measure (project finance on the saved water).

Cash-flow conventions (end-of-year, constant currency unless the user enters escalation):

    t = 0            :  -CAPEX
    t = 1 .. N       :  benefit_t - cost_t
        volume_t     =  Qs (1 - d)^(t-1)                       saved water, m3 (d = yearly performance loss)
        benefit_t    =  (volume_t * price + other) (1 + g)^(t-1)   (g = price escalation)
        cost_t       =  OPEX (1 + e)^(t-1) + [t = T_r] REPL   (e = cost escalation; REPL a one-off replacement)
        t = N        :  + SALVAGE   (added to the benefit)

Indicators (r = discount rate):

    NPV      = sum_t CF_t / (1+r)^t
    IRR      : the rate that makes NPV = 0 (None when the cash flows never change sign)
    SPB      = simple payback: first time the cumulative net cash flow turns >= 0 (linear inside the year)
    DPB      = discounted payback: the same on discounted cash flows
    BCR      = PV(benefits + salvage) / PV(CAPEX + OPEX + REPL)
    PI       = NPV / CAPEX
    LCOW     = PV(CAPEX + OPEX + REPL - SALVAGE) / PV(saved volume)     cost of one saved m3 (levelised)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .model import PlanItem, Plant


class EconError(ValueError):
    pass


@dataclass
class EconInputs:
    saving_m3: float                  # first-year saved water, m3
    price: float                      # value of one saved m3 (water + treatment + wastewater), currency/m3
    capex: float
    opex: float = 0.0                 # per year, first-year money
    life: int = 15
    rate_pct: float = 10.0
    price_esc_pct: float = 0.0        # yearly rise of the water value and of other benefits
    opex_esc_pct: float = 0.0         # yearly rise of operating cost
    degradation_pct: float = 0.0      # yearly loss of the saving
    other_benefit: float = 0.0        # per year (energy, chemicals, ...), first-year money
    salvage: float = 0.0              # received at the end of the life
    repl_year: int = 0                # 0 = none
    repl_cost: float = 0.0

    def validate(self) -> None:
        if self.life < 1 or self.life > 100:
            raise EconError("life")
        if self.capex < 0 or self.opex < 0 or self.saving_m3 < 0 or self.price < 0:
            raise EconError("negative")
        if not -50 < self.rate_pct < 1000:
            raise EconError("rate")
        if not 0 <= self.degradation_pct < 100:
            raise EconError("degradation")
        if self.repl_year and not 1 <= self.repl_year <= self.life:
            raise EconError("repl_year")


@dataclass
class EconResult:
    inputs: EconInputs
    years: List[int]
    volume: List[float]
    benefit: List[float]
    cost: List[float]
    net: List[float]
    cum: List[float]
    dnet: List[float]
    dcum: List[float]
    npv: float
    irr: Optional[float]              # percent
    payback: Optional[float]
    dpayback: Optional[float]
    bcr: Optional[float]
    pi: Optional[float]
    lcow: Optional[float]
    pv_benefit: float
    pv_cost: float
    pv_volume: float
    verdict: str                      # good | marginal | poor | invalid

    @property
    def total_volume(self) -> float:
        return sum(self.volume)


def npv_of(rate: float, flows: List[float]) -> float:
    return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(flows))


def irr_of(flows: List[float]) -> Optional[float]:
    """Internal rate of return as a fraction; None without a sign change. Bisection on a bracketing grid."""
    if not (any(f < 0 for f in flows) and any(f > 0 for f in flows)):
        return None
    grid = [-0.95, -0.8, -0.6, -0.4, -0.2, -0.1, 0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0, 2.0, 5.0, 10.0, 50.0]
    prev_r, prev_v = grid[0], npv_of(grid[0], flows)
    for r in grid[1:]:
        v = npv_of(r, flows)
        if prev_v == 0:
            return prev_r
        if prev_v * v < 0:
            lo, hi, flo = prev_r, r, prev_v
            for _ in range(200):
                mid = (lo + hi) / 2
                fm = npv_of(mid, flows)
                if flo * fm <= 0:
                    hi = mid
                else:
                    lo, flo = mid, fm
                if hi - lo < 1e-12:
                    break
            return (lo + hi) / 2
        prev_r, prev_v = r, v
    return None


def _payback(net: List[float]) -> Optional[float]:
    """First time the cumulative sum of ``net`` (index 0 = t0) reaches zero, linear within the year."""
    cum = net[0]
    if cum >= 0:
        return 0.0
    for t in range(1, len(net)):
        nxt = cum + net[t]
        if nxt >= 0 and net[t] > 0:
            return (t - 1) + (-cum) / net[t]
        cum = nxt
    return None


def evaluate(inp: EconInputs) -> EconResult:
    inp.validate()
    n = int(inp.life)
    r = inp.rate_pct / 100.0
    g, e, d = inp.price_esc_pct / 100.0, inp.opex_esc_pct / 100.0, inp.degradation_pct / 100.0
    years = list(range(n + 1))
    vol = [0.0] * (n + 1)
    ben = [0.0] * (n + 1)
    cost = [0.0] * (n + 1)
    cost[0] = inp.capex
    salvage_pv_part = 0.0
    for t in range(1, n + 1):
        vol[t] = inp.saving_m3 * (1.0 - d) ** (t - 1)
        ben[t] = (vol[t] * inp.price + inp.other_benefit) * (1.0 + g) ** (t - 1)
        cost[t] = inp.opex * (1.0 + e) ** (t - 1)
        if inp.repl_year == t:
            cost[t] += inp.repl_cost
    ben[n] += inp.salvage
    net = [ben[t] - cost[t] for t in years]
    cum, s = [], 0.0
    for v in net:
        s += v
        cum.append(s)
    disc = [1.0 / (1.0 + r) ** t for t in years]
    dnet = [net[t] * disc[t] for t in years]
    dcum, s = [], 0.0
    for v in dnet:
        s += v
        dcum.append(s)
    pv_b = sum(ben[t] * disc[t] for t in years)
    pv_c = sum(cost[t] * disc[t] for t in years)
    pv_v = sum(vol[t] * disc[t] for t in years)
    npv = pv_b - pv_c
    irr = irr_of(net)
    bcr = pv_b / pv_c if pv_c > 0 else None
    pi = npv / inp.capex if inp.capex > 0 else None
    lcow = (pv_c - inp.salvage * disc[n]) / pv_v if pv_v > 0 else None
    if inp.saving_m3 <= 0:
        verdict = "invalid"
    elif npv > 0 and bcr is not None and bcr >= 1.2 and (irr is None or irr * 100 > inp.rate_pct):
        verdict = "good"
    elif npv >= 0:
        verdict = "marginal"
    else:
        verdict = "poor"
    return EconResult(inp, years, vol, ben, cost, net, cum, dnet, dcum, npv,
                      None if irr is None else irr * 100.0, _payback(net), _payback(dnet), bcr, pi, lcow,
                      pv_b, pv_c, pv_v, verdict)


# ------------------------------------------------------------------ sensitivity
SENS_VARS = ("saving_m3", "price", "capex", "opex", "rate_pct", "life")


def sensitivity(inp: EconInputs, delta: float = 0.2) -> List[Tuple[str, float, float, float]]:
    """(variable, NPV at -delta, NPV at +delta, swing), largest swing first."""
    import dataclasses
    rows = []
    for name in SENS_VARS:
        base = getattr(inp, name)
        vals = []
        for sign in (-1, 1):
            v = base * (1 + sign * delta)
            if name == "life":
                v = max(1, int(round(v)))
            vals.append(evaluate(dataclasses.replace(inp, **{name: v})).npv)
        rows.append((name, vals[0], vals[1], abs(vals[1] - vals[0])))
    rows.sort(key=lambda r: -r[3])
    return rows


# ------------------------------------------------------------------ link to the plant / plan
def discharge_value_per_m3(plant: Plant, target: str = "") -> float:
    """Currency per m3 of intake saved that is also saved on discharge fees and wastewater treatment,
    assuming discharge falls in proportion to intake."""
    omap = {x.name: x for x in plant.outlets}
    tmap = {x.name: x for x in plant.treatments}

    def one(s) -> Tuple[float, float]:
        vi, vd = s.total_intake, s.total_discharge
        if vi <= 0 or vd <= 0:
            return 0.0, vi
        fees = sum(omap[k].unit_cost * v for k, v in s.discharge.items() if k in omap)
        wt = sum(tmap[k].unit_cost * f for k, f in s.wastewater_treatments.items() if k in tmap) * vd
        return (fees + wt) / vi, vi

    pool = plant.leaves_of(target) if target else plant.leaves()      # a unit with equipment: weighted over its equipment
    tot = sum(s.total_intake for s in pool)
    return sum(one(s)[0] * one(s)[1] for s in pool) / tot if tot > 0 else 0.0


def default_price(plant: Plant, target: str = "") -> float:
    from .measures import value_per_m3
    return value_per_m3(plant, target) + discharge_value_per_m3(plant, target)


def inputs_from_item(plant: Plant, item: PlanItem, saving_m3: Optional[float] = None) -> EconInputs:
    """Build the economic inputs of a plan item. ``saving_m3`` defaults to the item's share of the plan's
    combined saving (so overlapping measures are not double counted)."""
    from .measures import evaluate_plan
    if saving_m3 is None:
        saving_m3 = 0.0
        for ln in evaluate_plan(plant).lines:
            if ln.item is item:
                saving_m3 = ln.saving
                break
    price = item.water_price if item.water_price > 0 else default_price(plant, item.target)
    return EconInputs(
        saving_m3=saving_m3, price=price, capex=item.capex, opex=item.opex, life=int(round(item.life_years)),
        rate_pct=item.rate_pct, price_esc_pct=item.price_esc_pct, opex_esc_pct=item.opex_esc_pct,
        degradation_pct=item.degradation_pct, other_benefit=item.other_benefit, salvage=item.salvage,
        repl_year=int(item.repl_year), repl_cost=item.repl_cost)


@dataclass
class ItemEcon:
    item: PlanItem
    result: Optional[EconResult]
    error: str = ""


def evaluate_plan_economics(plant: Plant) -> List[ItemEcon]:
    """Economics of every plan item (each with its share of the combined saving)."""
    from .measures import evaluate_plan
    out: List[ItemEcon] = []
    for ln in evaluate_plan(plant).lines:
        try:
            out.append(ItemEcon(ln.item, evaluate(inputs_from_item(plant, ln.item, ln.saving))))
        except EconError as e:
            out.append(ItemEcon(ln.item, None, str(e)))
    return out
