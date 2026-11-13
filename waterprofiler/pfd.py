"""Process-flow diagram (PFD) of the plant: the nodes with their symbols and positions, the streams between them, the
automatic layout, and the information that belongs to a node (balance, cost, measures, meters, product allocation).

Three levels are drawn: sources and sinks (outlets, evaporation, product) around the units; a unit with equipment is a
container that holds its equipment. Water streams are connected to the nodes that carry data (equipment, or units without
equipment); a stream can also end at a unit container (a transfer recorded on the unit).

Ids are ``kind:name`` with kind in source | subsystem | outlet | evap | product | pool | loss, the same as the Sankey
diagram, so an edit made on either picture means the same thing (``resolve_connection``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .analysis import Analysis
from .model import Plant

NODE_W, NODE_H = 96.0, 92.0          # symbol + label
GAP_X, GAP_Y = 54.0, 34.0
PAD, TITLE_H = 22.0, 28.0
COLS_IN_UNIT = 3
COLUMN_GAP = 210.0
LOSS_MIN_PCT = 0.5

SUBSYSTEM_SYMBOLS = ("process", "cooling_tower", "boiler", "sanitary", "irrigation", "vessel", "tank", "pump", "treatment")
_KIND_SYMBOL = {"process": "process", "cooling_tower": "cooling_tower", "boiler": "boiler", "sanitary": "sanitary",
                "irrigation": "irrigation", "wwtp": "treatment"}


@dataclass
class PNode:
    id: str
    kind: str                  # source | subsystem | outlet | evap | product | pool | loss
    name: str
    label: str
    symbol: str
    x: float = 0.0             # top-left; relative to the container when ``parent`` is set
    y: float = 0.0
    w: float = NODE_W
    h: float = NODE_H
    parent: str = ""           # id of the container the node sits in
    container: bool = False    # a unit with equipment
    children: List[str] = field(default_factory=list)
    status: str = ""           # balance status of a subsystem
    volume: float = 0.0        # m3/year through the node


@dataclass
class PEdge:
    src: str
    dst: str
    kind: str                  # intake | discharge | transfer | evap | product | loss
    volume: float
    sub: str = ""
    ref: str = ""


@dataclass
class PFD:
    nodes: Dict[str, PNode] = field(default_factory=dict)
    edges: List[PEdge] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def absolute(self, nid: str) -> Tuple[float, float]:
        n = self.nodes[nid]
        if n.parent and n.parent in self.nodes:
            px, py = self.absolute(n.parent)
            return px + n.x, py + n.y
        return n.x, n.y

    def bounds(self) -> Tuple[float, float, float, float]:
        if not self.nodes:
            return 0.0, 0.0, 0.0, 0.0
        xs, ys, xe, ye = [], [], [], []
        for nid, n in self.nodes.items():
            x, y = self.absolute(nid)
            xs.append(x), ys.append(y), xe.append(x + n.w), ye.append(y + n.h)
        return min(xs), min(ys), max(xe), max(ye)


def _symbol_of(plant: Plant, name: str, kind: str) -> str:
    return _KIND_SYMBOL.get(kind, "vessel")


def split_id(nid: str) -> Tuple[str, str]:
    k, _, n = nid.partition(":")
    return k, n


def build_pfd(a: Analysis, labels: Dict[str, str]) -> PFD:
    """``labels``: translated names of the fixed nodes: evap, product, loss, pool."""
    plant = a.plant
    plant.rollup()
    g = PFD()
    pos = (plant.pfd or {}).get("pos", {}) or {}
    sym_over = (plant.pfd or {}).get("symbol", {}) or {}
    bal = a.balance.nodes
    units = plant.units()

    def put(n: PNode) -> PNode:
        g.nodes[n.id] = n
        return n

    # ---- unit column: units (containers hold their equipment)
    y = 0.0
    unit_x = NODE_W + COLUMN_GAP
    right_edge = unit_x
    for u in units:
        ch = plant.children(u.name)
        uid = f"subsystem:{u.name}"
        st = bal[u.name].status if u.name in bal else ""
        if not ch:
            n = put(PNode(uid, "subsystem", u.name, u.name, sym_over.get(uid) or _symbol_of(plant, u.name, u.kind), unit_x, y, status=st))
            y += n.h + GAP_Y
            continue
        rows = (len(ch) + COLS_IN_UNIT - 1) // COLS_IN_UNIT
        cols = min(COLS_IN_UNIT, len(ch))
        cw = PAD * 2 + cols * NODE_W + (cols - 1) * GAP_X
        chh = TITLE_H + PAD + rows * NODE_H + (rows - 1) * GAP_Y + PAD
        c = put(PNode(uid, "subsystem", u.name, u.name, "unit", unit_x, y, cw, chh, container=True, status=st))
        for k, e in enumerate(ch):
            eid = f"subsystem:{e.name}"
            r_, c_ = divmod(k, COLS_IN_UNIT)
            put(PNode(eid, "subsystem", e.name, e.name, sym_over.get(eid) or _symbol_of(plant, e.name, e.kind),
                      PAD + c_ * (NODE_W + GAP_X), TITLE_H + PAD + r_ * (NODE_H + GAP_Y), parent=uid,
                      status=bal[e.name].status if e.name in bal else ""))
            c.children.append(eid)
        y += chh + GAP_Y
        right_edge = max(right_edge, unit_x + cw)
    sink_x = right_edge + COLUMN_GAP

    # ---- edges from the data carried by the leaves
    leaves = plant.leaves()
    srcs: Dict[str, None] = {}
    outs: Dict[str, None] = {}

    def src_node(name: str) -> str:
        nid = f"source:{name}"
        if nid not in g.nodes:
            put(PNode(nid, "source", name, name, sym_over.get(nid) or "source"))
        return nid

    def out_node(name: str) -> str:
        nid = f"outlet:{name}"
        if nid not in g.nodes:
            put(PNode(nid, "outlet", name, name, sym_over.get(nid) or "outlet"))
        return nid

    def sink(kind: str) -> str:
        nid = f"{kind}:{labels[kind]}"
        if nid not in g.nodes:
            put(PNode(nid, kind, labels[kind], labels[kind], kind))
        return nid

    def edge(s: str, d: str, vol: float, kind: str, sub: str = "", ref: str = "") -> None:
        if vol > 1e-9:
            g.edges.append(PEdge(s, d, kind, vol, sub, ref))

    for s in leaves:
        sid = f"subsystem:{s.name}"
        for src, v in s.intake.items():
            edge(src_node(src), sid, v, "intake", s.name, src)
        for out, v in s.discharge.items():
            edge(sid, out_node(out), v, "discharge", s.name, out)
        if s.evaporation > 0:
            edge(sid, sink("evap"), s.evaporation, "evap", s.name)
        if s.product > 0:
            edge(sid, sink("product"), s.product, "product", s.name)
        b = bal.get(s.name)
        if b and b.unknown_loss > 0 and b.unknown_loss_pct_of_inflow > LOSS_MIN_PCT:
            edge(sid, sink("loss"), b.unknown_loss, "loss", s.name)
    linked: Dict[str, float] = {}
    pair: Dict[Tuple[str, str], float] = {}
    for lk in plant.links:
        if lk.volume <= 0 or lk.src == lk.dst:
            continue
        if plant.node(lk.src) is None or plant.node(lk.dst) is None:
            g.warnings.append(f"{lk.src} -> {lk.dst}")
            continue
        pair[(lk.src, lk.dst)] = pair.get((lk.src, lk.dst), 0.0) + lk.volume
        linked[lk.src] = linked.get(lk.src, 0.0) + lk.volume
    for (s_, d_), v in pair.items():
        edge(f"subsystem:{s_}", f"subsystem:{d_}", v, "transfer", s_, d_)
    for s in leaves:
        rest = s.to_other - linked.get(s.name, 0.0)
        if rest > 1e-6:
            edge(f"subsystem:{s.name}", sink("pool"), rest, "transfer", s.name)

    # ---- source and sink columns (after the edges so that only the used ones appear)
    sources_order = [x.name for x in plant.sources] + [n.name for n in g.nodes.values() if n.kind == "source" and n.name not in {x.name for x in plant.sources}]
    yy = 0.0
    for name in sources_order:
        nid = f"source:{name}"
        if nid in g.nodes:
            n = g.nodes[nid]
            n.x, n.y = 0.0, yy
            yy += n.h + GAP_Y
    sink_order = [f"outlet:{o.name}" for o in plant.outlets] + [f"evap:{labels['evap']}", f"product:{labels['product']}",
                                                                f"pool:{labels['pool']}", f"loss:{labels['loss']}"]
    yy = 0.0
    seen = set()
    for nid in sink_order + [k for k in g.nodes if g.nodes[k].kind in ("outlet",)]:
        if nid in g.nodes and nid not in seen:
            seen.add(nid)
            n = g.nodes[nid]
            n.x, n.y = sink_x, yy
            yy += n.h + GAP_Y
    # centre the two outer columns on the unit column
    unit_h = max((n.y + n.h for n in g.nodes.values() if n.kind == "subsystem" and not n.parent), default=0.0)
    for kinds in (("source",), ("outlet", "evap", "product", "pool", "loss")):
        col = [n for n in g.nodes.values() if n.kind in kinds]
        if col:
            h = max(n.y + n.h for n in col)
            shift = max(0.0, (unit_h - h) / 2)
            for n in col:
                n.y += shift

    # ---- flow through every node
    for n in g.nodes.values():
        ins = sum(e.volume for e in g.edges if e.dst == n.id)
        outs = sum(e.volume for e in g.edges if e.src == n.id)
        n.volume = max(ins, outs)
    for n in g.nodes.values():
        if n.container:
            n.volume = sum(g.nodes[c].volume for c in n.children)
    # ---- the user's positions win (top-level: absolute; equipment: inside its unit)
    for nid, xy in pos.items():
        n = g.nodes.get(nid)
        if n is not None and isinstance(xy, (list, tuple)) and len(xy) == 2:
            try:
                n.x, n.y = float(xy[0]), float(xy[1])
            except (TypeError, ValueError):
                pass
    return g


def set_position(plant: Plant, nid: str, x: float, y: float) -> None:
    plant.pfd = dict(plant.pfd or {})
    p = dict(plant.pfd.get("pos", {}))
    p[nid] = [round(float(x), 1), round(float(y), 1)]
    plant.pfd["pos"] = p


def set_symbol(plant: Plant, nid: str, symbol: str) -> None:
    k, name = split_id(nid)
    if k != "subsystem" or symbol not in SUBSYSTEM_SYMBOLS:
        raise ValueError("symbol")
    if plant.node(name) is None:
        raise KeyError(name)
    plant.pfd = dict(plant.pfd or {})
    s = dict(plant.pfd.get("symbol", {}))
    s[nid] = symbol
    plant.pfd["symbol"] = s


def reset_layout(plant: Plant) -> None:
    plant.pfd = {k: v for k, v in (plant.pfd or {}).items() if k != "pos"}


def prune(plant: Plant) -> None:
    """Forget positions and symbols of nodes that no longer exist."""
    names = {f"subsystem:{s.name}" for s in plant.subsystems} | {f"source:{s.name}" for s in plant.sources} | \
            {f"outlet:{o.name}" for o in plant.outlets}
    fixed = ("evap:", "product:", "pool:", "loss:")
    for key in ("pos", "symbol"):
        d = (plant.pfd or {}).get(key)
        if d:
            plant.pfd[key] = {k: v for k, v in d.items() if k in names or k.startswith(fixed)}


# ---------------------------------------------------------------------------------------- editing: connect two nodes
def resolve_connection(a_id: str, b_id: str) -> Tuple[str, str, str]:
    """(flow kind, owning subsystem, reference) for a stream drawn from node a to node b (either order for the ends that are
    only ever one side). Raises ValueError for a combination that is not a water stream."""
    ka, na = split_id(a_id)
    kb, nb = split_id(b_id)
    if ka in ("outlet", "evap", "product", "pool") or (ka == "subsystem" and kb == "source"):
        ka, na, kb, nb = kb, nb, ka, na
    if ka == "source" and kb == "subsystem":
        return "intake", nb, na
    if ka == "subsystem" and kb == "subsystem":
        if na == nb:
            raise ValueError("a subsystem cannot send water to itself")
        return "transfer", na, nb
    if ka == "subsystem" and kb == "outlet":
        return "discharge", na, nb
    if ka == "subsystem" and kb in ("evap", "product"):
        return kb, na, ""
    raise ValueError("bad connection")


# ---------------------------------------------------------------------------------------- what belongs to a node
@dataclass
class NodeInfo:
    id: str
    kind: str
    name: str
    title: str
    rows: List[Tuple[str, object, str]] = field(default_factory=list)      # (i18n key, value, format) format: m3 cur pct num text
    lists: Dict[str, List[Tuple[str, object, str]]] = field(default_factory=dict)   # section key -> [(label, value, format)]
    subsystem: str = ""                                                      # name to open in the data editor, "" if none


def _measures_of(plant: Plant, names: List[str], lang: str) -> List[Tuple[str, object, str]]:
    from . import measures as M
    out = []
    root = {plant.root_of(n) for n in names}
    for it in plant.plan:
        if it.target and (it.target in names or it.target in root):
            try:
                m = M.get(it.measure_id)
                out.append((f"{m.id}. {m.name(lang)}", it.capex, "cur"))
            except Exception:                    # noqa: BLE001 - an unknown measure id must not break the panel
                out.append((str(it.measure_id), it.capex, "cur"))
    return out


def node_info(a: Analysis, nid: str, lang: str = "fa") -> Optional[NodeInfo]:
    from . import allocation as AL
    plant = a.plant
    kind, name = split_id(nid)
    info = NodeInfo(nid, kind, name, name)
    total_in = a.balance.sum_intake or 0.0
    if kind == "subsystem":
        s = plant.node(name)
        if s is None:
            return None
        info.subsystem = name
        names = [x.name for x in plant.leaves_of(name)] + [name]
        b = a.balance.nodes.get(name)
        c = a.cost.nodes.get(name)
        info.rows += [("pfd_i_kind", s.kind, "text"), ("pfd_i_intake", s.total_intake, "m3"),
                      ("pfd_i_share", 100.0 * s.total_intake / total_in if total_in > 0 else 0.0, "pct")]
        if b is not None:
            info.rows += [("pfd_i_outflow", b.outflow, "m3"), ("pfd_i_storage", b.storage_change, "m3"),
                          ("pfd_i_residual", b.unknown_loss, "m3"), ("pfd_i_sigma", b.sigma * 1.96, "m3"),
                          ("pfd_i_significant", "yes" if b.significant else "no", "flag"), ("pfd_i_status", b.status, "status")]
        if c is not None:
            info.rows += [("pfd_i_cost", c.total, "cur"), ("pfd_i_cost_m3", c.per_m3_intake, "cur3")]
        info.lists["pfd_s_intake"] = [(k, v, "m3") for k, v in s.intake.items()]
        info.lists["pfd_s_discharge"] = [(k, v, "m3") for k, v in s.discharge.items()]
        leaf_names = {x.name for x in plant.leaves_of(name)}
        al = {}
        for ln in leaf_names:
            for p_, f_ in AL.clean_fractions(plant.allocation.get(ln, {})).items():
                al[p_] = al.get(p_, 0.0) + f_ * 100.0 / len(leaf_names)
        info.lists["pfd_s_alloc"] = [(k, v, "pct") for k, v in al.items()]
        info.lists["pfd_s_measures"] = _measures_of(plant, names, lang)
        mt = [(m.name + (f" ±{m.accuracy_pct:g}%" if m.accuracy_pct else ""), m.tag, "text") for m in plant.site.meters
              if m.tag.startswith(f"sub:{name}:") or any(m.tag.startswith(f"sub:{n}:") for n in leaf_names)]
        info.lists["pfd_s_meters"] = mt
        info.rows.append(("pfd_i_pumps", sum(len(x.pumps) for x in plant.leaves_of(name)), "num"))
        if plant.has_children(name):
            info.lists["pfd_s_equipment"] = [(e.name, e.total_intake, "m3") for e in plant.children(name)]
    elif kind == "source":
        src = next((x for x in plant.sources if x.name == name), None)
        used = [(x.name, x.intake.get(name, 0.0), "m3") for x in plant.leaves() if x.intake.get(name, 0.0) > 0]
        tot = sum(v for _n, v, _f in used)
        info.rows += [("pfd_i_supplied", tot, "m3"), ("pfd_i_share", 100.0 * tot / total_in if total_in > 0 else 0.0, "pct")]
        if src is not None:
            info.rows += [("pfd_i_price", src.unit_cost, "cur3"), ("pfd_i_cost", src.unit_cost * tot, "cur")]
            if src.metered_m3:
                info.rows.append(("pfd_i_billed", src.metered_m3, "m3"))
        info.lists["pfd_s_users"] = used
        info.lists["pfd_s_meters"] = [(m.name + (f" ±{m.accuracy_pct:g}%" if m.accuracy_pct else ""), m.tag, "text")
                                      for m in plant.site.meters if m.tag == f"source:{name}"]
    elif kind == "outlet":
        out = next((x for x in plant.outlets if x.name == name), None)
        used = [(x.name, x.discharge.get(name, 0.0), "m3") for x in plant.leaves() if x.discharge.get(name, 0.0) > 0]
        tot = sum(v for _n, v, _f in used)
        info.rows += [("pfd_i_discharged", tot, "m3")]
        if out is not None:
            info.rows += [("pfd_i_price", out.unit_cost, "cur3"), ("pfd_i_cost", out.unit_cost * tot, "cur")]
        info.lists["pfd_s_users"] = used
        info.lists["pfd_s_meters"] = [(m.name + (f" ±{m.accuracy_pct:g}%" if m.accuracy_pct else ""), m.tag, "text")
                                      for m in plant.site.meters if m.tag == f"outlet:{name}"]
    elif kind in ("evap", "product"):
        key = "evaporation" if kind == "evap" else "product"
        used = [(x.name, getattr(x, key), "m3") for x in plant.leaves() if getattr(x, key) > 0]
        info.rows.append(("pfd_i_total", sum(v for _n, v, _f in used), "m3"))
        info.lists["pfd_s_users"] = used
    elif kind in ("pool", "loss"):
        used = []
        for x in plant.leaves():
            if kind == "pool":
                rest = x.to_other - sum(l.volume for l in plant.links if l.src == x.name)
                if rest > 1e-6:
                    used.append((x.name, rest, "m3"))
            else:
                b = a.balance.nodes.get(x.name)
                if b and b.unknown_loss > 0:
                    used.append((x.name, b.unknown_loss, "m3"))
        info.rows.append(("pfd_i_total", sum(v for _n, v, _f in used), "m3"))
        info.lists["pfd_s_users"] = used
    else:
        return None
    return info
