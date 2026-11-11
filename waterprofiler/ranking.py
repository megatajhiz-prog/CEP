"""Ranking of the plan's water-saving measures (multi-criteria decision analysis) and the best set within a budget.

Criteria (per measure of the plan):
  saving      water saved, m3/year                      (higher is better)
  npv         net present value                         (higher)
  payback     simple payback, years                     (lower; "never" counts as the measure's life)
  capex       investment                                (lower)
  lcow        levelised cost of saved water, per m3     (lower)
  ease        ease of implementation, score 1..5        (higher, entered by the user)
  reliability technical reliability / low risk, 1..5    (higher, entered by the user)

Two methods: weighted sum of min-max normalised criteria (WSM, default) and TOPSIS. The weights are the user's; a
sensitivity run perturbs every weight by +-50 % many times and reports how often each measure is first and its range of ranks.
The portfolio is the set of measures that maximises the chosen objective for the combined (overlap-corrected) result
under an investment budget; up to 14 measures are enumerated exactly, more are filled greedily.
"""

from __future__ import annotations

import copy
import itertools
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import economics as EC
from . import measures as M
from .model import PlanItem, Plant

CRITERIA: Tuple[Tuple[str, bool], ...] = (       # (id, higher is better)
    ("saving", True), ("npv", True), ("payback", False), ("capex", False), ("lcow", False),
    ("ease", True), ("reliability", True),
)
DEFAULT_WEIGHTS: Dict[str, float] = {"saving": 25, "npv": 25, "payback": 15, "capex": 10, "lcow": 5, "ease": 10, "reliability": 10}
METHODS = ("wsm", "topsis")
OBJECTIVES = ("npv", "saving")
EXACT_LIMIT = 14
RUNS = 400


class RankError(ValueError):
    pass


@dataclass
class Settings:
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    method: str = "wsm"
    budget: float = 0.0            # 0 = no limit
    objective: str = "npv"

    @staticmethod
    def of(plant: Plant) -> "Settings":
        d = plant.ranking or {}
        w = dict(DEFAULT_WEIGHTS)
        for k, v in (d.get("weights") or {}).items():
            if k in w:
                try:
                    w[k] = max(0.0, float(v))
                except (TypeError, ValueError):
                    pass
        m = d.get("method", "wsm")
        o = d.get("objective", "npv")
        try:
            b = max(0.0, float(d.get("budget", 0.0) or 0.0))
        except (TypeError, ValueError):
            b = 0.0
        return Settings(w, m if m in METHODS else "wsm", b, o if o in OBJECTIVES else "npv")

    def store(self, plant: Plant) -> None:
        plant.ranking = {"weights": dict(self.weights), "method": self.method, "budget": self.budget, "objective": self.objective}


@dataclass
class RankRow:
    index: int                     # position in plant.plan
    item: PlanItem
    label: str
    raw: Dict[str, float]
    score: float = 0.0             # 0..1 under the chosen method
    rank: int = 0
    wsm: float = 0.0
    topsis: float = 0.0
    rank_mean: float = 0.0
    rank_min: int = 0
    rank_max: int = 0
    p_first: float = 0.0           # share of the weight perturbations in which it ranks first


@dataclass
class Portfolio:
    chosen: List[int]              # indices in plant.plan
    capex: float
    saving: float                  # combined, m3/year
    npv: float
    exact: bool
    budget: float


@dataclass
class RankResult:
    rows: List[RankRow]            # sorted by rank
    skipped: List[Tuple[int, str]] # (plan index, reason)
    weights: Dict[str, float]      # normalised
    portfolio: Optional[Portfolio]
    warnings: List[str] = field(default_factory=list)


def normalise_weights(w: Dict[str, float]) -> Dict[str, float]:
    tot = sum(max(0.0, v) for v in w.values())
    if tot <= 0:
        raise RankError("weights")
    return {k: max(0.0, v) / tot for k, v in w.items()}


def _raw(plant: Plant) -> Tuple[List[RankRow], List[Tuple[int, str]]]:
    ev = M.evaluate_plan(plant)
    rows: List[RankRow] = []
    skipped: List[Tuple[int, str]] = []
    for i, (ln, ie) in enumerate(zip(ev.lines, EC.evaluate_plan_economics(plant))):
        if ie.result is None:
            skipped.append((i, ie.error or "invalid"))
            continue
        r = ie.result
        life = ln.item.life_years or 1.0
        raw = {"saving": ln.saving, "npv": r.npv, "payback": r.payback if r.payback is not None else life,
               "capex": ln.item.capex, "lcow": r.lcow if r.lcow is not None else float("inf"),
               "ease": min(5.0, max(1.0, ln.item.ease)), "reliability": min(5.0, max(1.0, ln.item.reliability))}
        rows.append(RankRow(i, ln.item, f"{ln.measure.id}. {ln.measure.fa}", raw))
    finite = [x.raw["lcow"] for x in rows if x.raw["lcow"] != float("inf")]
    worst = (max(finite) * 2 if finite else 0.0)
    for x in rows:
        if x.raw["lcow"] == float("inf"):
            x.raw["lcow"] = worst
    return rows, skipped


def _norm(rows: Sequence[RankRow]) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = [dict() for _ in rows]
    for c, high in CRITERIA:
        vals = [x.raw[c] for x in rows]
        lo, hi = min(vals), max(vals)
        for k, v in enumerate(vals):
            out[k][c] = 0.5 if hi - lo <= 1e-12 else ((v - lo) / (hi - lo) if high else (hi - v) / (hi - lo))
    return out


