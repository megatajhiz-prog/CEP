"""Plant water-flow graph (source -> subsystem -> outlet / evaporation / product / loss)
built from an :class:`Analysis`; the GUI draws it as a Sankey-style diagram.

Edge colours and node status come from the water balance, so a leaking subsystem is visible
at a glance. Transfers between subsystems use ``plant.links``; any R'_out not covered by a
link is routed to a single "undefined transfer" node so that the picture never hides water.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .analysis import Analysis

LOSS_MIN_PCT = 0.5     # unaccounted loss below this share of inflow is not drawn as an edge


@dataclass
class FlowNode:
    id: str
    kind: str            # source | subsystem | outlet | evap | product | loss | pool
    name: str
    volume: float = 0.0
    column: int = 0
    status: str = ""     # balance status for subsystems


@dataclass
class FlowEdge:
    src: str
    dst: str
    volume: float
    kind: str            # intake | discharge | transfer | evap | product | loss


@dataclass
class FlowGraph:
    nodes: List[FlowNode] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def node(self, nid: str) -> FlowNode:
        for n in self.nodes:
            if n.id == nid:
                return n
        raise KeyError(nid)


def build_flow(a: Analysis, labels: Dict[str, str]) -> FlowGraph:
    """``labels``: translated names for the fixed nodes: evap, product, loss, pool."""
    plant = a.plant
    g = FlowGraph()
    status = {b.name: b for b in a.balance.subsystems}
    names = {s.name for s in plant.subsystems}

    def add(kind: str, name: str, col: int, st: str = "") -> str:
        nid = f"{kind}:{name}"
        if not any(n.id == nid for n in g.nodes):
            g.nodes.append(FlowNode(nid, kind, name, 0.0, col, st))
        return nid

    def edge(src: str, dst: str, vol: float, kind: str) -> None:
        if vol > 1e-9:
            g.edges.append(FlowEdge(src, dst, vol, kind))

    for s in plant.subsystems:
        b = status.get(s.name)
        add("subsystem", s.name, 1, b.status if b else "")
    for sub in plant.subsystems:
        sid = f"subsystem:{sub.name}"
        for src, v in sub.intake.items():
            edge(add("source", src, 0), sid, v, "intake")
        for out, v in sub.discharge.items():
            edge(sid, add("outlet", out, 2), v, "discharge")
        if sub.evaporation > 0:
            edge(sid, add("evap", labels["evap"], 2), sub.evaporation, "evap")
        if sub.product > 0:
            edge(sid, add("product", labels["product"], 2), sub.product, "product")
        b = status.get(sub.name)
        if b and b.unknown_loss > 0 and b.unknown_loss_pct_of_inflow > LOSS_MIN_PCT:
            edge(sid, add("loss", labels["loss"], 2), b.unknown_loss, "loss")

    # transfers between subsystems
    linked: Dict[str, float] = {}
    for lk in plant.links:
        if lk.src in names and lk.dst in names and lk.src != lk.dst and lk.volume > 0:
            linked[lk.src] = linked.get(lk.src, 0.0) + lk.volume
        elif lk.volume > 0:
            g.warnings.append(f"{lk.src} -> {lk.dst}")
    for sub in plant.subsystems:
        total = sub.to_other
        done = linked.get(sub.name, 0.0)
        if total <= 0:
            continue
        scale = min(1.0, total / done) if done > 0 else 0.0
        for lk in plant.links:
            if lk.src == sub.name and lk.dst in names and lk.dst != lk.src and lk.volume > 0:
                edge(f"subsystem:{sub.name}", f"subsystem:{lk.dst}", lk.volume * scale, "transfer")
        rest = total - done * scale
        if rest > 1e-6:
            edge(f"subsystem:{sub.name}", add("pool", labels["pool"], 2), rest, "transfer")

    for n in g.nodes:
        ins = sum(e.volume for e in g.edges if e.dst == n.id)
        outs = sum(e.volume for e in g.edges if e.src == n.id)
        n.volume = max(ins, outs)
    return g
