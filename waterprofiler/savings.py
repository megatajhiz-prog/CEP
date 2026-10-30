"""Potential water and cost savings (report Section 2.3.1, Table 8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .estimators import InputError, STEAM_LB_PER_H_PER_BHP
from .units import LB_TO_KG


@dataclass
class SavingsResult:
    baseline_makeup: float
    new_makeup: float
    makeup_savings: float
    new_blowdown: Optional[float] = None
    blowdown_savings: Optional[float] = None
    cost_savings: Optional[float] = None   # per year, currency


def _cost(makeup_savings: float, blowdown_savings: Optional[float],
          water_unit_cost: float, discharge_unit_cost: float, treatment_unit_cost: float) -> float:
    c = makeup_savings * (water_unit_cost + treatment_unit_cost)
    if blowdown_savings is not None:
        c += blowdown_savings * discharge_unit_cost
    return c


def cooling_tower_coc(
    evaporation_m3: float,
    baseline_makeup_m3: float,
    new_cycles: float,
    water_unit_cost: float = 0.0,
    discharge_unit_cost: float = 0.0,
    treatment_unit_cost: float = 0.0,
) -> SavingsResult:
    """Raise cycles of concentration C -> C'.  M' = E / (1 - 1/C'),  dM = M0 - M'.

    Blowdown follows B' = M' - E.
    """
    if new_cycles <= 1.0:
        raise InputError("new cycles of concentration must be > 1")
    m_new = evaporation_m3 / (1.0 - 1.0 / new_cycles)
    b_base = baseline_makeup_m3 - evaporation_m3
    b_new = m_new - evaporation_m3
    dm = baseline_makeup_m3 - m_new
    db = b_base - b_new
    return SavingsResult(baseline_makeup_m3, m_new, dm, b_new, db,
                         _cost(dm, db, water_unit_cost, discharge_unit_cost, treatment_unit_cost))


def boiler_coc_and_condensate(
    baseline_makeup_m3: float,
    hours_per_year: float,
    load_fraction: float,
    new_cycles: float,
    new_condensate_return_pct: float,
    bhp: Optional[float] = None,
    rated_steam_kg_per_h: Optional[float] = None,
    baseline_blowdown_m3: Optional[float] = None,
    water_unit_cost: float = 0.0,
    discharge_unit_cost: float = 0.0,
    treatment_unit_cost: float = 0.0,
) -> SavingsResult:
    """Boiler: G' = S/(1-1/C') * L * H;  M' = (1 - R%/100) * G';  dM = M0 - M'."""
    if new_cycles <= 1.0:
        raise InputError("new cycles of concentration must be > 1")
    if not 0.0 <= new_condensate_return_pct <= 100.0:
        raise InputError("condensate return must be between 0 and 100 %")
    if rated_steam_kg_per_h is None:
        if bhp is None:
            raise InputError("give bhp or rated_steam_kg_per_h")
        rated_steam_kg_per_h = bhp * STEAM_LB_PER_H_PER_BHP * LB_TO_KG
    g_new = rated_steam_kg_per_h / (1.0 - 1.0 / new_cycles) * load_fraction * hours_per_year * 1e-3
    m_new = (1.0 - new_condensate_return_pct / 100.0) * g_new
    dm = baseline_makeup_m3 - m_new
    b_new = g_new / new_cycles
    db = (baseline_blowdown_m3 - b_new) if baseline_blowdown_m3 is not None else None
    return SavingsResult(baseline_makeup_m3, m_new, dm, b_new, db,
                         _cost(dm, db, water_unit_cost, discharge_unit_cost, treatment_unit_cost))


def leak_repair(leak_m3_per_h: float, hours_per_year: float, fraction_fixed: float = 1.0,
                water_unit_cost: float = 0.0, discharge_unit_cost: float = 0.0,
                to_drain: bool = True) -> SavingsResult:
    """Simple leak / open-flow elimination: saved = rate * hours * fraction."""
    saved = leak_m3_per_h * hours_per_year * fraction_fixed
    cost = saved * water_unit_cost + (saved * discharge_unit_cost if to_drain else 0.0)
    return SavingsResult(saved, 0.0, saved, cost_savings=cost)


def simple_payback_years(capex: float, annual_savings: float) -> Optional[float]:
    return capex / annual_savings if annual_savings > 0 else None
