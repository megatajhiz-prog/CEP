"""Water mass balance and calibration (report Section 2.2.2, Table 6).

Corrected sign convention
-------------------------
For subsystem x the unknown (unaccounted) loss is

    L_x = I_x + R'_in - R'_out - P_x - E_x - W_x

i.e. everything entering minus everything leaving. ``R_x`` (recirculation
inside the subsystem) cancels and does not enter the balance. The report
prints the signs of this equation inconsistently.

For the plant:

    L = sum(I_x) - [sum(P_x) + sum(E_x) + sum(W_x)]

Calibration compares sum(I_x) with the metered/billed source intake and
sum(W_x) with the metered discharge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import Plant, Subsystem


@dataclass
class SubsystemBalance:
    name: str
    inflow: float
    outflow: float
    unknown_loss: float          # L_x  (negative -> outflow exceeds inflow)
    unknown_loss_pct_of_inflow: float
    status: str                  # "balanced" | "unaccounted loss" | "excess outflow"


@dataclass
class PlantBalance:
    subsystems: List[SubsystemBalance]
    sum_intake: float
    sum_discharge: float
    sum_evaporation: float
    sum_product: float
    unknown_loss: float                       # L
    metered_intake: Optional[float]
    metered_discharge: Optional[float]
    source_side_imbalance: Optional[float]    # metered intake - sum(I_x): water used but not allocated
    discharge_side_imbalance: Optional[float] # metered discharge - sum(W_x)
    plant_imbalance: Optional[float]          # metered intake - metered discharge - sum(E) - sum(P)
    intake_by_source: Dict[str, float] = field(default_factory=dict)
    discharge_by_outlet: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    nodes: Dict[str, "SubsystemBalance"] = field(default_factory=dict)   # every unit and every equipment, by name

    @property
    def closure_pct(self) -> Optional[float]:
        """Plant imbalance as a percent of metered intake."""
        if self.plant_imbalance is None or not self.metered_intake:
            return None
        return 100.0 * self.plant_imbalance / self.metered_intake


def _status(l: float, inflow: float, tol: float) -> str:
    if inflow <= 0:
        return "balanced" if abs(l) <= 1e-9 else "excess outflow"
    r = l / inflow
    if abs(r) <= tol:
        return "balanced"
    return "unaccounted loss" if r > 0 else "excess outflow"


def subsystem_balance(s: Subsystem, tol: float = 0.02) -> SubsystemBalance:
    inflow = s.total_intake + s.from_other
    outflow = s.to_other + s.product + s.evaporation + s.total_discharge
    l = inflow - outflow
    pct = 100.0 * l / inflow if inflow > 0 else 0.0
    return SubsystemBalance(s.name, inflow, outflow, l, pct, _status(l, inflow, tol))


def plant_balance(plant: Plant, tol: float = 0.02) -> PlantBalance:
    plant.rollup()
    leaves = plant.leaves()                 # plant totals are sums over the nodes that carry data
    subs = [subsystem_balance(s, tol) for s in plant.units()]            # a partition: units (with their equipment summed)
    nodes = {s.name: subsystem_balance(s, tol) for s in plant.subsystems}

    sum_i = sum(s.total_intake for s in leaves)
    sum_w = sum(s.total_discharge for s in leaves)
    sum_e = sum(s.evaporation for s in leaves)
    sum_p = sum(s.product for s in leaves)
    l = sum_i - (sum_p + sum_e + sum_w)

    by_src: Dict[str, float] = {src.name: 0.0 for src in plant.sources}
    by_out: Dict[str, float] = {o.name: 0.0 for o in plant.outlets}
    warnings: List[str] = []
    for s in leaves:
        for k, v in s.intake.items():
            if k not in by_src:
                warnings.append(f"{s.name}: intake from unknown source '{k}'")
            by_src[k] = by_src.get(k, 0.0) + v
        for k, v in s.discharge.items():
            if k not in by_out:
                warnings.append(f"{s.name}: discharge to unknown outlet '{k}'")
            by_out[k] = by_out.get(k, 0.0) + v

    # Internal transfers must cancel across the plant.
    transfer_gap = sum(s.to_other for s in leaves) - sum(s.from_other for s in leaves)
    if abs(transfer_gap) > 1e-6 * max(1.0, sum_i):
        warnings.append(
            f"Inter-subsystem transfers do not cancel (sent minus received = {transfer_gap:.1f} m3); "
            "check R'_out and R'_in entries"
        )

    srcs = [x.metered_m3 for x in plant.sources]
    outs = [x.metered_m3 for x in plant.outlets]
    m_in = sum(v for v in srcs if v is not None) if any(v is not None for v in srcs) else None
    m_out = sum(v for v in outs if v is not None) if any(v is not None for v in outs) else None

    src_imb = (m_in - sum_i) if m_in is not None else None
    out_imb = (m_out - sum_w) if m_out is not None else None
    plant_imb = (m_in - m_out - sum_e - sum_p) if (m_in is not None and m_out is not None) else None

    return PlantBalance(
        subsystems=subs, sum_intake=sum_i, sum_discharge=sum_w, sum_evaporation=sum_e,
        sum_product=sum_p, unknown_loss=l, metered_intake=m_in, metered_discharge=m_out,
        source_side_imbalance=src_imb, discharge_side_imbalance=out_imb,
        plant_imbalance=plant_imb, intake_by_source=by_src, discharge_by_outlet=by_out,
        warnings=warnings, nodes=nodes,
    )
