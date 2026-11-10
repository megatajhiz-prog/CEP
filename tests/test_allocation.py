"""Allocation of water and cost to products."""
import pytest
from waterprofiler.analysis import analyse
from waterprofiler.allocation import allocate, METRICS
from waterprofiler.model import Plant, Subsystem, Source, Outlet, Product
from waterprofiler import structure as ST
from waterprofiler.sample import demo_plant


def _plant():
    p = Plant(name="t", sources=[Source("W", 2.0)], outlets=[Outlet("O", 0.5)])
    p.subsystems = [
        Subsystem(name="Line A", intake={"W": 600.0}, product=100.0, evaporation=100.0, discharge={"O": 400.0}),
        Subsystem(name="Line B", intake={"W": 300.0}, product=50.0, evaporation=50.0, discharge={"O": 200.0}),
        Subsystem(name="Utilities", intake={"W": 100.0}, evaporation=100.0),
    ]
    p.site.products = [Product("Steel", "t", per_year=100.0), Product("Pipes", "piece", per_year=1000.0)]
    p.allocation = {"Line A": {"Steel": 100.0}, "Line B": {"Pipes": 100.0}}
    return p


def _check_identity(a):
    for m in METRICS:
        s = sum(x.total(m) for x in a.products) + a.unallocated[m]
        assert s == pytest.approx(a.totals[m])


def test_direct_and_spread():
    p = _plant()
    a = allocate(p, analyse(p).cost)
    st, pi = a.product("Steel"), a.product("Pipes")
    assert st.direct["intake"] == 600 and pi.direct["intake"] == 300
    assert st.spread["intake"] == pytest.approx(100 * 600 / 900)       # utilities in proportion to direct water
    assert st.intake_per_unit == pytest.approx((600 + 100 * 600 / 900) / 100)
    assert pi.intake_per_unit == pytest.approx((300 + 100 * 300 / 900) / 1000)
    assert a.coverage_pct == pytest.approx(100 * 900 / 1000)
    assert a.nodes_without_share == ["Utilities"]
    _check_identity(a)


def test_no_spread_leaves_remainder_unallocated():
    p = _plant()
    p.alloc_spread = False
    a = allocate(p, analyse(p).cost)
    assert a.unallocated["intake"] == pytest.approx(100.0) and a.product("Steel").spread["intake"] == 0
    _check_identity(a)


def test_partial_shares_and_overshoot():
    p = _plant()
    p.allocation["Line A"] = {"Steel": 50.0, "Pipes": 30.0}              # 20 % serves everything
    a = allocate(p, analyse(p).cost)
    assert a.product("Pipes").direct["intake"] == pytest.approx(300 + 0.3 * 600)
    _check_identity(a)
    p.allocation["Line A"] = {"Steel": 90.0, "Pipes": 60.0}              # 150 % -> scaled to 100 %
    a = allocate(p, analyse(p).cost)
    assert any("scaled down" in w for w in a.warnings)
    _check_identity(a)


def test_cost_is_allocated_too():
    p = _plant()
    c = analyse(p).cost
    a = allocate(p, c)
    assert a.totals["cost"] == pytest.approx(c.total) and a.product("Steel").cost_per_unit > 0


def test_unit_with_equipment_uses_equipment_shares_and_migrates():
    p = _plant()
    ST.add_equipment(p, "Line A", "Furnace")             # data of Line A moves to the holder, with its shares
    holder = "Line A · unallocated"
    assert p.allocation.get(holder) == {"Steel": 100.0} and "Line A" not in p.allocation
    a = allocate(p, analyse(p).cost)
    assert a.product("Steel").direct["intake"] == 600
    ST.rename_node(p, "Line B", "Line Z")
    assert "Line Z" in p.allocation
    ST.remove_node(p, "Line Z")
    assert "Line Z" not in p.allocation
    _check_identity(allocate(p, analyse(p).cost))


def test_mixed_units_have_no_plant_total():
    p = _plant()
    assert p.production_units_mixed() and p.sync_production() == 0.0
    p.site.products[1].unit = "t"
    assert not p.production_units_mixed() and p.sync_production() == 1100.0


def test_roundtrip_and_old_files():
    p = _plant()
    q = Plant.from_dict(p.to_dict())
    assert q.allocation == p.allocation and q.alloc_spread
    d = p.to_dict()
    d.pop("allocation"); d.pop("alloc_spread")
    assert Plant.from_dict(d).allocation == {}


def test_demo_plant_runs():
    p = demo_plant("fa")
    a = analyse(p).allocation
    assert a is not None and all(x.intake_per_unit is None or x.intake_per_unit >= 0 for x in a.products)
