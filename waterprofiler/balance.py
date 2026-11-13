"""Water mass balance and calibration (report Section 2.2.2, Table 6).

Corrected sign convention
-------------------------
For subsystem x the balance residual is

    L_x = I_x + R'_in - R'_out - P_x - E_x - W_x - dS_x

i.e. everything entering minus everything leaving minus the change of stored volume. ``R_x`` (recirculation
inside the subsystem) cancels and does not enter the balance. The report
prints the signs of this equation inconsistently. The residual is *not* assumed to be a leak: it holds
meter error, unrecorded use and leakage together. ``sigma`` is its measurement uncertainty (see uncertainty.py) and
``significant`` says whether it is larger than 2 sigma.

For the plant:

    L = sum(I_x) - [sum(P_x) + sum(E_x) + sum(W_x) + sum(dS_x)]

Calibration compares sum(I_x) with the metered/billed source intake and
sum(W_x) with the metered discharge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import uncertainty as U
from .model import Plant, Subsystem


@dataclass
class SubsystemBalance:
    name: str
    inflow: float
    outflow: float
    unknown_loss: float          # L_x  (negative -> outflow exceeds inflow)
    unknown_loss_pct_of_inflow: float
    status: str                  # "balanced" | "unaccounted loss" | "excess outflow"
    storage_change: float = 0.0  # dS_x
    sigma: float = 0.0           # standard uncertainty of the residual
    significant: bool = False    # |residual| > 2 sigma


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
    sum_storage: float = 0.0
    sigma: float = 0.0                        # standard uncertainty of the plant residual
    significant: bool = False                 # |L| > 2 sigma
    unmetered_share: float = 0.0              # share of the flow volume without a stated meter accuracy
    imbalance_sigma: Optional[float] = None   # standard uncertainty of plant_imbalance
    imbalance_significant: Optional[bool] = None   # |plant_imbalance| > 2 sigma: more than the meters alone explain
    permit_use: Dict[str, tuple] = field(default_factory=dict)   # source -> (used m3, permit m3, used / permit)
    unmetered_sources: List[str] = field(default_factory=list)   # sources without a meter while others have one
    unmetered_outlets: List[str] = field(default_factory=list)

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


def subsystem_balance(s: Subsystem, tol: float = 0.02, sigma: float = 0.0) -> SubsystemBalance:
    inflow = s.total_intake + s.from_other
    outflow = s.to_other + s.product + s.evaporation + s.total_discharge
    l = inflow - outflow - s.storage_change
    pct = 100.0 * l / inflow if inflow > 0 else 0.0
    return SubsystemBalance(s.name, inflow, outflow, l, pct, _status(l, inflow, tol), s.storage_change, sigma,
                            abs(l) > U.K * sigma and sigma > 0)


def plant_balance(plant: Plant, tol: float = 0.02) -> PlantBalance:
    plant.rollup()
    leaves = plant.leaves()                 # plant totals are sums over the nodes that carry data
    acc = U.meter_accuracy(plant)
    subs = [subsystem_balance(s, tol, U.node_sigma(plant, s, acc)) for s in plant.units()]   # a partition of the plant
    nodes = {s.name: subsystem_balance(s, tol, U.node_sigma(plant, s, acc)) for s in plant.subsystems}

    sum_i = sum(s.total_intake for s in leaves)
    sum_w = sum(s.total_discharge for s in leaves)
    sum_e = sum(s.evaporation for s in leaves)
    sum_p = sum(s.product for s in leaves)
    sum_s = sum(s.storage_change for s in leaves)
    l = sum_i - (sum_p + sum_e + sum_w + sum_s)
    sig, unmet = U.plant_sigma(plant)

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

    # Plant meters. When only some sources (outlets) have a meter, an unmetered one is taken at the volume allocated to it,
    # so the boundary balance is not understated; the result is flagged with a warning.
    def totals(items, allocated):
        used = {x.name: (x.metered_m3 if x.metered_m3 is not None else allocated.get(x.name, 0.0)) for x in items}
        some = any(x.metered_m3 is not None for x in items)
        missing = [x.name for x in items if x.metered_m3 is None and allocated.get(x.name, 0.0) > 0] if some else []
        return (sum(used.values()) if some else None), used, missing

    m_in, used_in, miss_in = totals(plant.sources, by_src)
    m_out, used_out, miss_out = totals(plant.outlets, by_out)
    if miss_in:
        warnings.append("Sources without a meter while others have one: " + ", ".join(miss_in)
                        + "; their allocated volume is used in the plant balance")
    if miss_out:
        warnings.append("Outlets without a meter while others have one: " + ", ".join(miss_out)
                        + "; their allocated volume is used in the plant balance")

    permit_use: Dict[str, tuple] = {}
    for x in plant.sources:
        if x.permit_on and x.permit_m3 > 0:
            used = used_in.get(x.name, 0.0)
            permit_use[x.name] = (used, x.permit_m3, used / x.permit_m3)
            if used > x.permit_m3:
                warnings.append(f"Source '{x.name}': abstraction {used:,.0f} m3/year exceeds its permit {x.permit_m3:,.0f} m3/year "
                                f"({100 * used / x.permit_m3:.0f} %)")
            elif used >= 0.9 * x.permit_m3:
                warnings.append(f"Source '{x.name}': abstraction {used:,.0f} m3/year is {100 * used / x.permit_m3:.0f} % of its permit "
                                f"{x.permit_m3:,.0f} m3/year")

    src_imb = (m_in - sum_i) if m_in is not None else None
    out_imb = (m_out - sum_w) if m_out is not None else None
    plant_imb = (m_in - m_out - sum_e - sum_p - sum_s) if (m_in is not None and m_out is not None) else None
    imb_sigma = imb_sig = None
    if plant_imb is not None:
        imb_sigma = U.boundary_sigma(plant, used_in, used_out)
        imb_sig = abs(plant_imb) > U.K * imb_sigma > 0
        if imb_sig:
            warnings.append(f"Plant boundary imbalance {plant_imb:,.0f} m3 is larger than 2 sigma ({imb_sigma:,.0f} m3): "
                            "the meters alone do not explain it (leak, unmetered flow or a meter error)")

    return PlantBalance(
        subsystems=subs, sum_intake=sum_i, sum_discharge=sum_w, sum_evaporation=sum_e,
        sum_product=sum_p, unknown_loss=l, metered_intake=m_in, metered_discharge=m_out,
        source_side_imbalance=src_imb, discharge_side_imbalance=out_imb,
        plant_imbalance=plant_imb, intake_by_source=by_src, discharge_by_outlet=by_out,
        warnings=warnings, nodes=nodes, sum_storage=sum_s, sigma=sig, significant=abs(l) > U.K * sig > 0,
        unmetered_share=unmet, imbalance_sigma=imb_sigma, imbalance_significant=imb_sig,
        permit_use=permit_use, unmetered_sources=miss_in, unmetered_outlets=miss_out,
    )
