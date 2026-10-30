"""One-call analysis of a plant: balance + cost + KPIs + ranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .balance import PlantBalance, plant_balance
from .cost import PlantCost, plant_cost
from .kpi import PlantKPI, RankedSubsystem, plant_kpi, rank_subsystems
from .model import Plant


@dataclass
class Analysis:
    plant: Plant
    balance: PlantBalance
    cost: PlantCost
    kpi: PlantKPI
    ranking: List[RankedSubsystem]

    @property
    def warnings(self) -> List[str]:
        return list(self.balance.warnings) + list(self.cost.warnings)


def analyse(plant: Plant) -> Analysis:
    b = plant_balance(plant)
    c = plant_cost(plant)
    return Analysis(plant, b, c, plant_kpi(plant, b, c), rank_subsystems(c))
