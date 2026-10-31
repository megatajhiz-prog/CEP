"""Data reconciliation: weighted least-squares closure of the water balance.

Given measured/estimated flows x0 with standard deviations sigma, find the
adjusted flows x that minimise

    sum_i ((x_i - x0_i) / sigma_i)^2

subject to linear constraints  A x = b  (subsystem balances L_x = 0, plant
meter totals, inter-subsystem transfers cancelling). The closed form is

    x = x0 - S A^T (A S A^T)^+ (A x0 - b),     S = diag(sigma^2)

Non-negativity is enforced by an active-set loop: any flow driven below zero is
pinned at zero and the problem is solved again.
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


def _flows(plant: Plant) -> List[Tuple[Key, float]]:
    """Adjustable flows. A flow entered as exactly 0 means 'does not exist' and stays fixed at 0."""
    out: List[Tuple[Key, float]] = []

    def add(key: Key, v: float) -> None:
        if v != 0.0:
            out.append((key, v))

    for i, s in enumerate(plant.subsystems):
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
) -> ReconcileResult:
    """Return a reconciled copy of ``plant``.

    rel_sigma maps (subsystem name, flow key) -> relative standard deviation,
    e.g. {("Cooling tower", "intake:Municipal"): 0.03} for a well-metered flow.
    Flow keys: ``intake:<source>``, ``discharge:<outlet>``, ``from_other``,
    ``to_other``, ``product``, ``evaporation``.
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

    sig = np.empty(n)
    for j, ((i, key), v) in enumerate(flows):
        r = rel_sigma.get((plant.subsystems[i].name, key), default_rel_sigma)
        sig[j] = max(r * max(abs(v), 0.01 * mean_flow), 1e-9)

    rows: List[np.ndarray] = []
    rhs: List[float] = []

    # 1) each subsystem closes: inflows - outflows = 0
    for i, s in enumerate(plant.subsystems):
        a = np.zeros(n)
        for src in s.intake:
            put(a, (i, f"intake:{src}"), 1.0)
        put(a, (i, "from_other"), 1.0)
        put(a, (i, "to_other"), -1.0)
        put(a, (i, "product"), -1.0)
        put(a, (i, "evaporation"), -1.0)
        for o in s.discharge:
            put(a, (i, f"discharge:{o}"), -1.0)
        rows.append(a); rhs.append(0.0)

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

    fixed = np.zeros(n, dtype=bool)
    x = x0.copy()
    for _ in range(n + 1):
        free = ~fixed
        Af = A[:, free]
        Sf = S[np.ix_(free, free)]
        resid = A @ np.where(fixed, 0.0, x0) - b
        M = Af @ Sf @ Af.T
        lam = np.linalg.pinv(M) @ resid
        xf = x0[free] - Sf @ Af.T @ lam
        x = np.zeros(n)
        x[free] = xf
        neg = free & (x < -1e-12)
        if not neg.any():
            break
        # pin the most negative flow at zero and iterate
        worst = np.argmin(np.where(neg, x, 0.0))
        fixed[worst] = True
        notes.append("a flow was pinned at zero to keep reconciled values non-negative")
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

    chi2 = float(np.sum(((x - x0) / sig) ** 2))
    return ReconcileResult(
        plant=new_plant,
        adjustments=adjustments,
        chi_square=chi2,
        residual_before=float(np.linalg.norm(A @ x0 - b)),
        residual_after=float(np.linalg.norm(A @ x - b)),
        notes=sorted(set(notes)),
    )
