"""Fixes from the ORNL benchmark: reconcile sanity checks, partial metering, significance of the boundary imbalance."""
import pytest

from waterprofiler import balance, reconcile
from waterprofiler.messages import localize
from waterprofiler.model import Meter, Outlet, Plant, Site, Source, Subsystem
from waterprofiler.sample import demo_plant, ornl_pilot3

approx = pytest.approx


def _two(src_meter=None, out_meter=None, discharge=90.0, evap=10.0):
    a = Subsystem("A", intake={"S": 100.0}, evaporation=evap, discharge={"O": discharge})
    return Plant(sources=[Source("S", 1.0, src_meter)], outlets=[Outlet("O", 1.0, out_meter)], subsystems=[a])


# ---------------------------------------------------------------- 1) reconcile sanity checks
def test_consistent_data_gives_no_warning():
    p = demo_plant()
    p.subsystems[1].evaporation *= 1.03
    r = reconcile.reconcile(p, use_meters=False)
    assert r.consistent and not r.warnings and r.dof > 0


def test_conflicting_meter_is_flagged_not_silently_absorbed():
    p = demo_plant()
    p.sources[0].metered_m3 = p.sources[0].metered_m3 * 3.0          # a meter that contradicts all the subsystems
    r = reconcile.reconcile(p, use_meters=True)
    assert not r.consistent and r.suspects
    assert any("exceeds the 95 %" in w or "cannot be closed" in w for w in r.warnings)


def test_limit_on_relative_change_holds_and_reports_conflict():
    p = demo_plant()
    p.sources[0].metered_m3 = p.sources[0].metered_m3 * 3.0
    r = reconcile.reconcile(p, use_meters=True, max_rel_change=0.5)
    for s0, s1 in zip(p.subsystems, r.plant.subsystems):
        for k, v in s0.intake.items():
            assert s1.intake[k] <= v * 1.5 + 1e-6
    assert any("cannot be closed" in w for w in r.warnings)          # the limits make the conflict visible
    assert "a flow was held at its upper limit" in r.notes


def test_chi2_limit_values():
    assert reconcile.chi2_95(1) == approx(3.84, rel=0.03)
    assert reconcile.chi2_95(10) == approx(18.31, rel=0.01)


# ---------------------------------------------------------------- 2) partial metering
def test_partly_metered_sources_are_flagged_and_completed():
    a = Subsystem("A", intake={"S1": 60.0, "S2": 40.0}, evaporation=10.0, discharge={"O": 90.0})
    p = Plant(sources=[Source("S1", 1.0, 60.0), Source("S2", 1.0, None)], outlets=[Outlet("O", 1.0, 90.0)], subsystems=[a])
    b = balance.plant_balance(p)
    assert b.unmetered_sources == ["S2"] and any("Sources without a meter" in w for w in b.warnings)
    assert b.metered_intake == approx(100.0)          # S2 at its allocated volume, not dropped
    assert b.plant_imbalance == approx(0.0)
    assert "منابع بدون کنتور" in localize(next(w for w in b.warnings if "Sources without" in w), "fa")


def test_partly_metered_outlets_are_flagged():
    a = Subsystem("A", intake={"S": 100.0}, evaporation=10.0, discharge={"O1": 50.0, "O2": 40.0})
    p = Plant(sources=[Source("S", 1.0, 100.0)], outlets=[Outlet("O1", 1.0, 50.0), Outlet("O2", 1.0, None)], subsystems=[a])
    b = balance.plant_balance(p)
    assert b.unmetered_outlets == ["O2"] and b.metered_discharge == approx(90.0)
    assert b.plant_imbalance == approx(0.0)


def test_fully_metered_or_unmetered_plants_have_no_partial_flag():
    for p in (_two(100.0, 90.0), _two()):
        b = balance.plant_balance(p)
        assert not b.unmetered_sources and not b.unmetered_outlets


# ---------------------------------------------------------------- 3) significance of the boundary imbalance
def test_small_imbalance_is_not_significant():
    p = _two(src_meter=100.0, out_meter=88.0)          # gap 2 m3, meters assumed 10 % -> sigma about 14
    b = balance.plant_balance(p)
    assert b.plant_imbalance == approx(2.0)
    assert b.imbalance_sigma > 10 and b.imbalance_significant is False
    assert not any("boundary imbalance" in w for w in b.warnings)


def test_large_imbalance_with_accurate_meters_is_significant():
    p = _two(src_meter=100.0, out_meter=70.0)           # 20 m3 gap
    p.site = Site(meters=[Meter("m1", "source:S", "flow", "m3", 1.0), Meter("m2", "outlet:O", "flow", "m3", 1.0),
                          Meter("m3", "sub:A:evaporation", "flow", "m3", 1.0)])
    b = balance.plant_balance(p)
    assert b.plant_imbalance == approx(20.0)
    assert b.imbalance_sigma < 5 and b.imbalance_significant is True
    w = next(w for w in b.warnings if "boundary imbalance" in w)
    assert "ناترازی مرز کارخانه" in localize(w, "fa")


def test_ornl_boundary_imbalance_is_judged():
    from waterprofiler.analysis import analyse
    b = analyse(ornl_pilot3("en")).balance
    assert b.imbalance_sigma and b.imbalance_significant in (True, False)
