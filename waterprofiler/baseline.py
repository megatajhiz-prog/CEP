"""Regression baseline of plant water intake (monthly) and the savings measured against it.

    W_m = b0 + b1 * x1_m + b2 * x2_m + ...          (W = intake of month m, x = production, operating hours, air temperature, ...)

* Drivers are the monthly series the plant already has (production of every product and, when they share one unit, their sum; operating hours, air temperature, employees). Every subset of up to three drivers is fitted by ordinary least squares;
  the model with the highest adjusted R2 whose coefficients are ALL significant (p < 0.01) is chosen; if there is none the
  baseline is the mean (intercept only) and says so.
* Quality statistics follow the usual M&V practice: R2, adjusted R2, CV(RMSE), t and p of every coefficient.
* The baseline can be trained on the first months and applied to the latest ``n_report`` months: expected intake, actual intake,
  saving = expected - actual, the CUSUM of the savings, and a 95 % prediction uncertainty of the total
  (sum of s^2 (1 + x'(X'X)^-1 x) over the months, errors independent).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import timeseries as TS
from .model import Plant

MIN_OBS = 8                      # months needed before a regression is attempted
MAX_DRIVERS = 3
P_LIMIT = 0.01
MIN_GAIN = 0.01                  # a further driver must raise the adjusted R2 by at least this much
Z95 = 1.96


# ------------------------------------------------------------------------------------------------ statistics
def _betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c; c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c; c = c if abs(c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-12:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1 - x) / b


def t_pvalue(t: float, dof: int) -> float:
    """Two-sided p-value of a Student t statistic."""
    if dof <= 0 or not math.isfinite(t):
        return 1.0
    return _betainc(dof / 2.0, 0.5, dof / (dof + t * t))


# ---------------------------------------------------------------------------------------------------- model
@dataclass
class Driver:
    key: str
    fa: str
    en: str

    def label(self, lang: str) -> str:
        return self.fa if lang == "fa" else self.en


@dataclass
class BaselineModel:
    drivers: List[Driver]
    coef: List[float]                  # intercept first
    se: List[float]
    t: List[float]
    p: List[float]
    n: int
    r2: float
    adj_r2: float
    cv_rmse: float                     # %
    s: float                           # residual standard deviation, m3
    xtx_inv: List[List[float]] = field(default_factory=list)
    intercept_only: bool = False

    @property
    def dof(self) -> int:
        return self.n - len(self.coef)

    @property
    def good(self) -> bool:
        """The usual screening of a usable baseline: R2 >= 0.75 and CV(RMSE) <= 25 % (monthly data)."""
        return not self.intercept_only and self.r2 >= 0.75 and self.cv_rmse <= 25.0

    def predict(self, x: Sequence[float]) -> float:
        return self.coef[0] + sum(c * v for c, v in zip(self.coef[1:], x))

    def predict_var(self, x: Sequence[float]) -> float:
        v = np.array([1.0] + list(x))
        q = float(v @ np.array(self.xtx_inv) @ v) if self.xtx_inv else 1.0 / max(self.n, 1)
        return self.s ** 2 * (1.0 + q)


def fit(y: Sequence[float], X: Sequence[Sequence[float]], drivers: Sequence[Driver]) -> Optional[BaselineModel]:
    """OLS of y on the columns X (one list per driver); None if the system is singular or has no degrees of freedom."""
    n = len(y)
    k = len(drivers) + 1
    if n - k < 1:
        return None
    A = np.column_stack([np.ones(n)] + [np.asarray(c, float) for c in X]) if X else np.ones((n, 1))
    yy = np.asarray(y, float)
    try:
        xtx = A.T @ A
        if np.linalg.matrix_rank(xtx) < k:
            return None
        inv = np.linalg.inv(xtx)
    except np.linalg.LinAlgError:
        return None
    beta = inv @ A.T @ yy
    res = yy - A @ beta
    sse = float(res @ res)
    sst = float(((yy - yy.mean()) ** 2).sum())
    dof = n - k
    s2 = sse / dof
    se = np.sqrt(np.maximum(np.diag(inv) * s2, 0.0))
    tt = [float(b / e) if e > 0 else (math.inf if b else 0.0) for b, e in zip(beta, se)]
    p = [t_pvalue(v, dof) for v in tt]
    r2 = 1.0 - sse / sst if sst > 0 else 1.0
    adj = 1.0 - (1.0 - r2) * (n - 1) / dof if sst > 0 else 1.0
    mean = float(yy.mean())
    cv = 100.0 * math.sqrt(s2) / mean if mean else 0.0
    return BaselineModel(list(drivers), [float(b) for b in beta], [float(e) for e in se], tt, p, n, r2, adj, cv,
                         math.sqrt(s2), inv.tolist(), intercept_only=not drivers)


def select(y: Sequence[float], cols: Dict[str, List[float]], drivers: Dict[str, Driver],
           max_drivers: int = MAX_DRIVERS) -> Tuple[BaselineModel, List[str]]:
    """Best subset by adjusted R2 among models whose every coefficient has p < P_LIMIT (the intercept is exempt); a model with more drivers
    must beat a simpler one by MIN_GAIN of adjusted R2."""
    keys = [k for k in cols if np.ptp(cols[k]) > 0]
    best: Optional[BaselineModel] = None
    for r in range(1, min(max_drivers, len(keys)) + 1):
        for sub in combinations(keys, r):
            m = fit(y, [cols[k] for k in sub], [drivers[k] for k in sub])
            if m is None or any(p > P_LIMIT for p in m.p[1:]):
                continue
            if best is None:
                best = m
            elif len(m.drivers) > len(best.drivers):
                if m.adj_r2 > best.adj_r2 + MIN_GAIN:
                    best = m
            elif m.adj_r2 > best.adj_r2 + 1e-9:
                best = m
    warnings: List[str] = []
    if best is None:
        best = fit(y, [], [])
        warnings.append("bl_no_driver")
    return best, warnings


# ---------------------------------------------------------------------------------------------------- data
@dataclass
class Dataset:
    labels: List[str]
    y: List[float]
    cols: Dict[str, List[float]]
    drivers: Dict[str, Driver]
    warnings: List[str] = field(default_factory=list)


def _driver_series(plant: Plant, sl) -> Tuple[Dict[str, List[Optional[float]]], Dict[str, Driver]]:
    cols: Dict[str, List[Optional[float]]] = {}
    drv: Dict[str, Driver] = {}
    prods = plant.site.products
    if prods and len({p.unit or plant.production_unit for p in prods}) <= 1 and len(prods) > 1:
        tot = TS.total_production_slices(plant, sl)             # one unit: the sum is a candidate as well
        if any(v is not None for v in tot):
            cols["production"], drv["production"] = tot, Driver("production", "تولید کل", "Total production")
    for p in prods:                                             # every product is also a candidate: never only a sum
        v = TS.slice_values(plant, f"production:{p.name}", sl)
        if any(x is not None for x in v):
            cols[f"production:{p.name}"] = v
            drv[f"production:{p.name}"] = Driver(f"production:{p.name}", f"تولید «{p.name}»", f"Production of {p.name}")
    for key, fa, en in (("site:operating_hours", "ساعات کار", "Operating hours"), ("env:temp", "دمای هوا", "Air temperature"),
                        ("site:employees", "پرسنل", "Employees")):
        v = TS.slice_values(plant, key, sl)
        if any(x is not None for x in v):
            cols[key], drv[key] = v, Driver(key, fa, en)
    return cols, drv


def dataset(plant: Plant) -> Dataset:
    """Months (complete ones) in which the intake and every chosen driver have a value."""
    sl = TS.monthly_slices(plant)
    y = TS.total_intake_slices(plant, sl)
    cols, drv = _driver_series(plant, sl)
    ok_cols = {k: v for k, v in cols.items() if sum(x is not None for x in v) >= MIN_OBS}
    idx = [i for i, v in enumerate(y) if v is not None and all(c[i] is not None for c in ok_cols.values())]
    warn: List[str] = []
    if len(idx) < MIN_OBS and ok_cols:                  # a sparse driver must not throw away the intake months
        ok_cols = {}
        idx = [i for i, v in enumerate(y) if v is not None]
        warn.append("bl_sparse_drivers")
    return Dataset([sl[i].label for i in idx], [float(y[i]) for i in idx],
                   {k: [float(c[i]) for i in idx] for k, c in ok_cols.items()}, {k: drv[k] for k in ok_cols}, warn)


# ------------------------------------------------------------------------------------------------ result
@dataclass
class Month:
    label: str
    actual: float
    expected: float
    saving: float              # expected - actual (positive = less water than the baseline predicts)
    cusum: float
    in_report: bool


@dataclass
class BaselineResult:
    model: Optional[BaselineModel]
    months: List[Month]
    n_train: int
    n_report: int
    saving_total: float = 0.0          # over the report months
    saving_pct: float = 0.0
    saving_sigma: float = 0.0          # 95 % half-width of the total
    significant: bool = False
    warnings: List[str] = field(default_factory=list)


def evaluate(plant: Plant, n_report: int = 0) -> BaselineResult:
    ds = dataset(plant)
    n = len(ds.y)
    warnings = list(ds.warnings)
    n_report = max(0, min(n_report, n - MIN_OBS)) if n_report else 0
    if n < MIN_OBS:
        return BaselineResult(None, [], n, 0, warnings=warnings + ["bl_too_few"])
    nt = n - n_report
    model, w = select(ds.y[:nt], {k: c[:nt] for k, c in ds.cols.items()}, ds.drivers)
    warnings += w
    if model is None:
        return BaselineResult(None, [], nt, n_report, warnings=warnings + ["bl_too_few"])
    if not model.intercept_only and not model.good:
        warnings.append("bl_weak")
    months: List[Month] = []
    cum = 0.0
    var = 0.0
    sav = act = 0.0
    keys = [d.key for d in model.drivers]
    for i in range(n):
        x = [ds.cols[k][i] for k in keys]
        e = model.predict(x)
        s = e - ds.y[i]
        cum += s
        rep = i >= nt
        if rep:
            var += model.predict_var(x)
            sav += s
            act += ds.y[i]
        months.append(Month(ds.labels[i], ds.y[i], e, s, cum, rep))
    half = Z95 * math.sqrt(var)
    exp_total = sav + act
    return BaselineResult(model, months, nt, n_report, sav, 100.0 * sav / exp_total if exp_total else 0.0, half,
                          n_report > 0 and half > 0 and abs(sav) > half, warnings)
