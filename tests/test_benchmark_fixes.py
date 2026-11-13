"""Fixes from the benchmark: reconcile sanity checks, partial metering, significance of the boundary imbalance."""
import pytest

from waterprofiler import balance, reconcile
from waterprofiler.messages import localize
from waterprofiler.model import Meter, Outlet, Plant, Site, Source, Subsystem
from waterprofiler.sample import demo_plant

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


# ---------------------------------------------------------------- per-source abstraction limit (optional)
def _permit_plant(on, permit, used=100.0):
    a = Subsystem("A", intake={"S": used}, evaporation=used, discharge={})
    return Plant(sources=[Source("S", 1.0, None, False, on, permit)], outlets=[Outlet("O")], subsystems=[a])


def test_permit_off_is_ignored_even_with_a_value():
    b = balance.plant_balance(_permit_plant(False, 50.0))
    assert not b.permit_use and not any("permit" in w for w in b.warnings)


def test_permit_exceeded_and_near():
    b = balance.plant_balance(_permit_plant(True, 80.0))
    assert b.permit_use["S"] == approx((100.0, 80.0, 1.25))
    w = next(w for w in b.warnings if "permit" in w)
    assert "exceeds" in w and "حداکثر مجاز" in localize(w, "fa")
    b = balance.plant_balance(_permit_plant(True, 105.0))
    assert any("% of its permit" in w for w in b.warnings) and "رسیده" in localize(next(w for w in b.warnings if "permit" in w), "fa")
    b = balance.plant_balance(_permit_plant(True, 200.0))
    assert not any("permit" in w for w in b.warnings) and b.permit_use["S"][2] == approx(0.5)


def test_permit_roundtrip_json_and_old_files():
    p = _permit_plant(True, 80.0)
    assert Plant.from_dict(p.to_dict()).sources[0].permit_on and Plant.from_dict(p.to_dict()).sources[0].permit_m3 == 80.0
    old = p.to_dict()
    for s in old["sources"]:
        s.pop("permit_on"), s.pop("permit_m3")
    assert Plant.from_dict(old).sources[0].permit_on is False        # files from before the limit existed


def test_plant_permit_is_the_sum_of_the_enabled_source_limits():
    from waterprofiler.indicators import compute
    a = Subsystem("A", intake={"S1": 60.0, "S2": 30.0, "S3": 10.0}, evaporation=100.0)
    p = Plant(sources=[Source("S1", 1.0, None, False, True, 100.0), Source("S2", 1.0, None, False, True, 50.0),
                       Source("S3", 1.0, None, False, False, 5.0)], outlets=[Outlet("O")], subsystems=[a])
    ind = compute(p).get("sup_permit_use")
    assert ind.value == approx(100.0 * 90 / 150) and ind.reason == ""      # S3 has its limit off: ignored
    p.sources[0].permit_on = p.sources[1].permit_on = False
    ind = compute(p).get("sup_permit_use")
    assert ind.value is None and ind.reason == "permit"
