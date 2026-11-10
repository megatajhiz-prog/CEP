"""Three levels: site -> unit -> equipment. A unit with equipment is the sum of them; plant totals never double count."""

from datetime import date

import pytest

from waterprofiler import flow as F
from waterprofiler import indicators as K
from waterprofiler import measures as M
from waterprofiler import periodview as PV
from waterprofiler import structure as ST
from waterprofiler import timeseries as T
from waterprofiler.analysis import analyse
from waterprofiler.model import Meter, Outlet, Plant, PlanItem, Point, Product, Site, Source, Subsystem, Transfer
from waterprofiler.reconcile import reconcile


def plant() -> Plant:
    p = Plant(
        name="t", production_per_year=1000.0, production_unit="t", currency="IRR",
        site=Site(products=[Product("P", "t", per_year=1000.0)]),
        sources=[Source("A", 2.0, metered_m3=1000.0), Source("B", 4.0)], outlets=[Outlet("S", 3.0, metered_m3=450.0)],
        subsystems=[
            Subsystem("X", "process", intake={"A": 600.0}, recirculated=200.0, product=100.0, discharge={"S": 400.0}),
            Subsystem("Y", "cooling_tower", intake={"A": 400.0}, evaporation=300.0, discharge={"S": 50.0},
                      params={"mc": 300.0, "bc": 1200.0}),
        ])
    p.profile.sub_production = {"X": 1000.0}
    return p


def totals(p):
    a = analyse(p)
    return (a.balance.sum_intake, a.balance.sum_discharge, a.balance.sum_evaporation, a.balance.sum_product,
            a.balance.unknown_loss, a.cost.total, a.kpi.recirculation_ratio)


def test_splitting_a_unit_keeps_every_total():
    p0 = plant()
    base = totals(p0)
    p = plant()
    eq = ST.add_equipment(p, "X", "Line 1", "process")
    eq2 = ST.add_equipment(p, "X", "Line 2", "process")
    holder = p.node("X · unallocated")
    assert holder is not None and holder.parent == "X"
    # move half of the holder's flows to the new equipment
    for k in ("intake", "discharge"):
        for n, v in list(getattr(holder, k).items()):
            getattr(holder, k)[n] = v / 2
            getattr(eq, k)[n] = v / 4
            getattr(eq2, k)[n] = v / 4
    holder.product, eq.product, eq2.product = 50.0, 25.0, 25.0
    holder.recirculated, eq.recirculated, eq2.recirculated = 100.0, 50.0, 50.0
    assert totals(p) == pytest.approx(base)
    u = p.node("X")
    assert u.total_intake == pytest.approx(600) and u.product == pytest.approx(100) and u.recirculated == pytest.approx(200)
    assert [s.name for s in p.units()] == ["X", "Y"]
    assert {s.name for s in p.leaves()} == {"X · unallocated", "Line 1", "Line 2", "Y"}


def test_first_equipment_takes_over_what_the_unit_carried():
    p = plant()
    p.series["sub:X:intake"] = [Point("2025-01-01", "2025-12-31", 600.0)]
    p.links.append(Transfer("X", "Y", 50.0))
    T_ = ST
    T_.add_equipment(p, "X", "Line 1")
    h = p.node("X · unallocated")
    assert h.intake == {"A": 600.0} and h.params == {} and h.discharge == {"S": 400.0}
    assert p.node("X").params == {} and p.node("X").pumps == []
    assert p.links[0].src == "X · unallocated"
    assert p.profile.sub_production.get("X") == 1000.0           # the unit's production is now the sum of its equipment
    assert p.profile.sub_production.get("X · unallocated") == 1000.0
    assert not [k for k in p.series if k.startswith("sub:X:")]


