"""Allocation of the plant's water (and its true cost) to the products.

Every node that carries data (equipment, or a unit without equipment) states which percentage of its water
goes to which product. The rest of a node (100 % minus the shares) serves the plant as a whole: utilities,
sanitary use, irrigation. With ``alloc_spread`` that remainder is spread over the products in proportion to the
water they were allocated directly; otherwise it is reported as unallocated.

Results per product: intake, discharge, consumption (evaporation + water in product), true cost and the intensities
per unit of that product (m3 per t, m3 per piece ...): the plant-wide intensity is meaningless when products are
measured in different units.

Identity (tested): sum over products + unallocated = plant total, for intake, discharge, consumption and cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .cost import PlantCost
from .model import Plant

METRICS = ("intake", "discharge", "consumption", "cost")


@dataclass
class ProductWater:
    name: str
    unit: str
    per_year: float
    direct: Dict[str, float]                  # allocated by the nodes' shares
    spread: Dict[str, float]                  # received from the shared remainder
    intake_per_unit: Optional[float] = None
    discharge_per_unit: Optional[float] = None
    consumption_per_unit: Optional[float] = None
    cost_per_unit: Optional[float] = None

    def total(self, metric: str) -> float:
        return self.direct.get(metric, 0.0) + self.spread.get(metric, 0.0)


@dataclass
class Allocation:
    products: List[ProductWater]
    totals: Dict[str, float]                  # plant totals
    unallocated: Dict[str, float]             # not given to any product
    shared: Dict[str, float]                  # the remainder that was spread (0 when alloc_spread is off)
    coverage_pct: float                       # share of the intake that nodes assigned to products directly
    nodes_without_share: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def product(self, name: str) -> Optional[ProductWater]:
        return next((p for p in self.products if p.name == name), None)


def node_shares(plant: Plant, name: str, products: List[str], warnings: Optional[List[str]] = None) -> Dict[str, float]:
    """Fractions (0..1) of node ``name`` going to each known product; scaled down if they exceed 100 %."""
    raw = plant.allocation.get(name) or {}
    out: Dict[str, float] = {}
    for p, v in raw.items():
        if p not in products:
            if warnings is not None and v:
                warnings.append(f"{name}: share given to unknown product '{p}'")
            continue
        if v and v > 0:
            out[p] = float(v) / 100.0
    tot = sum(out.values())
    if tot > 1.0 + 1e-9:
        if warnings is not None:
            warnings.append(f"{name}: shares add up to {100 * tot:.1f} % (> 100 %), scaled down")
        out = {p: v / tot for p, v in out.items()}
    return out


def allocate(plant: Plant, cost: PlantCost) -> Allocation:
    plant.rollup()
    prods = plant.site.products
    names = [p.name for p in prods]
    warns: List[str] = []
    direct = {p.name: {m: 0.0 for m in METRICS} for p in prods}
    totals = {m: 0.0 for m in METRICS}
    rest = {m: 0.0 for m in METRICS}
    without: List[str] = []
    for s in plant.leaves():
        nc = cost.nodes.get(s.name)
        vals = {"intake": s.total_intake, "discharge": s.total_discharge,
                "consumption": s.evaporation + s.product, "cost": nc.total if nc else 0.0}
        if not any(vals.values()):
            continue
        sh = node_shares(plant, s.name, names, warns)
        if not sh:
            without.append(s.name)
        used = sum(sh.values())
        for m in METRICS:
            totals[m] += vals[m]
            rest[m] += vals[m] * (1.0 - used)
            for p, f in sh.items():
                direct[p][m] += vals[m] * f
    w_tot = sum(d["intake"] for d in direct.values())
    spread_on = plant.alloc_spread and w_tot > 0
    out: List[ProductWater] = []
    for p in prods:
        sp = {m: (rest[m] * direct[p.name]["intake"] / w_tot if spread_on else 0.0) for m in METRICS}
        pw = ProductWater(p.name, p.unit or plant.production_unit, p.per_year or 0.0, dict(direct[p.name]), sp)
        q = pw.per_year
        if q > 0:
            pw.intake_per_unit = pw.total("intake") / q
            pw.discharge_per_unit = pw.total("discharge") / q
            pw.consumption_per_unit = pw.total("consumption") / q
            pw.cost_per_unit = pw.total("cost") / q
        out.append(pw)
    shared = dict(rest) if spread_on else {m: 0.0 for m in METRICS}
    unalloc = {m: 0.0 if spread_on else rest[m] for m in METRICS}
    cov = 100.0 * w_tot / totals["intake"] if totals["intake"] > 0 else 0.0
    if prods and without:
        warns.append("nodes with data but no product share: " + ", ".join(without))
    if not prods and totals["intake"] > 0:
        warns.append("no products defined")
    if plant.alloc_spread and not spread_on and rest["intake"] > 0 and prods:
        warns.append("the shared remainder cannot be spread: no node has been assigned to a product")
    return Allocation(out, totals, unalloc, shared, cov, without, warns)
