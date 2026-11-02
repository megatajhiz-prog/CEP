from waterprofiler.analysis import analyse
from waterprofiler.flow import build_flow
from waterprofiler.model import Plant, Transfer, sync_transfers
from waterprofiler.sample import demo_plant
from waterprofiler.storage import load_project, save_project

LAB = {"evap": "E", "product": "P", "loss": "L", "pool": "T"}


def _moved_plant():
    p = demo_plant("en")
    ct, irr = p.subsystems[1], p.subsystems[4]
    sewer = next(iter(ct.discharge))
    well = next(iter(irr.intake))
    ct.discharge[sewer] -= 1500
    irr.intake[well] -= 1500
    p.links = [Transfer(ct.name, irr.name, 1500)]
    sync_transfers(p)
    return p


def test_demo_graph_conserves_volume():
    a = analyse(demo_plant("en"))
    g = build_flow(a, LAB)
    for n in g.nodes:
        if n.kind == "subsystem":
            ins = sum(e.volume for e in g.edges if e.dst == n.id)
            outs = sum(e.volume for e in g.edges if e.src == n.id)
            assert abs(ins - outs) < 1e-6 * max(ins, 1)
    assert {n.kind for n in g.nodes} >= {"source", "subsystem", "outlet", "evap", "product"}
    assert not any(e.kind == "transfer" for e in g.edges)


def test_links_sync_and_draw_transfer():
    p = _moved_plant()
    ct, irr = p.subsystems[1], p.subsystems[4]
    assert ct.to_other == 1500 and irr.from_other == 1500
    a = analyse(p)
    assert all(abs(s.unknown_loss) < 1e-6 for s in a.balance.subsystems)
    g = build_flow(a, LAB)
    tr = [e for e in g.edges if e.kind == "transfer"]
    assert len(tr) == 1 and tr[0].src == f"subsystem:{ct.name}" and tr[0].dst == f"subsystem:{irr.name}"
    assert abs(tr[0].volume - 1500) < 1e-9


def test_transfer_without_link_goes_to_pool():
    p = demo_plant("en")
    p.subsystems[1].to_other = 400.0           # R'_out set but no destination given
    g = build_flow(analyse(p), LAB)
    pool = [e for e in g.edges if e.kind == "transfer"]
    assert len(pool) == 1 and pool[0].dst == "pool:T" and abs(pool[0].volume - 400) < 1e-9


def test_removing_links_clears_transfers():
    p = _moved_plant()
    old = {x.src for x in p.links} | {x.dst for x in p.links}
    p.links = []
    sync_transfers(p, touched=old)
    assert p.subsystems[1].to_other == 0 and p.subsystems[4].from_other == 0


def test_links_round_trip(tmp_path):
    p = _moved_plant()
    f = tmp_path / "x.wpj"
    save_project(p, str(f))
    q = load_project(str(f))
    assert [(x.src, x.dst, x.volume) for x in q.links] == [(x.src, x.dst, x.volume) for x in p.links]
    assert Plant.from_dict({"name": "old"}).links == []


def test_report_embeds_flow_picture():
    from waterprofiler.report_html import build_report_html
    html = build_report_html(analyse(demo_plant("fa")), "fa", flow="flow")
    assert "src='flow'" in html


# ---------------------------------------------------------------- interactive editing (engine part)
def test_set_add_delete_flow_and_transfer_sync():
    import pytest
    from waterprofiler import flow as F
    p = demo_plant("en")
    boiler, ct = p.subsystems[2], p.subsystems[1]
    src = next(iter(boiler.intake))
    base = boiler.intake[src]
    F.set_flow(p, "intake", boiler.name, src, base + 100)
    assert boiler.intake[src] == base + 100
    F.add_flow(p, "intake", boiler.name, src, 50)
    assert boiler.intake[src] == base + 150
    F.delete_flow(p, "intake", boiler.name, src)
    assert src not in boiler.intake
    F.add_flow(p, "transfer", ct.name, boiler.name, 700)
    F.add_flow(p, "transfer", ct.name, boiler.name, 300)
    assert [(x.src, x.dst, x.volume) for x in p.links] == [(ct.name, boiler.name, 1000.0)]
    assert ct.to_other == 1000 and boiler.from_other == 1000
    F.delete_flow(p, "transfer", ct.name, boiler.name)
    assert p.links == [] and ct.to_other == 0 and boiler.from_other == 0
    F.set_flow(p, "evap", ct.name, "", 123.0)
    assert ct.evaporation == 123.0
    with pytest.raises(KeyError):
        F.set_flow(p, "intake", boiler.name, "no such source", 1.0)
    with pytest.raises(ValueError):
        F.set_flow(p, "transfer", ct.name, ct.name, 5.0)
    with pytest.raises(ValueError):
        F.set_flow(p, "evap", ct.name, "", -1.0)


def test_edge_identity_and_layout_roundtrip(tmp_path):
    from waterprofiler import flow as F
    p = _moved_plant()
    g = build_flow(analyse(p), LAB)
    tr = [e for e in g.edges if e.kind == "transfer"]
    assert tr and tr[0].sub == p.subsystems[1].name and tr[0].ref == p.subsystems[4].name
    for e in g.edges:
        if e.editable:
            assert abs(F.current_volume(p, e.kind, e.sub, e.ref) - e.volume) < 1e-6 or e.kind == "transfer"
    p.layout = {"subsystem:" + p.subsystems[0].name: 900.0}
    f = tmp_path / "x.wpj"
    save_project(p, str(f))
    assert load_project(str(f)).layout == p.layout
    assert build_flow(analyse(p), LAB).layout == p.layout
