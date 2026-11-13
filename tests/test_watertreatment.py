import pytest

from waterprofiler.analysis import analyse
from waterprofiler.model import Plant
from waterprofiler.sample import water_treatment_demo
from waterprofiler.watertreatment import analyse_water_treatment, message
from waterprofiler.wastewater import analyse_wastewater

approx = pytest.approx


def _r(lang="en"):
    return analyse_water_treatment(water_treatment_demo(lang))


def test_demo_balances():
    a = analyse(water_treatment_demo("en"))
    assert all(s.status == "balanced" for s in a.balance.subsystems)
    assert a.balance.plant_imbalance == approx(0.0, abs=1e-6)


def test_unit_figures():
    r = _r()
    pre, dm = r.units
    assert pre.inflow == 120_000 and pre.closure == approx(0)
    assert pre.yield_ == approx(114_000 / 120_000) and pre.waste_share == approx(0.05)
    assert dm.inflow == 40_000 and dm.yield_ == approx(0.75) and dm.tds_removal == approx(1 - 8 / 580)
    assert dm.utilisation == approx(0.8)
    assert r.raw_in == 120_000 and r.delivered == 114_000 - 40_000 + 30_000
    assert r.overall_yield == approx(104_000 / 120_000)
    assert r.waste_share_of_intake == approx(16_000 / 120_000)


def test_cost_follows_the_chain():
    r = _r()
    pre, dm = r.units
    raw = 100_000 * 0.6 + 20_000 * 1.5
    pre_total = raw + 0.06 * 120_000 + 0.15 * 120_000 * 0.08 + 60_000 / 15 + 6_000 * 1.0
    assert pre.cost_per_m3 == approx(pre_total / 114_000)
    dm_total = 40_000 * pre.cost_per_m3 + 0.35 * 40_000 + 1.2 * 40_000 * 0.08 + 180_000 / 15 + 10_000 * 1.0
    assert dm.cost_per_m3 == approx(dm_total / 30_000)
    assert dm.cost_per_m3 > pre.cost_per_m3 > 0.9


def test_consumers_and_quality_check():
    r = _r()
    c = {x.name: x for x in r.consumers}
    assert c["Boiler"].volume == 22_000 and c["Boiler"].suitable is True and c["Boiler"].tds == approx(8)
    assert c["Process"].volume == 62_000 and c["Process"].suitable is None
    assert c["Boiler"].cost_per_m3 == approx(r.units[1].cost_per_m3)
    p = water_treatment_demo("en")
    p.node("Demineralised water unit (RO)").params["tds_out"] = 120
    assert any(w.startswith("wt_unsuitable:Boiler") for w in analyse_water_treatment(p).warnings)


def test_warnings():
    p = water_treatment_demo("en")
    p.node("Demineralised water unit (RO)").discharge = {"Sewer": 4_000}
    p.node("Pre-treatment (clarifier + filters)").params["capacity"] = 100_000
    w = analyse_water_treatment(p).warnings
    assert any(x.startswith("wt_closure") for x in w) and any(x.startswith("wt_overload") for x in w)
    p2 = water_treatment_demo("en")
    p2.node("Demineralised water unit (RO)").params["min_yield"] = 80
    assert any(x.startswith("wt_lowyield") for x in analyse_water_treatment(p2).warnings)
    for x in w:
        assert message(x, "fa") and message(x, "en")


def test_persistence_and_wastewater_sees_the_waste():
    p = Plant.from_dict(water_treatment_demo("fa").to_dict())
    assert analyse_water_treatment(p).raw_in == 120_000
    ww = analyse_wastewater(water_treatment_demo("en"))
    names = {s.name: s for s in ww.streams}
    assert names["Pre-treatment (clarifier + filters)"].cls == "blowdown"       # back-wash / reject count as generated wastewater
