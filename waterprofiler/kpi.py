"""Normalised indicators, subsystem ranking and savings-priority classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .balance import PlantBalance
from .cost import PlantCost
from .model import Plant


@dataclass
class PlantKPI:
    intake_m3: float
    gross_use_m3: float
    recirculation_ratio: Optional[float]      # sum(R + R_in) / gross use
    consumptive_fraction: Optional[float]     # (E + P) / intake
    discharge_fraction: Optional[float]       # W / intake
    unaccounted_fraction: Optional[float]     # L / intake
    intake_per_unit: Optional[float]          # m3 per production unit
    true_cost_per_unit: Optional[float]
    true_cost_per_m3: Optional[float]
    true_to_direct_ratio: Optional[float]


@dataclass
class RankedSubsystem:
    name: str
    intake_m3: float
    intake_share: float
    cost: float
    cost_share: float
    cost_per_m3: Optional[float]
    priority: str          # "volume" | "cost" | "both" | "low"
    note: str


def plant_kpi(plant: Plant, bal: PlantBalance, cost: PlantCost) -> PlantKPI:
    intake = bal.sum_intake
    recirc = sum(s.recirculated + s.from_other for s in plant.subsystems)
    gross = intake + recirc
    prod = plant.production_per_year or 0.0

    def ratio(a: float, b: float) -> Optional[float]:
        return a / b if b > 0 else None

    return PlantKPI(
        intake_m3=intake,
        gross_use_m3=gross,
        recirculation_ratio=ratio(recirc, gross),
        consumptive_fraction=ratio(bal.sum_evaporation + bal.sum_product, intake),
        discharge_fraction=ratio(bal.sum_discharge, intake),
        unaccounted_fraction=ratio(bal.unknown_loss, intake),
        intake_per_unit=ratio(intake, prod),
        true_cost_per_unit=ratio(cost.total, prod),
        true_cost_per_m3=cost.true_cost_per_m3_intake,
        true_to_direct_ratio=cost.true_to_direct_ratio,
    )


def rank_subsystems(cost: PlantCost, share_threshold: float = 0.20, ratio_threshold: float = 1.25) -> List[RankedSubsystem]:
    """Rank by true cost and classify where to focus.

    - 'volume': large share of intake -> water-saving priority
    - 'cost'  : cost share well above intake share (small volume, expensive water)
    - 'both'  : both of the above
    """
    out: List[RankedSubsystem] = []
    for sc in cost.subsystems:
        ws = cost.water_share.get(sc.name, 0.0)
        cs = cost.cost_share.get(sc.name, 0.0)
        big_vol = ws >= share_threshold
        costly = ws > 0 and cs / ws >= ratio_threshold and cs >= 0.05 or (ws == 0 and cs >= 0.05)
        if big_vol and costly:
            pr, note = "both", "large water user and disproportionately expensive"
        elif big_vol:
            pr, note = "volume", "large share of source water"
        elif costly:
            pr, note = "cost", "small volume but high cost per m3 (treatment, energy or disposal)"
        else:
            pr, note = "low", ""
        out.append(RankedSubsystem(sc.name, sc.intake_m3, ws, sc.total, cs, sc.per_m3_intake, pr, note))
    out.sort(key=lambda r: r.cost, reverse=True)
    return out
