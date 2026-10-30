"""Turn estimator results into subsystem flow fields (shared by the GUI and tests)."""

from __future__ import annotations

from typing import Dict, Optional

from . import estimators as est
from .estimators import FlowEstimate
from .model import Subsystem

# parameter names accepted per subsystem kind
PARAMS: Dict[str, tuple] = {
    "process": ("units", "g", "r", "p"),
    "cooling_tower": ("hours", "load", "tons", "dt", "mc", "bc"),
    "boiler": ("hours", "load", "bhp", "fc", "mc", "bc"),
    "sanitary": ("employees", "days", "lpd"),
    "irrigation": ("area", "depth"),
}


def estimate(kind: str, p: Dict[str, float]) -> FlowEstimate:
    if kind == "process":
        return est.process_water(p["units"], p["g"], p.get("r", 0.0), p.get("p", 0.0))
    if kind == "cooling_tower":
        return est.cooling_tower_water(p["hours"], p["tons"], p["load"], p["dt"], p["mc"], p["bc"])
    if kind == "boiler":
        return est.boiler_water(p["hours"], p["load"], p["fc"], p["mc"], p["bc"], bhp=p["bhp"])
    if kind == "sanitary":
        return est.sanitary_water(p["employees"], p["days"], p["lpd"])
    if kind == "irrigation":
        return est.irrigation_water(p["area"], p["depth"])
    raise est.InputError(f"no estimator for subsystem type '{kind}'")


def apply_estimate(s: Subsystem, kind: str, p: Dict[str, float], source: str, outlet: Optional[str]) -> FlowEstimate:
    """Overwrite the subsystem's flow fields with the estimate and remember the parameters."""
    r = estimate(kind, p)
    s.kind = kind
    s.intake = {source: r.makeup} if r.makeup > 0 else {}
    s.recirculated = r.recirc
    s.product = r.product
    s.evaporation = r.evap
    if kind == "process":
        discharge = r.makeup - r.product
    else:
        discharge = r.blowdown
    s.discharge = {outlet: discharge} if (outlet and discharge > 0) else {}
    s.params = dict(p)
    return r
