"""Unit conversion constants and helpers. Internal units: m3/year, kWh, degC."""

GAL_TO_M3 = 0.003785411784          # US gallon -> m3
MGAL_TO_M3 = 1e6 * GAL_TO_M3        # million US gallons -> m3
LB_TO_KG = 0.45359237
HP_TO_KW = 0.746                    # electrical horsepower, as used in the report
REFRIG_TON_TO_KW = 3.516852842      # 1 ton of refrigeration
SQFT_TO_M2 = 0.09290304
INCH_TO_M = 0.0254
MMBTU_TO_KWH = 293.07107

# Specific heat and density of water used in the heat-in-wastewater term.
CP_WATER_KJ_PER_KG_K = 4.186
RHO_WATER_KG_PER_M3 = 1000.0
KJ_PER_KWH = 3600.0


def f_to_c_delta(delta_f: float) -> float:
    return delta_f / 1.8


def c_to_f_delta(delta_c: float) -> float:
    return delta_c * 1.8


def kw_to_tons(kw: float) -> float:
    return kw / REFRIG_TON_TO_KW


def tons_to_kw(tons: float) -> float:
    return tons * REFRIG_TON_TO_KW


def gpm_to_m3_per_h(gpm: float) -> float:
    return gpm * GAL_TO_M3 * 60.0


def m3h_to_gpm(m3h: float) -> float:
    return m3h / (GAL_TO_M3 * 60.0)
