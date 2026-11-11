"""Sensitivity and Monte-Carlo risk analysis of the economics of water-saving measures.

Sensitivity (one input at a time around the base case, ``sensitivity_table``):
  * tornado / table: NPV, LCOW, IRR and payback with every input at -delta and +delta (relative; percentage points for the
    escalation and degradation rates);
  * spider: NPV against a common range of relative changes of each input;
  * break-even: the value of an input at which NPV = 0 (bisection);
  * two-way grid: NPV against the saved volume and the water value.

Risk (Monte Carlo, ``simulate``): every uncertain input gets a triangular distribution (lowest, base = most likely, highest);
the cash flows are evaluated for thousands of draws at once (numpy, the same formulas as ``economics.evaluate``). Reported:
mean, standard deviation, percentiles, probability of a negative NPV, value at risk (5 %), expected shortfall, histogram,
cumulative curve and the rank correlation of every input (or, for the whole plan, of every measure) with the NPV.
For the whole plan every measure is drawn independently, except the water value and the discount rate, which are common to
all measures (one tariff, one cost of capital): their draws are shared.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import economics as EC
from .model import Plant

# ----------------------------------------------------------------------------------------------- sensitivity
REL_VARS = ("saving_m3", "price", "capex", "opex", "other_benefit", "salvage")
PP_VARS = ("rate_pct", "price_esc_pct", "opex_esc_pct", "degradation_pct")          # changed in percentage points
SENS_VARS = ("saving_m3", "price", "capex", "opex", "rate_pct", "life", "price_esc_pct", "degradation_pct")
PP_STEP = 2.0                                                                       # +- points when delta = 20 %


@dataclass
class SensRow:
    var: str
    low_value: float
    high_value: float
    low: EC.EconResult
    high: EC.EconResult

    @property
    def swing(self) -> float:
        return abs(self.high.npv - self.low.npv)


def _shift(inp: EC.EconInputs, var: str, sign: int, delta: float) -> EC.EconInputs:
    base = getattr(inp, var)
    if var == "life":
        v = max(1, int(round(base * (1 + sign * delta))))
    elif var in PP_VARS:
        v = base + sign * PP_STEP * delta / 0.2
        if var == "degradation_pct":
            v = min(max(v, 0.0), 99.0)
    else:
        v = max(0.0, base * (1 + sign * delta))
    return dataclasses.replace(inp, **{var: v})


def sensitivity_table(inp: EC.EconInputs, delta: float = 0.2) -> List[SensRow]:
    rows = []
    for var in SENS_VARS:
        lo, hi = _shift(inp, var, -1, delta), _shift(inp, var, 1, delta)
        rows.append(SensRow(var, getattr(lo, var), getattr(hi, var), EC.evaluate(lo), EC.evaluate(hi)))
    rows.sort(key=lambda r: -r.swing)
    return rows


def spider(inp: EC.EconInputs, span: float = 0.3, steps: int = 6) -> Tuple[List[float], Dict[str, List[float]]]:
    """(relative changes, {variable: NPV at each change}) for the variables with a relative scale and the rate."""
    xs = [-span + 2 * span * k / steps for k in range(steps + 1)]
    out: Dict[str, List[float]] = {}
    for var in ("saving_m3", "price", "capex", "opex", "rate_pct"):
        ys = []
        for x in xs:
            v = getattr(inp, var) * (1 + x)
            ys.append(EC.evaluate(dataclasses.replace(inp, **{var: max(0.0, v)})).npv)
        out[var] = ys
    return xs, out


def break_even(inp: EC.EconInputs) -> Dict[str, Optional[float]]:
    """Relative change (fraction) of each input that brings the NPV to zero; None when no change in [-100 %, +1000 %] does."""
    res: Dict[str, Optional[float]] = {}
    for var in ("saving_m3", "price", "capex", "opex", "rate_pct"):
        base = getattr(inp, var)
        if base <= 0:
            res[var] = None
            continue

        def f(x: float) -> float:
            return EC.evaluate(dataclasses.replace(inp, **{var: base * (1 + x)})).npv

        lo, hi = (-0.999, 10.0)
        flo, fhi = f(lo), f(hi)
        if flo == 0:
            res[var] = lo
        elif fhi == 0:
            res[var] = hi
        elif flo * fhi > 0:
            res[var] = None
        else:
            for _ in range(100):
                mid = (lo + hi) / 2
                fm = f(mid)
                if flo * fm <= 0:
                    hi = mid
                else:
                    lo, flo = mid, fm
                if hi - lo < 1e-10:
                    break
            res[var] = (lo + hi) / 2
    return res


def two_way(inp: EC.EconInputs, span: float = 0.3, steps: int = 6) -> Tuple[List[float], List[float], List[List[float]]]:
    """NPV grid: rows = changes of the saved volume, columns = changes of the water value."""
    xs = [-span + 2 * span * k / steps for k in range(steps + 1)]
    grid = [[EC.evaluate(dataclasses.replace(inp, saving_m3=inp.saving_m3 * (1 + a), price=inp.price * (1 + b))).npv
             for b in xs] for a in xs]
    return xs, xs, grid


# ----------------------------------------------------------------------------------------------- Monte Carlo
MC_VARS = ("saving_m3", "price", "capex", "opex", "other_benefit", "rate_pct", "price_esc_pct", "opex_esc_pct", "degradation_pct")
DEFAULT_RANGES: Dict[str, Tuple[float, float]] = {      # relative (%) for REL_VARS, percentage points for PP_VARS
    "saving_m3": (-25.0, 10.0), "price": (-15.0, 25.0), "capex": (-10.0, 30.0), "opex": (-15.0, 25.0),
    "other_benefit": (-20.0, 20.0), "rate_pct": (-2.0, 3.0), "price_esc_pct": (-2.0, 3.0),
    "opex_esc_pct": (-1.0, 3.0), "degradation_pct": (0.0, 3.0),
}
MAX_RUNS = 50000
SHARED = ("price", "rate_pct")


@dataclass
class RiskSettings:
    runs: int = 5000
    seed: int = 1
    ranges: Dict[str, Tuple[float, float]] = field(default_factory=lambda: dict(DEFAULT_RANGES))
    scope: str = "plan"            # "plan" or "item:<index>"

    @staticmethod
    def of(plant: Plant) -> "RiskSettings":
        d = getattr(plant, "risk", None) or {}
        rg = dict(DEFAULT_RANGES)
        for k, v in (d.get("ranges") or {}).items():
            if k in rg:
                try:
                    lo, hi = float(v[0]), float(v[1])
                    rg[k] = (min(lo, hi), max(lo, hi))
                except (TypeError, ValueError, IndexError):
                    pass
        try:
            runs = int(d.get("runs", 5000))
        except (TypeError, ValueError):
            runs = 5000
        try:
            seed = int(d.get("seed", 1))
        except (TypeError, ValueError):
            seed = 1
        return RiskSettings(min(max(runs, 100), MAX_RUNS), seed, rg, str(d.get("scope", "plan")))

    def store(self, plant: Plant) -> None:
        plant.risk = {"runs": self.runs, "seed": self.seed, "ranges": {k: list(v) for k, v in self.ranges.items()},
                      "scope": self.scope}


def _tri_ppf(u: np.ndarray, lo: float, mode: float, hi: float) -> np.ndarray:
    if hi - lo <= 1e-15:
        return np.full_like(u, mode)
    c = (mode - lo) / (hi - lo)
    left = lo + np.sqrt(u * (hi - lo) * (mode - lo))
    right = hi - np.sqrt((1 - u) * (hi - lo) * (hi - mode))
    return np.where(u < c, left, right)


def draw(inp: EC.EconInputs, ranges: Dict[str, Tuple[float, float]], u: np.ndarray) -> Dict[str, np.ndarray]:
    """Samples of every uncertain input from uniforms ``u`` (shape runs x len(MC_VARS)); base value is the mode."""
    out: Dict[str, np.ndarray] = {}
    for k, var in enumerate(MC_VARS):
        base = float(getattr(inp, var))
        lo_r, hi_r = ranges.get(var, (0.0, 0.0))
        if var in REL_VARS:
            lo, hi = base * (1 + lo_r / 100.0), base * (1 + hi_r / 100.0)
            lo, hi = max(0.0, lo), max(lo, hi, 0.0)
        else:
            lo, hi = base + lo_r, base + hi_r
            if var == "degradation_pct":
                lo, hi = min(max(lo, 0.0), 99.0), min(max(hi, 0.0), 99.0)
        lo, hi = min(lo, base), max(hi, base)
        out[var] = _tri_ppf(u[:, k], lo, base, hi)
    return out


def _vec(inp: EC.EconInputs, s: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Vectorised twin of ``economics.evaluate``: NPV, LCC, LCOW, B/C ratio and the net-cash-flow matrix."""
    n = int(inp.life)
    t = np.arange(1, n + 1)
    g, e, d, r = (s["price_esc_pct"][:, None] / 100.0, s["opex_esc_pct"][:, None] / 100.0,
                  s["degradation_pct"][:, None] / 100.0, s["rate_pct"][:, None] / 100.0)
    vol = s["saving_m3"][:, None] * (1.0 - d) ** (t - 1)
    ben = (vol * s["price"][:, None] + s["other_benefit"][:, None]) * (1.0 + g) ** (t - 1)
    ben[:, -1] += inp.salvage
    cost = s["opex"][:, None] * (1.0 + e) ** (t - 1)
    if inp.repl_year:
        cost[:, int(inp.repl_year) - 1] += inp.repl_cost
    disc = (1.0 + r) ** (-t)
    capex = s["capex"]
    pv_b = (ben * disc).sum(1)
    pv_c = capex + (cost * disc).sum(1)
    pv_v = (vol * disc).sum(1)
    lcc = pv_c - inp.salvage * disc[:, -1]
    with np.errstate(divide="ignore", invalid="ignore"):
        lcow = np.where(pv_v > 0, lcc / pv_v, np.nan)
        bcr = np.where(pv_c > 0, pv_b / pv_c, np.nan)
    flows = np.concatenate([-capex[:, None], ben - cost], axis=1)
    return {"npv": pv_b - pv_c, "lcc": lcc, "lcow": lcow, "bcr": bcr, "flows": flows}


