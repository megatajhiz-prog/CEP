"""Allocation of water to products.

Each node that carries data (a unit without equipment, or an equipment) says which share of its water serves which
product: ``plant.allocation[node][product] = fraction`` (0..1, the fractions of a node add up to at most 1). What is not
allocated is *general* water (utilities, sanitary, losses, ...) and is reported separately: it is never silently spread.

For every product the module reports the intake, the consumed part (evaporation + water in product), the discharge and
the true cost that belong to it, and the intensities per unit of that product (m3/unit and cost/unit). Intensities are
per product, so products measured in different units are never added together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .cost import PlantCost, plant_cost
from .model import Plant

EPS = 1e-9


@dataclass
class ProductWater:
    name: str                      # "" for the general (unallocated) water
    unit: str = ""
    production: float = 0.0
    intake: float = 0.0
    consumption: float = 0.0       # evaporation + water in product
    discharge: float = 0.0
    cost: float = 0.0              # true cost of the allocated water
    intake_share_pct: float = 0.0
    per_unit_intake: Optional[float] = None     # m3 per unit of product
    per_unit_cost: Optional[float] = None       # currency per unit of product


@dataclass
class AllocationResult:
    products: List[ProductWater]
    general: ProductWater
    total_intake: float
    total_cost: float
    allocated_pct: float           # share of the plant's intake that is allocated to products
    by_node: Dict[str, Dict[str, float]] = field(default_factory=dict)   # effective fractions used, per node
    warnings: List[str] = field(default_factory=list)


def clean_fractions(fr: Dict[str, float]) -> Dict[str, float]:
    """Drop empty / negative entries."""
    return {p: float(f) for p, f in (fr or {}).items() if f and f > 0}


def set_fractions(plant: Plant, node: str, fractions: Dict[str, float]) -> None:
    """Store the fractions of a node (empty = no allocation). Raises ValueError for a sum above 1 or a node that is not a leaf."""
    fr = clean_fractions(fractions)
    if sum(fr.values()) > 1.0 + 1e-6:
        raise ValueError(f"allocation of '{node}' adds up to {sum(fr.values()):.3f} > 1")
    if node not in {s.name for s in plant.leaves()}:
        raise ValueError(f"'{node}' carries no data of its own: allocate its equipment")
    if fr:
        plant.allocation[node] = fr
    else:
        plant.allocation.pop(node, None)


def split_by_weights(plant: Plant, node: str, weights: Dict[str, float]) -> None:
    """Allocate the whole of a node in proportion to ``weights`` (product -> weight)."""
    w = clean_fractions(weights)
    tot = sum(w.values())
    if tot <= 0:
        raise ValueError("weights must contain a positive value")
    set_fractions(plant, node, {p: v / tot for p, v in w.items()})


def allocate(plant: Plant, cost: Optional[PlantCost] = None) -> AllocationResult:
    plant.rollup()
    cost = cost or plant_cost(plant)
    products = {p.name: p for p in plant.site.products}
    rows = {p: ProductWater(p, products[p].unit or plant.production_unit, products[p].per_year or 0.0)
            for p in products}
    general = ProductWater("")
    leaves = {s.name: s for s in plant.leaves()}
    warnings: List[str] = []
    used: Dict[str, Dict[str, float]] = {}

    for node in plant.allocation:
        if node not in leaves and plant.node(node) is not None:
            warnings.append(f"alloc_not_leaf:{node}")
    for name, s in leaves.items():
        fr = clean_fractions(plant.allocation.get(name, {}))
        for p in [p for p in fr if p not in products]:
            warnings.append(f"alloc_unknown_product:{name}:{p}")
            fr.pop(p)
        tot = sum(fr.values())
        if tot > 1.0 + 1e-6:
            warnings.append(f"alloc_over:{name}")
            fr = {p: f / tot for p, f in fr.items()}
            tot = 1.0
        used[name] = fr
        nc = cost.nodes.get(name)
        vals = (s.total_intake, s.evaporation + s.product, s.total_discharge, nc.total if nc else 0.0)
        for p, f in fr.items():
            r = rows[p]
            r.intake += f * vals[0]; r.consumption += f * vals[1]; r.discharge += f * vals[2]; r.cost += f * vals[3]
        g = max(0.0, 1.0 - tot)
        general.intake += g * vals[0]; general.consumption += g * vals[1]
        general.discharge += g * vals[2]; general.cost += g * vals[3]

    total_i = sum(s.total_intake for s in leaves.values())
    total_c = sum((cost.nodes[n].total if n in cost.nodes else 0.0) for n in leaves)
    for r in list(rows.values()) + [general]:
        r.intake_share_pct = 100.0 * r.intake / total_i if total_i > 0 else 0.0
        if r.name and r.production > 0:
            r.per_unit_intake = r.intake / r.production
            r.per_unit_cost = r.cost / r.production
    allocated = sum(r.intake for r in rows.values())
    if len({r.unit for r in rows.values()}) > 1:
        warnings.append("alloc_mixed_units")
    return AllocationResult(list(rows.values()), general, total_i, total_c,
                            100.0 * allocated / total_i if total_i > 0 else 0.0, used, warnings)
