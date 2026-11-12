import pytest
from waterprofiler import pfd as P, structure as ST
from waterprofiler.analysis import analyse
from waterprofiler.model import Plant, Subsystem, Source, Outlet, Transfer, PlanItem
from waterprofiler.sample import demo_with_history

LAB = {"evap": "Evaporation", "product": "Product", "loss": "Residual", "pool": "Transfer"}


def _build(p):
    return analyse(p), P.build_pfd(analyse(p), LAB)


def test_demo_graph_is_complete_and_edges_match_the_data():
    p = demo_with_history("en")
    a, g = _build(p)
    assert all(e.src in g.nodes and e.dst in g.nodes for e in g.edges)
    for s in p.leaves():
        assert g.nodes[f"subsystem:{s.name}"].volume == pytest.approx(
            max(sum(e.volume for e in g.edges if e.dst == f"subsystem:{s.name}"),
                sum(e.volume for e in g.edges if e.src == f"subsystem:{s.name}")))
    intake = sum(e.volume for e in g.edges if e.kind == "intake")
    assert intake == pytest.approx(sum(s.total_intake for s in p.leaves()))
    # no two nodes of one column overlap
    top = [n for n in g.nodes.values() if not n.parent]
    for i, a_ in enumerate(top):
        for b_ in top[i + 1:]:
            assert a_.x != b_.x or abs(a_.y - b_.y) >= a_.h - 1e-9


def test_unit_with_equipment_becomes_a_container():
    p = demo_with_history("en")
    unit = p.units()[0].name
    ST.add_equipment(p, unit, "Kiln")
    ST.add_equipment(p, unit, "Mixer")
    a, g = _build(p)
    c = g.nodes[f"subsystem:{unit}"]
    assert c.container and len(c.children) == 3 and c.symbol == "unit"
    for cid in c.children:
        n = g.nodes[cid]
        assert n.parent == c.id and 0 <= n.x and n.x + n.w <= c.w and 0 <= n.y and n.y + n.h <= c.h
    # streams end at the equipment that carry the data, never at the container
    assert all(not g.nodes[e.dst].container and not g.nodes[e.src].container for e in g.edges if e.kind != "transfer")
    assert c.volume == pytest.approx(sum(g.nodes[x].volume for x in c.children))
    assert g.absolute(c.children[1])[0] > g.absolute(c.id)[0]


def test_positions_and_symbols_persist_and_prune():
    p = demo_with_history("en")
    nid = f"subsystem:{p.units()[0].name}"
    P.set_position(p, nid, 12.34, 56.78)
    P.set_symbol(p, nid, "tank")
    P.set_position(p, "subsystem:Ghost", 1, 1)
    q = Plant.from_dict(p.to_dict())
    _a, g = _build(q)
    assert (g.nodes[nid].x, g.nodes[nid].y, g.nodes[nid].symbol) == (12.3, 56.8, "tank")
    P.prune(q)
    assert "subsystem:Ghost" not in q.pfd["pos"] and nid in q.pfd["pos"]
    with pytest.raises(ValueError):
        P.set_symbol(q, nid, "rocket")
    with pytest.raises(KeyError):
        P.set_symbol(q, "subsystem:Ghost", "tank")
    P.reset_layout(q)
    assert "pos" not in q.pfd and q.pfd["symbol"][nid] == "tank"


def test_resolve_connection_covers_every_water_stream():
    assert P.resolve_connection("source:W", "subsystem:A") == ("intake", "A", "W")
    assert P.resolve_connection("subsystem:A", "source:W") == ("intake", "A", "W")
    assert P.resolve_connection("subsystem:A", "subsystem:B") == ("transfer", "A", "B")
    assert P.resolve_connection("subsystem:A", "outlet:S") == ("discharge", "A", "S")
    assert P.resolve_connection("outlet:S", "subsystem:A") == ("discharge", "A", "S")
    assert P.resolve_connection("subsystem:A", "evap:E") == ("evap", "A", "")
    assert P.resolve_connection("product:P", "subsystem:A") == ("product", "A", "")
    for bad in (("source:W", "outlet:S"), ("subsystem:A", "subsystem:A"), ("evap:E", "product:P")):
        with pytest.raises(ValueError):
            P.resolve_connection(*bad)


def test_transfers_and_pool_edges():
    p = Plant(name="t", sources=[Source("W", 1.0)], outlets=[Outlet("O", 0.0)])
    p.subsystems = [Subsystem(name="A", intake={"W": 1000.0}, to_other=400.0, evaporation=100.0, discharge={"O": 500.0}),
                    Subsystem(name="B", from_other=300.0, discharge={"O": 300.0})]
    p.links = [Transfer("A", "B", 300.0)]
    _a, g = _build(p)
    tr = [(e.src, e.dst, e.volume) for e in g.edges if e.kind == "transfer"]
    assert ("subsystem:A", "subsystem:B", 300.0) in tr
    assert any(d.startswith("pool:") and v == pytest.approx(100.0) for _s, d, v in tr)      # the undefined rest stays visible


def test_node_info_for_every_kind():
    p = demo_with_history("en")
    a = analyse(p)
    g = P.build_pfd(a, LAB)
    for nid, n in g.nodes.items():
        info = P.node_info(a, nid, "en")
        assert info is not None and info.rows
    unit = p.units()[0].name
    info = P.node_info(a, f"subsystem:{unit}", "en")
    rows = {k: v for k, v, _f in info.rows}
    assert rows["pfd_i_intake"] == pytest.approx(p.node(unit).total_intake)
    assert rows["pfd_i_cost"] > 0 and info.subsystem == unit
    src = P.node_info(a, f"source:{p.sources[0].name}", "en")
    assert dict((k, v) for k, v, _f in src.rows)["pfd_i_supplied"] == pytest.approx(
        sum(s.intake.get(p.sources[0].name, 0.0) for s in p.leaves()))
    assert P.node_info(a, "subsystem:Ghost", "en") is None and P.node_info(a, "weird:x", "en") is None


def test_node_info_shows_measures_allocation_and_equipment():
    p = demo_with_history("en")
    unit = p.plan[0].target or p.units()[0].name
    info = P.node_info(analyse(p), f"subsystem:{unit}", "en")
    assert any(True for _ in info.lists["pfd_s_measures"]) or not p.plan[0].target
    ST.add_equipment(p, unit, "Kiln")
    info = P.node_info(analyse(p), f"subsystem:{unit}", "en")
    assert len(info.lists["pfd_s_equipment"]) == 2
