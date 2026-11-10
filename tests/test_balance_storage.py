"""Water balance with the change of stored volume (dS) and the uncertainty of the residual."""

import math
from datetime import date

import pytest

from waterprofiler import periodview as PV
from waterprofiler import structure as ST
from waterprofiler import timeseries as T
from waterprofiler import uncertainty as U
from waterprofiler.analysis import analyse
from waterprofiler.balance import plant_balance, subsystem_balance
from waterprofiler.model import Meter, Outlet, Plant, Site, Source, Subsystem
from waterprofiler.reconcile import reconcile


def plant(ds=0.0) -> Plant:
    return Plant(name="t", production_per_year=1.0, production_unit="t",
                 sources=[Source("A", 1.0)], outlets=[Outlet("S", 1.0)],
                 subsystems=[Subsystem("X", "process", intake={"A": 100.0}, product=20.0, evaporation=40.0,
                                       discharge={"S": 10.0}, storage_change=ds)])


def test_storage_change_enters_the_residual():
    p = plant(ds=30.0)
    b = plant_balance(p)
    assert b.subsystems[0].unknown_loss == pytest.approx(100 - 70 - 30)
    assert b.unknown_loss == pytest.approx(0.0) and b.sum_storage == 30.0
    assert b.subsystems[0].status == "balanced"
    assert plant_balance(plant()).unknown_loss == pytest.approx(30.0)     # without dS the same water is "lost"


def test_storage_change_in_plant_meter_imbalance():
    p = plant(ds=30.0)
    p.sources[0].metered_m3 = 100.0
    p.outlets[0].metered_m3 = 10.0
    b = plant_balance(p)
    assert b.plant_imbalance == pytest.approx(100 - 10 - 40 - 20 - 30)


def test_units_sum_storage_change_and_equipment_carry_it():
    p = plant(ds=0.0)
    a = ST.add_equipment(p, "X", "L1")
    a.storage_change = 8.0
    p.rollup()
    assert p.node("X").storage_change == pytest.approx(8.0)
    assert plant_balance(p).sum_storage == pytest.approx(8.0)
    ST.remove_node(p, "L1")
    assert p.node("X").storage_change == 0.0


def test_storage_series_is_a_variable_and_can_be_negative():
    p = plant()
    d0, d1 = date(2025, 1, 1), date(2025, 12, 31)
    assert T.spec_of(p, "sub:X:storage") is not None
    T.put(p, "sub:X:storage", d0, d1, -12.0)
    T.sync(p)
    assert p.node("X").storage_change == pytest.approx(-12.0)
    ST.add_equipment(p, "X", "L1")
    assert T.spec_of(p, "sub:X:storage").derived
    q, _ = PV.period_plant(p, d0, d1)
    assert q.node("X").storage_change == pytest.approx(sum(c.storage_change for c in q.children("X")))


def test_sigma_from_default_and_from_meters():
    p = plant()
    s = p.subsystems[0]
    assert U.node_sigma(p, s) == pytest.approx(math.sqrt(10 ** 2 + 2 ** 2 + 4 ** 2 + 1 ** 2))   # 10 % of each flow
    b = plant_balance(p)
    assert b.subsystems[0].unknown_loss == pytest.approx(30.0) and b.subsystems[0].significant
    p.site.meters = [Meter("m1", "sub:X:intake", accuracy_pct=1.0), Meter("m2", "sub:X:evaporation", accuracy_pct=2.0),
                     Meter("m3", "sub:X:product", accuracy_pct=2.0), Meter("m4", "sub:X:discharge", accuracy_pct=1.0)]
    assert U.node_sigma(p, s) == pytest.approx(math.sqrt(1.0 ** 2 + 0.4 ** 2 + 0.8 ** 2 + 0.1 ** 2))
    p.profile.unmetered_unc_pct = 40.0
    p.site.meters = []
    assert U.node_sigma(p, s) == pytest.approx(math.sqrt(40 ** 2 + 8 ** 2 + 16 ** 2 + 4 ** 2))
    assert not plant_balance(p).subsystems[0].significant                 # now within the assumed error


def test_plant_sigma_uses_source_and_outlet_meters_and_reports_unmetered_share():
    p = plant()
    p.site.meters = [Meter("src", "source:A", accuracy_pct=1.0), Meter("out", "outlet:S", accuracy_pct=1.0)]
    sig, unmet = U.plant_sigma(p)
    assert sig == pytest.approx(math.sqrt(1.0 ** 2 + 0.1 ** 2 + 2 ** 2 + 4 ** 2))    # evaporation and product stay at 10 %
    assert unmet == pytest.approx(60.0 / 170.0)
    assert plant_balance(p).sigma == pytest.approx(sig)


def test_unit_sigma_is_the_root_sum_of_squares_of_its_equipment():
    p = plant()
    a = ST.add_equipment(p, "X", "L1")
    b = ST.add_equipment(p, "X", "L2")
    a.intake, a.product = {"A": 50.0}, 10.0
    b.intake, b.product = {"A": 50.0}, 10.0
    p.node("X · unallocated").intake = {}
    expected = math.sqrt(U.node_sigma(p, a) ** 2 + U.node_sigma(p, b) ** 2 + U.node_sigma(p, p.node("X · unallocated")) ** 2)
    assert U.node_sigma(p, p.node("X")) == pytest.approx(expected)


def test_reconcile_closes_each_node_to_its_storage_change():
    p = plant(ds=10.0)
    r = reconcile(p).plant
    s = r.subsystems[0]
    assert s.total_intake - (s.product + s.evaporation + s.total_discharge) == pytest.approx(10.0, abs=1e-6)


def test_reconcile_uses_a_stated_meter_accuracy_as_its_sigma():
    p = plant()
    p.site.meters = [Meter("m", "sub:X:intake", accuracy_pct=0.1)]        # intake is nearly exact: the others move instead
    r = reconcile(p)
    assert r.plant.subsystems[0].total_intake == pytest.approx(100.0, rel=0.01)


def test_old_files_load_without_storage_and_with_default_uncertainty():
    d = plant().to_dict()
    for s in d["subsystems"]:
        s.pop("storage_change", None)
    d["profile"].pop("unmetered_unc_pct", None)
    q = Plant.from_dict(d)
    assert q.subsystems[0].storage_change == 0.0 and q.profile.unmetered_unc_pct == 10.0
    assert Plant.from_dict(plant(ds=3.0).to_dict()).subsystems[0].storage_change == 3.0
    a = analyse(q)
    assert a.balance.sigma > 0
