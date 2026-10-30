"""True cost of water (report Section 2.2.3, Table 7), in currency units per year.

For subsystem x:

    $x = sum_s $s * I_x,s                      (source water)
       + sum_o $o * W_x,o                      (wastewater discharge)
       + sum_t $t * T_x,t                      (water treatment)
       + sum_t' $t' * T'_x,t'                  (wastewater treatment)
       + $elec * Elec_x                        (pumps and motors)
       + $fuel * Fuel_x                        (heat lost in wastewater)

Treated water volume:   T_x,t  = f_x,t * (I_x + R'_in,x)
Treated wastewater:     T'_x,t' = f_x,t' * W_x

Heat in wastewater (report Table 7, step 4, with the sign corrected so that a
wastewater stream hotter than the intake counts as lost heat):

    Q_kWh = rho * W * cp * (T_wastewater - T_intake) / 3600 / eta_heating
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .balance import plant_balance
from .model import Plant, Subsystem
from .units import CP_WATER_KJ_PER_KG_K, KJ_PER_KWH, RHO_WATER_KG_PER_M3

COMPONENTS = ("intake", "water_treatment", "pumping", "wastewater_treatment", "discharge", "heat")


@dataclass
class SubsystemCost:
    name: str
    intake_m3: float
    discharge_m3: float
    components: Dict[str, float]
    electricity_kwh: float
    heat_kwh_thermal: float
    treated_water_m3: Dict[str, float] = field(default_factory=dict)
    treated_wastewater_m3: Dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return sum(self.components.values())

    @property
    def per_m3_intake(self) -> Optional[float]:
        return self.total / self.intake_m3 if self.intake_m3 > 0 else None


@dataclass
class PlantCost:
    subsystems: List[SubsystemCost]
    by_component: Dict[str, float]
    total: float
    direct_billed_cost: float          # source water purchase + municipal-style discharge fees
    true_to_direct_ratio: Optional[float]
    true_cost_per_m3_intake: Optional[float]
    water_share: Dict[str, float]      # subsystem -> share of total intake
    cost_share: Dict[str, float]       # subsystem -> share of true cost
    warnings: List[str] = field(default_factory=list)


def heat_lost_kwh(discharge_m3: float, t_intake_c: Optional[float], t_wastewater_c: Optional[float],
                  efficiency: float) -> float:
    if t_intake_c is None or t_wastewater_c is None or discharge_m3 <= 0:
        return 0.0
    dt = t_wastewater_c - t_intake_c
    if dt <= 0:
        return 0.0
    eta = efficiency if efficiency > 0 else 1.0
    kj = RHO_WATER_KG_PER_M3 * discharge_m3 * CP_WATER_KJ_PER_KG_K * dt
    return kj / KJ_PER_KWH / eta


def subsystem_cost(plant: Plant, s: Subsystem) -> SubsystemCost:
    c = plant.costs
    comp = {k: 0.0 for k in COMPONENTS}

    for src_name, vol in s.intake.items():
        comp["intake"] += plant.source(src_name).unit_cost * vol
    for out_name, vol in s.discharge.items():
        comp["discharge"] += plant.outlet(out_name).unit_cost * vol

    treated_w: Dict[str, float] = {}
    for tname, frac in s.water_treatments.items():
        vol = frac * (s.total_intake + s.from_other)
        treated_w[tname] = vol
        comp["water_treatment"] += plant.treatment(tname).unit_cost * vol

    treated_ww: Dict[str, float] = {}
    for tname, frac in s.wastewater_treatments.items():
        vol = frac * s.total_discharge
        treated_ww[tname] = vol
        comp["wastewater_treatment"] += plant.treatment(tname).unit_cost * vol

    kwh = sum(p.kwh_per_year() for p in s.pumps)
    comp["pumping"] = c.electricity_per_kwh * kwh

    heat = heat_lost_kwh(s.total_discharge, s.t_intake_c, s.t_wastewater_c, c.heating_efficiency)
    comp["heat"] = c.fuel_per_kwh_thermal * heat

    return SubsystemCost(s.name, s.total_intake, s.total_discharge, comp, kwh, heat, treated_w, treated_ww)


def plant_cost(plant: Plant) -> PlantCost:
    warnings: List[str] = []
    subs = []
    for s in plant.subsystems:
        for t in list(s.water_treatments) + list(s.wastewater_treatments):
            if not any(x.name == t for x in plant.treatments):
                warnings.append(f"{s.name}: unknown treatment '{t}'")
        for t, f in {**s.water_treatments, **s.wastewater_treatments}.items():
            if not 0.0 <= f <= 1.0:
                warnings.append(f"{s.name}: treated fraction for '{t}' is {f}, expected 0..1")
        subs.append(subsystem_cost(plant, s))

    by_comp = {k: sum(sc.components[k] for sc in subs) for k in COMPONENTS}
    total = sum(by_comp.values())
    direct = by_comp["intake"] + by_comp["discharge"]
    total_intake = sum(sc.intake_m3 for sc in subs)

    water_share = {sc.name: (sc.intake_m3 / total_intake if total_intake > 0 else 0.0) for sc in subs}
    cost_share = {sc.name: (sc.total / total if total > 0 else 0.0) for sc in subs}

    return PlantCost(
        subsystems=subs, by_component=by_comp, total=total, direct_billed_cost=direct,
        true_to_direct_ratio=(total / direct) if direct > 0 else None,
        true_cost_per_m3_intake=(total / total_intake) if total_intake > 0 else None,
        water_share=water_share, cost_share=cost_share, warnings=warnings,
    )
