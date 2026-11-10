"""Measurement uncertainty of the water balance.

Each flow of a node has a standard uncertainty sigma = relative accuracy x value:
  * the accuracy of the meter whose tag is that flow (``sub:<node>:intake`` ... ``source:<name>`` / ``outlet:<name>`` at
    plant level; Meter.accuracy_pct), when one is stated;
  * otherwise the assumed relative uncertainty of an unmetered flow (``plant.profile.unmetered_unc_pct``, an input).

The residual R = sum(in) - sum(out) - dS of a node then has sigma_R = sqrt(sum(sigma_i^2)) (independent errors). A residual is
*significant* when |R| > 2 sigma_R (about 95 % coverage): below that, a non-zero residual is what the meters alone would give.
Transfers between two nodes of the plant are the same volume, entered once as a link: they cancel at plant level, so only the
metered (or assumed) uncertainty of each end counts at node level.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .model import Plant, Subsystem

K = 2.0                       # coverage factor of the significance test (about 95 %)

# flow -> (tag suffix, getter)
_NODE_FLOWS = (
    ("intake", lambda s: s.total_intake),
    ("discharge", lambda s: s.total_discharge),
    ("evaporation", lambda s: s.evaporation),
    ("product", lambda s: s.product),
    ("storage", lambda s: abs(s.storage_change)),
)


def meter_accuracy(plant: Plant) -> Dict[str, float]:
    """tag -> relative accuracy (fraction) of the meters that state one."""
    return {m.tag: m.accuracy_pct / 100.0 for m in plant.site.meters if m.tag and m.accuracy_pct > 0}


def unmetered_rel(plant: Plant) -> float:
    return max(0.0, plant.profile.unmetered_unc_pct) / 100.0


def node_components(plant: Plant, s: Subsystem, acc: Dict[str, float] = None) -> List[Tuple[str, float, float, bool]]:
    """[(flow, value, sigma, metered)] for one node; transfers use the assumed uncertainty (a link has no meter)."""
    acc = meter_accuracy(plant) if acc is None else acc
    un = unmetered_rel(plant)
    out: List[Tuple[str, float, float, bool]] = []
    for f, get in _NODE_FLOWS:
        v = get(s)
        if v <= 0:
            continue
        a = acc.get(f"sub:{s.name}:{f}")
        out.append((f, v, (a if a is not None else un) * v, a is not None))
    for f, v in (("from_other", s.from_other), ("to_other", s.to_other)):
        if v > 0:
            out.append((f, v, un * v, False))
    return out


def node_sigma(plant: Plant, s: Subsystem, acc: Dict[str, float] = None) -> float:
    """sigma of the residual of a node. A unit with equipment: the root of the sum of squares of its equipment."""
    acc = meter_accuracy(plant) if acc is None else acc
    kids = plant.children(s.name)
    if kids:
        return math.sqrt(sum(node_sigma(plant, c, acc) ** 2 for c in kids))
    return math.sqrt(sum(sg ** 2 for _f, _v, sg, _m in node_components(plant, s, acc)))


def plant_sigma(plant: Plant) -> Tuple[float, float]:
    """(sigma of the plant residual, share of the flow volume that has no stated meter accuracy).

    Transfers cancel at plant level. A source or outlet with a stated meter accuracy replaces the per-node sigma of the water
    drawn from it or sent to it.
    """
    acc = meter_accuracy(plant)
    un = unmetered_rel(plant)
    var = 0.0
    vol_all = vol_unmetered = 0.0
    by_src: Dict[str, float] = {}
    by_out: Dict[str, float] = {}
    for s in plant.leaves():
        for k, v in s.intake.items():
            by_src[k] = by_src.get(k, 0.0) + v
        for k, v in s.discharge.items():
            by_out[k] = by_out.get(k, 0.0) + v
        for f, v, sg, metered in node_components(plant, s, acc):
            if f in ("from_other", "to_other", "intake", "discharge"):
                continue                       # intake and discharge are taken by source and outlet below
            var += sg ** 2
            vol_all += v
            vol_unmetered += 0.0 if metered else v
    for tag, d in (("source", by_src), ("outlet", by_out)):
        for name, v in d.items():
            a = acc.get(f"{tag}:{name}")
            var += ((a if a is not None else un) * v) ** 2
            vol_all += v
            vol_unmetered += 0.0 if a is not None else v
    return math.sqrt(var), (vol_unmetered / vol_all if vol_all > 0 else 0.0)
