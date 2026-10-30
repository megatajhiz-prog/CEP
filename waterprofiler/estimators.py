"""Bottom-up subsystem water-use estimators (report Tables 1-5).

All volumes are returned in m3/year. Each function returns a ``FlowEstimate``
whose fields map to the quantities used by the water balance:

    gross      G  gross water use (intake + recirculation)
    makeup     M  fresh water intake
    recirc     R  water recirculated within the subsystem
    evap       E  evaporation / consumptive loss
    blowdown   B  blowdown / wastewater
    product    P  water incorporated into product
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from .units import GAL_TO_M3, LB_TO_KG, HP_TO_KW, c_to_f_delta, SQFT_TO_M2

STEAM_LB_PER_H_PER_BHP = 34.5       # standard definition of one boiler horsepower
LITRE_TO_M3 = 1e-3


class InputError(ValueError):
    """Raised for physically impossible or incomplete inputs."""


@dataclass
class FlowEstimate:
    gross: float = 0.0
    makeup: float = 0.0
    recirc: float = 0.0
    evap: float = 0.0
    blowdown: float = 0.0
    product: float = 0.0
    cycles: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _check_fraction(name: str, v: float) -> None:
    if not 0.0 <= v <= 1.0:
        raise InputError(f"{name} must be between 0 and 1, got {v}")


def _check_positive(name: str, v: float) -> None:
    if v < 0:
        raise InputError(f"{name} must be >= 0, got {v}")


def _cycles(numerator: float, denominator: float, label: str) -> float:
    if denominator <= 0 or numerator <= 0:
        raise InputError(f"{label}: conductivities must be > 0")
    c = numerator / denominator
    if c <= 1.0:
        raise InputError(
            f"{label}: cycles of concentration must be > 1 (got {c:.3f}); "
            "check that blowdown conductivity exceeds the reference conductivity"
        )
    return c


# ---------------------------------------------------------------- Table 1
def process_water(
    units_per_year: float,
    water_use_per_unit_m3: float,
    recycled_fraction: float = 0.0,
    consumed_in_product_per_unit_m3: float = 0.0,
) -> FlowEstimate:
    """Process subsystem. G = N*g, R = G*r, M = G-R, P = N*p."""
    _check_positive("units_per_year", units_per_year)
    _check_positive("water_use_per_unit_m3", water_use_per_unit_m3)
    _check_fraction("recycled_fraction", recycled_fraction)
    g = units_per_year * water_use_per_unit_m3
    r = g * recycled_fraction
    p = units_per_year * consumed_in_product_per_unit_m3
    return FlowEstimate(gross=g, makeup=g - r, recirc=r, product=p)


# ---------------------------------------------------------------- Table 2
def cooling_tower_water(
    hours_per_year: float,
    tonnage: float,
    load_fraction: float,
    delta_t_c: float,
    makeup_conductivity: float,
    blowdown_conductivity: float,
    evaporation_pct_per_10f: float = 0.85,
    gpm_per_ton: float = 3.0,
) -> FlowEstimate:
    """Evaporative cooling tower.

    G = gpm_per_ton * tons * load * hours * 60   (rule of thumb, 3 gpm/ton)
    E = G * (e/100) * dT_F / 10
    C = Bc / Mc
    M = E / (1 - 1/C)
    B = M - E
    R = G - M
    Drift is ignored, as in the report.
    """
    _check_positive("hours_per_year", hours_per_year)
    _check_positive("tonnage", tonnage)
    _check_fraction("load_fraction", load_fraction)
    _check_positive("delta_t_c", delta_t_c)
    c = _cycles(blowdown_conductivity, makeup_conductivity, "Cooling tower")
    g_gal = gpm_per_ton * tonnage * load_fraction * hours_per_year * 60.0
    g = g_gal * GAL_TO_M3
    e = g * (evaporation_pct_per_10f / 100.0) * c_to_f_delta(delta_t_c) / 10.0
    m = e / (1.0 - 1.0 / c)
    b = m - e
    return FlowEstimate(gross=g, makeup=m, recirc=g - m, evap=e, blowdown=b, cycles=c)


def once_through_cooling(hours_per_year: float, flow_m3_per_h: float) -> FlowEstimate:
    """Intake = gross use = discharge = F*H (no recirculation, no loss)."""
    _check_positive("hours_per_year", hours_per_year)
    _check_positive("flow_m3_per_h", flow_m3_per_h)
    v = flow_m3_per_h * hours_per_year
    return FlowEstimate(gross=v, makeup=v, blowdown=v)


# ---------------------------------------------------------------- Table 3
def boiler_water(
    hours_per_year: float,
    load_fraction: float,
    feedwater_conductivity: float,
    makeup_conductivity: float,
    blowdown_conductivity: float,
    bhp: float | None = None,
    rated_steam_kg_per_h: float | None = None,
    steam_lb_per_h_per_bhp: float = STEAM_LB_PER_H_PER_BHP,
) -> FlowEstimate:
    """Steam boiler.

    C = Bc / Fc
    G = [S / (1 - 1/C)] * L * H          (S = rated steam, converted lb->m3)
    M = (Fc / Mc) * G
    B = G / C
    E = M - B        (steam losses; the report's definition)
    R = G - M        (condensate return)

    Give either ``bhp`` (the report's input) or ``rated_steam_kg_per_h``.
    1 kg of water is taken as 1e-3 m3.
    """
    _check_positive("hours_per_year", hours_per_year)
    _check_fraction("load_fraction", load_fraction)
    if rated_steam_kg_per_h is None:
        if bhp is None:
            raise InputError("Boiler: give bhp or rated_steam_kg_per_h")
        rated_steam_kg_per_h = bhp * steam_lb_per_h_per_bhp * LB_TO_KG
    c = _cycles(blowdown_conductivity, feedwater_conductivity, "Boiler")
    if makeup_conductivity <= 0 or feedwater_conductivity <= 0:
        raise InputError("Boiler: conductivities must be > 0")
    makeup_share = feedwater_conductivity / makeup_conductivity
    if makeup_share > 1.0:
        raise InputError(
            "Boiler: feedwater conductivity cannot exceed makeup conductivity "
            "(makeup share of feedwater would exceed 100 %)"
        )
    g = rated_steam_kg_per_h / (1.0 - 1.0 / c) * load_fraction * hours_per_year * 1e-3
    m = makeup_share * g
    b = g / c
    return FlowEstimate(gross=g, makeup=m, recirc=g - m, evap=m - b, blowdown=b, cycles=c)


# ---------------------------------------------------------------- Table 4
def sanitary_water(employees: float, days_per_year: float, litres_per_employee_day: float) -> FlowEstimate:
    """Kitchen and restrooms. Typical: 10 gal (38 L) toilets only .. 35 gal (132 L) full service."""
    g = employees * days_per_year * litres_per_employee_day * LITRE_TO_M3
    return FlowEstimate(gross=g, makeup=g, blowdown=g)


# ---------------------------------------------------------------- Table 5
GAL_PER_SQFT_PER_INCH = 0.623


def irrigation_water(area_m2: float, depth_mm_per_year: float) -> FlowEstimate:
    """Landscaping. G = area * depth; all of it is consumptive (E = G).

    The report prints an extra 'D' term in this formula; it is a typo.
    """
    _check_positive("area_m2", area_m2)
    _check_positive("depth_mm_per_year", depth_mm_per_year)
    g = area_m2 * depth_mm_per_year * 1e-3
    return FlowEstimate(gross=g, makeup=g, evap=g)


def irrigation_water_us(area_sqft: float, depth_inch: float) -> FlowEstimate:
    """US-unit form of the same formula: 0.623 gal per sq ft per inch."""
    g = GAL_PER_SQFT_PER_INCH * depth_inch * area_sqft * GAL_TO_M3
    return FlowEstimate(gross=g, makeup=g, evap=g)