def irr_vec(flows: np.ndarray, lo: float = -0.9, hi: float = 20.0) -> np.ndarray:
    """IRR (fraction) of every row by bisection; NaN when the flows do not change sign or no root is bracketed."""
    t = np.arange(flows.shape[1])

    def f(rate: np.ndarray) -> np.ndarray:
        return (flows * (1.0 + rate[:, None]) ** (-t)).sum(1)

    a = np.full(flows.shape[0], lo)
    b = np.full(flows.shape[0], hi)
    fa, fb = f(a), f(b)
    ok = (fa > 0) & (fb < 0)
    for _ in range(80):
        m = (a + b) / 2
        fm = f(m)
        up = fm > 0
        a = np.where(up, m, a)
        b = np.where(up, b, m)
    return np.where(ok, (a + b) / 2, np.nan)


@dataclass
class Stats:
    mean: float
    sd: float
    p5: float
    p50: float
    p95: float
    minimum: float
    maximum: float


def _stats(x: np.ndarray) -> Optional[Stats]:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return None
    return Stats(float(x.mean()), float(x.std(ddof=1)) if x.size > 1 else 0.0, float(np.percentile(x, 5)),
                 float(np.percentile(x, 50)), float(np.percentile(x, 95)), float(x.min()), float(x.max()))


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if np.ptp(x) <= 1e-15 or np.ptp(y) <= 1e-15:
        return 0.0
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx, ry)[0, 1])