def _wsm(norm: Sequence[Dict[str, float]], w: Dict[str, float]) -> List[float]:
    return [sum(w[c] * n[c] for c, _h in CRITERIA) for n in norm]


def _topsis(norm: Sequence[Dict[str, float]], w: Dict[str, float]) -> List[float]:
    """TOPSIS on the min-max normalised matrix (every criterion already 'higher is better')."""
    ideal = {c: max(n[c] for n in norm) for c, _h in CRITERIA}
    anti = {c: min(n[c] for n in norm) for c, _h in CRITERIA}
    res = []
    for n in norm:
        dp = sum((w[c] * (n[c] - ideal[c])) ** 2 for c, _h in CRITERIA) ** 0.5
        dm = sum((w[c] * (n[c] - anti[c])) ** 2 for c, _h in CRITERIA) ** 0.5
        res.append(dm / (dp + dm) if dp + dm > 0 else 0.5)
    return res


def _ranks(scores: Sequence[float]) -> List[int]:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    r = [0] * len(scores)
    for pos, i in enumerate(order, 1):
        r[i] = pos
    return r


def _score(norm, w, method) -> List[float]:
    return _topsis(norm, w) if method == "topsis" else _wsm(norm, w)


def sensitivity(norm: Sequence[Dict[str, float]], w: Dict[str, float], method: str,
                runs: int = RUNS, seed: int = 7) -> Tuple[List[float], List[int], List[int], List[float]]:
    """(mean rank, best rank, worst rank, share of runs ranked first) per measure for weights perturbed by +-50 %."""
    rng = random.Random(seed)
    n = len(norm)
    tot = [0.0] * n
    lo = [n + 1] * n
    hi = [0] * n
    first = [0] * n
    for _ in range(runs):
        ww = normalise_weights({c: w[c] * rng.uniform(0.5, 1.5) for c, _h in CRITERIA})
        rk = _ranks(_score(norm, ww, method))
        for i, r in enumerate(rk):
            tot[i] += r
            lo[i] = min(lo[i], r)
            hi[i] = max(hi[i], r)
            first[i] += r == 1
    return [t / runs for t in tot], lo, hi, [f / runs for f in first]


def _subset_result(plant: Plant, idx: Sequence[int]) -> Tuple[float, float, float]:
    """(capex, combined saving, sum of NPV) of a subset of the plan, overlaps corrected."""
    p = copy.copy(plant)
    p.plan = [plant.plan[i] for i in idx]
    if not p.plan:
        return 0.0, 0.0, 0.0
    ev = M.evaluate_plan(p)
    npv = sum(e.result.npv for e in EC.evaluate_plan_economics(p) if e.result is not None)
    return sum(i.capex for i in p.plan), ev.saving, npv


def portfolio(plant: Plant, candidates: Sequence[RankRow], budget: float, objective: str) -> Portfolio:
    idx = [x.index for x in candidates]
    key = (lambda r: (r[2], r[1])) if objective == "npv" else (lambda r: (r[1], r[2]))
    cap = budget if budget > 0 else float("inf")
    if len(idx) <= EXACT_LIMIT:
        best: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        best_set: Tuple[int, ...] = ()
        for k in range(1, len(idx) + 1):
            for sub in itertools.combinations(idx, k):
                if sum(plant.plan[i].capex for i in sub) > cap:
                    continue
                r = _subset_result(plant, sub)
                if key(r) > key(best):
                    best, best_set = r, sub
        return Portfolio(sorted(best_set), best[0], best[1], best[2], True, budget)
    chosen: List[int] = []                     # greedy by objective gain per investment
    cur = (0.0, 0.0, 0.0)
    left = list(idx)
    while left:
        cand = []
        for i in left:
            r = _subset_result(plant, chosen + [i])
            if r[0] <= cap:
                gain = key(r)[0] - key(cur)[0]
                cand.append((gain / max(plant.plan[i].capex, 1.0), i, r))
        cand = [c for c in cand if c[0] > 0]
        if not cand:
            break
        _g, i, r = max(cand)
        chosen.append(i)
        left.remove(i)
        cur = r
    return Portfolio(sorted(chosen), cur[0], cur[1], cur[2], False, budget)


def rank_plan(plant: Plant, settings: Optional[Settings] = None, with_portfolio: bool = True) -> RankResult:
    st = settings or Settings.of(plant)
    w = normalise_weights(st.weights)
    rows, skipped = _raw(plant)
    warnings: List[str] = []
    if skipped:
        warnings.append("skipped")
    if len(rows) < 2:
        warnings.append("few")
    if not rows:
        return RankResult([], skipped, w, None, warnings)
    norm = _norm(rows)
    wsm, top = _wsm(norm, w), _topsis(norm, w)
    score = top if st.method == "topsis" else wsm
    ranks = _ranks(score)
    mean, lo, hi, first = sensitivity(norm, w, st.method)
    for i, x in enumerate(rows):
        x.wsm, x.topsis, x.score, x.rank = wsm[i], top[i], score[i], ranks[i]
        x.rank_mean, x.rank_min, x.rank_max, x.p_first = mean[i], lo[i], hi[i], first[i]
    rows.sort(key=lambda x: x.rank)
    if len({x.index for x in rows}) != len(rows):
        raise RankError("duplicate")
    pf = portfolio(plant, rows, st.budget, st.objective) if with_portfolio else None
    if pf is not None and not pf.chosen and st.budget > 0:
        warnings.append("budget_too_small")
    if len(rows) > EXACT_LIMIT:
        warnings.append("greedy")
    return RankResult(rows, skipped, w, pf, warnings)