def test_transfer_inside_a_unit_is_internal():
    p = plant()
    a = ST.add_equipment(p, "X", "A1")
    b = ST.add_equipment(p, "X", "B1")
    h = p.node("X · unallocated")
    before = totals(p)
    p.links.append(Transfer("A1", "B1", 30.0))
    a.to_other = 30.0
    b.from_other = 30.0
    b.intake = {}                       # untouched; keeps the balances of the other nodes
    # A1 sends 30 it does not receive from anywhere: give it an intake of 30, and B1 uses it for a product of 30
    a.intake = {"A": 30.0}
    b.product = 30.0
    u = p.node("X")
    p.rollup()
    assert u.to_other == 0 and u.from_other == 0                         # internal: not a transfer of the unit
    assert u.recirculated == pytest.approx(h.recirculated + 30.0)         # but it is the unit's internal reuse
    bal = analyse(p).balance
    assert not [w for w in bal.warnings if "transfers do not cancel" in w]
    assert bal.sum_intake == pytest.approx(before[0] + 30.0)


def test_transfer_between_units_goes_through_the_units():
    p = plant()
    p.node("Y").discharge = {"S": 50.0}
    ST.add_equipment(p, "X", "L1")
    ST.add_equipment(p, "Y", "T1")
    p.links.append(Transfer("L1", "Y · unallocated", 10.0))
    from waterprofiler.model import sync_transfers
    sync_transfers(p)
    p.rollup()
    assert p.node("X").to_other == 10.0 and p.node("Y").from_other == 10.0
    g = F.build_flow(analyse(p), {"evap": "E", "product": "P", "loss": "L", "pool": "Pool"})
    assert {n.name for n in g.nodes if n.kind == "subsystem"} == {"X", "Y"}
    assert any(e.kind == "transfer" and e.src == "subsystem:X" and e.dst == "subsystem:Y" for e in g.edges)
    with pytest.raises(ValueError):
        F.set_flow(p, "intake", "X", "A", 5.0)                        # derived: edit the equipment


def test_depth_is_three_levels_and_names_are_unique():
    p = plant()
    ST.add_equipment(p, "X", "L1")
    with pytest.raises(ValueError):
        ST.add_equipment(p, "L1", "deeper")
    with pytest.raises(ValueError):
        ST.add_equipment(p, "X", "Y")
    with pytest.raises(ValueError):
        ST.add_equipment(p, "X", "  ")
    p.subsystems[-1].parent = "L1"                                   # a hand-edited deeper tree is repaired on load
    q = Plant.from_dict(p.to_dict())
    assert all(not s.parent or q.node(s.parent).parent == "" for s in q.subsystems)


def test_old_files_load_unchanged_and_new_ones_round_trip():
    d = plant().to_dict()
    for s in d["subsystems"]:
        s.pop("parent", None)
    q = Plant.from_dict(d)
    assert all(s.parent == "" for s in q.subsystems)
    assert totals(q) == pytest.approx(totals(plant()))
    p = plant()
    ST.add_equipment(p, "X", "L1")
    r = Plant.from_dict(p.to_dict())
    assert r.node("L1").parent == "X" and r.has_children("X")


def test_rename_follows_every_reference():
    p = plant()
    ST.add_equipment(p, "X", "L1")
    p.plan.append(PlanItem(1, "L1", 10.0))
    p.series["sub:L1:intake"] = [Point("2025-01-01", "2025-01-31", 5.0)]
    p.site.meters.append(Meter("m", "sub:L1:intake"))
    p.layout["subsystem:X"] = 1.0
    p.links.append(Transfer("L1", "Y", 1.0))
    ST.rename_node(p, "L1", "Line 1")
    ST.rename_node(p, "X", "Unit X")
    assert p.node("Line 1").parent == "Unit X" and p.node("X") is None
    assert "sub:Line 1:intake" in p.series and p.site.meters[0].tag == "sub:Line 1:intake"
    assert p.plan[0].target == "Line 1" and "subsystem:Unit X" in p.layout
    assert p.links[0].src == "Line 1"
    with pytest.raises(ValueError):
        ST.rename_node(p, "Line 1", "Y")


def test_removing_the_last_equipment_leaves_an_empty_unit():
    p = plant()
    ST.add_equipment(p, "X", "L1")
    ST.remove_node(p, "X · unallocated")
    assert p.has_children("X")
    ST.remove_node(p, "L1")
    u = p.node("X")
    assert not p.has_children("X") and u.total_intake == 0 and u.product == 0
    ST.add_equipment(p, "Y", "T1")
    ST.remove_node(p, "Y")
    assert p.node("Y") is None and p.node("T1") is None and p.node("Y · unallocated") is None