@dataclass
class RiskResult:
    runs: int
    scope: str
    npv: np.ndarray
    base_npv: float
    npv_stats: Stats
    lcow_stats: Optional[Stats]
    irr_stats: Optional[Stats]
    lcc_stats: Optional[Stats]
    p_loss: float                  # probability NPV < 0
    p_bcr_below_1: float
    var5: float                    # value at risk: loss at the 5 % quantile (>= 0), 0 if the 5 % quantile is a gain
    shortfall: float               # mean NPV of the worst 5 % of the draws
    hist_counts: List[int]
    hist_edges: List[float]
    cdf_x: List[float]             # NPV at the 0 %, 1 % ... 100 % quantiles
    drivers: List[Tuple[str, float]]    # (variable key or "item:<index>", Spearman rho with the NPV), largest |rho| first
    items: List[int] = field(default_factory=list)     # plan indices simulated


def _summarise(npv: np.ndarray, base_npv: float, lcow, irr, lcc, bcr, drivers, runs, scope, items, rate_pct) -> RiskResult:
    q5 = float(np.percentile(npv, 5))
    tail = npv[npv <= q5]
    counts, edges = np.histogram(npv, bins=30)
    return RiskResult(
        runs=runs, scope=scope, npv=npv, base_npv=base_npv, npv_stats=_stats(npv), lcow_stats=_stats(lcow) if lcow is not None else None,
        irr_stats=_stats(irr * 100.0) if irr is not None else None, lcc_stats=_stats(lcc) if lcc is not None else None,
        p_loss=float((npv < 0).mean()), p_bcr_below_1=float((bcr < 1).mean()) if bcr is not None else float((npv < 0).mean()),
        var5=max(0.0, -q5), shortfall=float(tail.mean()) if tail.size else q5,
        hist_counts=[int(c) for c in counts], hist_edges=[float(e) for e in edges],
        cdf_x=[float(v) for v in np.percentile(npv, np.arange(0, 101))],
        drivers=sorted(drivers, key=lambda d: -abs(d[1])), items=items)


