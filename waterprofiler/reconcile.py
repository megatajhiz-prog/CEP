"""Data reconciliation: weighted least-squares closure of the water balance.

Given measured/estimated flows x0 with standard deviations sigma, find the
adjusted flows x that minimise

    sum_i ((x_i - x0_i) / sigma_i)^2

subject to linear constraints  A x = b  (subsystem balances L_x = 0, plant
meter totals, inter-subsystem transfers cancelling). The closed form is

    x = x0 - S A^T (A S A^T)^+ (A x0 - b),     S = diag(sigma^2)

Non-negativity is enforced by an active-set loop: any flow driven below zero is
pinned at zero and the problem is solved again. The same loop can hold every flow within
``max_rel_change`` of its entered value (a flow that would move further is pinned at the limit).

Sanity checks after the solution (they do not change it, they tell whether to trust it):
  * chi-square test: with n independent constraints the weighted sum of squares of an
    honest data set is about n; a value above the 95 % point means the data contradict each
    other more than the stated uncertainties allow (a wrong meter or a missing flow);
  * a flow that moved by more than 3 sigma, or by more than half of its value, is listed;
  * the constraints could not be met inside the limits (the data are in conflict).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .model import Plant

Key = Tuple[int, str]   # (subsystem index, flow key)


@dataclass
class Adjustment:
    subsystem: str
    flow: str
    original: float
    adjusted: float

    @property
    def delta(self) -> float:
        return self.adjusted - self.original

    @property
    def delta_pct(self) -> Optional[float]:
        return 100.0 * self.delta / self.original if self.original else None


@dataclass
class ReconcileResult:
    plant: Plant
    adjustments: List[Adjustment]
    chi_square: float
    residual_before: float
    residual_after: float
    notes: List[str] = field(default_factory=list)
    dof: int = 0                       # independent constraints
    chi_critical: float = 0.0          # 95 % point of chi-square with dof degrees of freedom
    consistent: bool = True            # chi_square <= chi_critical
    warnings: List[str] = field(default_factory=list)
    suspects: List[Adjustment] = field(default_factory=list)   # moved by > 3 sigma or by > 50 %


def chi2_95(k: int) -> float:
    """95 % point of the chi-square distribution (Wilson-Hilferty approximation, good to ~1 % for k >= 1)."""
    if k <= 0:
        return 0.0
    c = 2.0 / (9.0 * k)
    return k * (1.0 - c + 1.6449 * c ** 0.5) ** 3


def _flows(plant: Plant) -> List[Tuple[Key, float]]:
    """Adjustable flows. A flow entered as exactly 0 means 'does not exist' and stays fixed at 0."""
    out: List[Tuple[Key, float]] = []

    def add(key: Key, v: float) -> None:
        if v != 0.0:
            out.append((key, v))

    leaf = {s.name for s in plant.leaves()}
    for i, s in enumerate(plant.subsystems):
        if s.name not in leaf:               # a unit with equipment is derived from them
            continue
        for src, v in s.intake.items():
            add((i, f"intake:{src}"), v)
        add((i, "from_other"), s.from_other)
        add((i, "to_other"), s.to_other)
        add((i, "product"), s.product)
        add((i, "evaporation"), s.evaporation)
        for o, v in s.discharge.items():
            add((i, f"discharge:{o}"), v)
    return out


def reconcile(
    plant: Plant,
    default_rel_sigma: float = 0.15,
    rel_sigma: Optional[Dict[Tuple[str, str], float]] = None,
    use_meters: bool = True,
    meter_rel_sigma: float = 0.02,
    max_rel_change: Optional[float] = None,
) -> ReconcileResult:
    """Return a reconciled copy of ``plant``.

    rel_sigma maps (subsystem name, flow key) -> relative standard deviation,
    e.g. {("Cooling tower", "intake:Municipal"): 0.03} for a well-metered flow.
    Flow keys: ``intake:<source>``, ``discharge:<outlet>``, ``from_other``,
    ``to_other``, ``product``, ``evaporation``.

    ``max_rel_change`` (e.g. 1.0) limits every flow to  x0 * (1 +- max_rel_change); None = only non-negative.
    """
    rel_sigma = rel_sigma or {}
    flows = _flows(plant)
    n = len(flows)
    if n == 0:
        raise ValueError("plant has no flows to reconcile")
    idx = {k: j for j, (k, _) in enumerate(flows)}

    def put(row: np.ndarray, key: Key, coeff: float) -> None:
        j = idx.get(key)
        if j is not None:
            row[j] += coeff
    x0 = np.array([v for _, v in flows], dtype=float)
    mean_flow = float(np.mean(np.abs(x0))) or 1.0

    from .uncertainty import meter_accuracy
    acc = meter_accuracy(plant)

    def _default_rel(name: str, key: str) -> float:
        """A stated meter accuracy of the node's flow replaces the default relative sigma."""
        f = key.split(":", 1)[0]
        return acc.get(f"sub:{name}:{f}", default_rel_sigma)

    sig = np.empty(n)
    for j, ((i, key), v) in enumerate(flows):
        nm = plant.subsystems[i].name
        r = rel_sigma.get((nm, key), _default_rel(nm, key))
        sig[j] = max(r * max(abs(v), 0.01 * mean_flow), 1e-9)

    rows: List[np.ndarray] = []
    rhs: List[float] = []

    # 1) each subsystem closes: inflows - outflows = change of stored volume
    leaf = {s.name for s in plant.leaves()}
    for i, s in enumerate(plant.subsystems):
        if s.name not in leaf:
            continue
        a = np.zeros(n)
        for src in s.intake:
            put(a, (i, f"intake:{src}"), 1.0)
        put(a, (i, "from_other"), 1.0)
        put(a, (i, "to_other"), -1.0)
        put(a, (i, "product"), -1.0)
        put(a, (i, "evaporation"), -1.0)
        for o in s.discharge:
            put(a, (i, f"discharge:{o}"), -1.0)
        rows.append(a); rhs.append(s.storage_change)

    # 2) transfers between subsystems cancel
    a = np.zeros(n)
    for i, _ in enumerate(plant.subsystems):
        put(a, (i, "to_other"), 1.0)
        put(a, (i, "from_other"), -1.0)
    rows.append(a); rhs.append(0.0)

    # 3) plant meters (per source and per outlet)
    notes: List[str] = []
    if use_meters:
        for src in plant.sources:
            if src.metered_m3 is None:
                continue
            a = np.zeros(n)
            for i, s in enumerate(plant.subsystems):
                if src.name in s.intake:
                    put(a, (i, f"intake:{src.name}"), 1.0)
            if a.any():
                rows.append(a); rhs.append(src.metered_m3)
        for o in plant.outlets:
            if o.metered_m3 is None:
                continue
            a = np.zeros(n)
            for i, s in enumerate(plant.subsystems):
                if o.name in s.discharge:
                    put(a, (i, f"discharge:{o.name}"), 1.0)
            if a.any():
                rows.append(a); rhs.append(o.metered_m3)
        # meter_rel_sigma is reserved: meters are treated as exact constraints.
        _ = meter_rel_sigma

    A = np.vstack(rows)
    b = np.array(rhs)
    S = np.diag(sig ** 2)

    lo = np.zeros(n)
    hi = np.full(n, np.inf)
    if max_rel_change is not None:
        mr = max(0.0, float(max_rel_change))
        lo = np.maximum(0.0, x0 * (1.0 - mr))
        hi = x0 * (1.0 + mr)
    fixed = np.zeros(n, dtype=bool)
    pin = np.zeros(n)
    x = x0.copy()
    for _ in range(2 * n + 2):
        free = ~fixed
        Af = A[:, free]
        Sf = S[np.ix_(free, free)]
        resid = A @ np.where(fixed, pin, x0) - b
        M = Af @ Sf @ Af.T
        lam = np.linalg.pinv(M) @ resid
        x = pin.copy()
        x[free] = x0[free] - Sf @ Af.T @ lam
        under = free & (x < lo - 1e-9 * np.maximum(1.0, np.abs(lo)))
        over = free & (x > hi + 1e-9 * np.maximum(1.0, np.abs(hi)))
        if not (under.any() or over.any()):
            break
        dist = np.where(under, (lo - x) / sig, 0.0) + np.where(over, (x - hi) / sig, 0.0)
        worst = int(np.argmax(dist))
        fixed[worst] = True
        if under[worst]:
            pin[worst] = lo[worst]
            notes.append("a flow was pinned at zero to keep reconciled values non-negative" if lo[worst] == 0.0
                         else "a flow was held at its lower limit")
        else:
            pin[worst] = hi[worst]
            notes.append("a flow was held at its upper limit")
    x = np.where(x < 0, 0.0, x)

    new_plant = copy.deepcopy(plant)
    adjustments: List[Adjustment] = []
    for j, ((i, key), v) in enumerate(flows):
        s = new_plant.subsystems[i]
        nv = float(x[j])
        if key.startswith("intake:"):
            s.intake[key.split(":", 1)[1]] = nv
        elif key.startswith("discharge:"):
            s.discharge[key.split(":", 1)[1]] = nv
        else:
            setattr(s, key, nv)
        if abs(nv - v) > 1e-9 * max(1.0, abs(v)):
            adjustments.append(Adjustment(s.name, key, v, nv))

    new_plant.rollup()
    chi2 = float(np.sum(((x - x0) / sig) ** 2))
    dof = int(np.linalg.matrix_rank(A))
    crit = chi2_95(dof)
    resid_after = float(np.linalg.norm(A @ x - b))
    warn: List[str] = []
    suspects = [adj for j, ((i, key), v) in enumerate(flows)
                for adj in [next((q for q in adjustments if q.subsystem == new_plant.subsystems[i].name and q.flow == key), None)]
                if adj is not None and (abs(adj.delta) > 3.0 * sig[j] or (adj.original and abs(adj.delta) > 0.5 * abs(adj.original)))]
    scale = max(1.0, float(np.linalg.norm(b)))
    if resid_after > 1e-6 * scale:
        warn.append("Reconciliation: the balance cannot be closed within the limits; the data contradict each other "
                    "(a meter reading or a flow is probably wrong)")
    if dof > 0 and chi2 > crit:
        warn.append(f"Reconciliation: weighted sum of squares {chi2:,.1f} exceeds the 95 % limit {crit:,.1f} for {dof} "
                    "constraints; the adjustments are larger than the stated uncertainties allow, check the flows listed first")
    if suspects:
        warn.append(f"Reconciliation: {len(suspects)} flow(s) moved by more than 3 sigma or by more than half of their value")
    return ReconcileResult(
        plant=new_plant,
        adjustments=adjustments,
        chi_square=chi2,
        residual_before=float(np.linalg.norm(A @ x0 - b)),
        residual_after=resid_after,
        notes=sorted(set(notes)),
        dof=dof, chi_critical=crit, consistent=not (dof > 0 and chi2 > crit), warnings=warn, suspects=suspects,
    )


def measured_sigma(plant: Plant, rel: float = 1e-4) -> Dict[Tuple[str, str], float]:
    """Relative sigmas that keep series-driven flows (time-series data = measurements) practically fixed.

    A flow the time series determines is rewritten into the model on every sync, so reconciliation may only
    adjust the flows that are not driven; the closure is absorbed by those.
    """
    from . import timeseries as TS            # local import: reconcile stays usable without the series module
    drv = TS.driven(plant)
    out: Dict[Tuple[str, str], float] = {}
    for s in plant.subsystems:
        if f"sub:{s.name}:intake" in drv:
            out.update({(s.name, f"intake:{n}"): rel for n in s.intake})
        if f"sub:{s.name}:discharge" in drv:
            out.update({(s.name, f"discharge:{n}"): rel for n in s.discharge})
        for f in ("evaporation", "product"):
            if f"sub:{s.name}:{f}" in drv:
                out[(s.name, f)] = rel
    return out