def test_move_equipment_between_units():
    p = plant()
    eq = ST.add_equipment(p, "X", "L1")
    eq.intake = {"A": 10.0}
    ST.move_equipment(p, "L1", "Y")
    assert eq.parent == "Y" and "Y · unallocated" in {s.name for s in p.subsystems}
    assert p.node("X").total_intake == pytest.approx(600.0)               # the holder keeps X's own water
    assert p.node("Y").total_intake == pytest.approx(410.0)


def test_series_of_a_unit_is_the_sum_of_its_equipment_and_is_not_entered():
    p = plant()
    ST.add_equipment(p, "X", "L1")
    h = p.node("X · unallocated")
    d0, d1 = date(2025, 1, 1), date(2025, 1, 31)
    T.put(p, "sub:L1:intake", d0, d1, 10.0)
    T.put(p, f"sub:{h.name}:intake", d0, d1, 90.0)
    with pytest.raises(ValueError):
        T.put(p, "sub:X:intake", d0, d1, 1.0)
    assert T.spec_of(p, "sub:X:intake").derived
    from waterprofiler import jcalendar as C
    sl = C.slices(d0, d1, "month", "gregorian", "en")
    assert T.slice_values(p, "sub:X:intake", sl) == [pytest.approx(100.0)]
    ok, bad = T.from_rows(p, [["sub:X:intake", "2025-01-01", "2025-01-31", "5"]])
    assert ok == 0 and len(bad) == 1
    ch = T.plan_changes(p, d0, d1)
    assert not [c for c in ch if c.key.startswith("sub:X:")]


def test_series_driven_equipment_flows_roll_up_into_the_unit():
    p = plant()
    ST.add_equipment(p, "X", "L1")
    d0, d1 = date(2025, 1, 1), date(2025, 12, 31)
    T.put(p, "sub:L1:evaporation", d0, d1, 40.0)
    T.sync(p)
    assert p.node("L1").evaporation == pytest.approx(40.0)
    assert p.node("X").evaporation == pytest.approx(40.0)


def test_reconcile_works_on_equipment_and_keeps_units_in_step():
    p = plant()
    ST.add_equipment(p, "X", "L1").intake = {"A": 20.0}
    r = reconcile(p).plant
    for u in r.units():
        kids = r.children(u.name)
        if kids:
            assert u.total_intake == pytest.approx(sum(c.total_intake for c in kids))
    assert sum(s.total_intake for s in r.leaves()) == pytest.approx(1000.0, rel=0.05)


def test_plan_on_a_unit_and_its_equipment_does_not_count_twice():
    p = plant()
    ST.add_equipment(p, "Y", "T1", "cooling_tower")
    ST.add_equipment(p, "Y", "T2", "cooling_tower")
    p.node("T1").intake = {"A": 150.0}
    p.node("T2").intake = {"A": 150.0}
    p.node("Y · unallocated").intake = {"A": 100.0}
    mid = M.all_measures()[0].id
    p.plan = [PlanItem(mid, "T1", 10.0), PlanItem(mid, "Y", 10.0)]
    res = M.evaluate_plan(p)
    assert "nested:Y" in res.warnings
    # T1 saves 15; the unit's base is 400 - 15 = 385 -> 38.5 more; never more than the unit's 10 % + the first 10 %
    assert res.saving == pytest.approx(15.0 + 38.5)


def test_indicators_and_period_view_run_on_a_tree():
    p = plant()
    ST.add_equipment(p, "X", "L1").intake = {"A": 5.0}
    ind = K.compute(p)
    assert ind.get("sup_intake").value == pytest.approx(1005.0)
    names = [r.name for r in ind.subsystems]
    assert names.index("X") < names.index("L1") < names.index("Y")
    T.put(p, "sub:L1:intake", date(2025, 1, 1), date(2025, 3, 31), 20.0)
    q, info = PV.period_plant(p, date(2025, 1, 1), date(2025, 3, 31))
    assert q.node("L1").total_intake > 0
    assert q.node("X").total_intake == pytest.approx(sum(c.total_intake for c in q.children("X")))