def simulate_item(inp: EC.EconInputs, st: RiskSettings, index: int = 0) -> RiskResult:
    rng = np.random.default_rng(st.seed)
    u = rng.random((st.runs, len(MC_VARS)))
    s = draw(inp, st.ranges, u)
    v = _vec(inp, s)
    irr = irr_vec(v["flows"])
    drivers = [(var, _spearman(s[var], v["npv"])) for var in MC_VARS]
    return _summarise(v["npv"], EC.evaluate(inp).npv, v["lcow"], irr, v["lcc"], v["bcr"], drivers, st.runs, f"item:{index}", [index],
                      inp.rate_pct)


def simulate_plan(plant: Plant, st: RiskSettings) -> Optional[RiskResult]:
    """All measures of the plan together; price and discount rate are drawn once and shared."""
    pairs = [(i, ie.result.inputs) for i, ie in enumerate(EC.evaluate_plan_economics(plant)) if ie.result is not None]
    if not pairs:
        return None
    rng = np.random.default_rng(st.seed)
    shared = rng.random((st.runs, len(MC_VARS)))
    total = np.zeros(st.runs)
    contrib: Dict[int, np.ndarray] = {}
    base = 0.0
    for i, inp in pairs:
        own = rng.random((st.runs, len(MC_VARS)))
        u = own.copy()
        for k, var in enumerate(MC_VARS):
            if var in SHARED:
                u[:, k] = shared[:, k]
        npv = _vec(inp, draw(inp, st.ranges, u))["npv"]
        contrib[i] = npv
        total += npv
        base += EC.evaluate(inp).npv
    drivers = [(f"item:{i}", _spearman(c, total)) for i, c in contrib.items()]
    return _summarise(total, base, None, None, None, None, drivers, st.runs, "plan", [i for i, _ in pairs], 0.0)


def simulate(plant: Plant, st: Optional[RiskSettings] = None) -> Optional[RiskResult]:
    st = st or RiskSettings.of(plant)
    if st.scope.startswith("item:"):
        try:
            idx = int(st.scope.split(":")[1])
            ie = EC.evaluate_plan_economics(plant)[idx]
        except (ValueError, IndexError):
            return simulate_plan(plant, st)
        return simulate_item(ie.result.inputs, st, idx) if ie.result is not None else None
    return simulate_plan(plant, st)
