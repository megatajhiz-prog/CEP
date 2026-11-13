import pytest

from waterprofiler.analysis import analyse
from waterprofiler.model import Plant
from waterprofiler.sample import wastewater_demo
from waterprofiler.model import Plant
from waterprofiler.wastewater import analyse_wastewater, message

approx = pytest.approx


def _r(lang="en"):
    return analyse_wastewater(wastewater_demo(lang))


def test_demo_plant_balances():
    a = analyse(wastewater_demo("en"))
    assert all(s.status == "balanced" for s in a.balance.subsystems)
    assert a.balance.plant_imbalance == approx(0.0, abs=1e-6)


def test_collection_and_reuse_figures():
    r = _r()
    assert r.generated == 85_000 and r.collected == 72_500
    assert r.collection_rate == approx(72_500 / 85_000)
    assert r.reuse_treated == 24_000
    assert r.reuse_rate == approx(24_000 / 85_000)
    assert r.fresh_saving_pct == approx(24_000 / 138_000)


def test_treatment_closure_and_recovery():
    r = _r()
    etp, ro = r.treatments
    assert etp.closure == approx(0) and ro.closure == approx(0)
    assert ro.recovery == approx(0.75) and etp.recovery == approx(30_000 / 72_500)
    assert etp.cod_removal == approx(1 - 60 / 1800) and ro.tds_removal == approx(1 - 40 / 1400)
    assert etp.cod_load_removed == approx((1800 - 60) * 72_500 / 1000)


def test_required_unit_is_not_charged_to_reuse():
    r = _r()
    etp, ro = r.treatments
    assert etp.required and etp.reclaimed_cost == 0 and etp.payback_years is None
    assert ro.reclaimed_cost == approx((0.45 * 24_000 + 120_000 / 15) / 18_000)
    assert ro.payback_years == approx(120_000 / ro.net_benefit)
    assert r.opex == approx(0.45 * 24_000)


def test_potential_uses_surplus_quality():
    r = _r()
    u = {x.name: x for x in r.users}
    assert u["Cooling tower"].note == "polish" and u["Cooling tower"].potential == 0   # salt 1400 > 1000
    assert u["Landscape"].potential == 5_000
    assert u["Offices and canteen"].potential == approx(0.3 * 8_000)
    assert r.potential_volume == approx(7_400)


def test_unsuitable_reuse_is_flagged():
    p = wastewater_demo("en")
    p.node("Reverse osmosis unit").params["tds_out"] = 900       # permeate too salty for the boiler (50 mg/L)
    r = analyse_wastewater(p)
    assert any(w.startswith("ww_unsuitable:Boiler") for w in r.warnings)


def test_gap_in_treatment_unit_is_flagged():
    p = wastewater_demo("en")
    p.node("Effluent treatment plant").discharge = {"Surface water": 30_000}
    r = analyse_wastewater(p)
    assert any(w.startswith("ww_closure:Effluent") for w in r.warnings)


def test_messages_both_languages_and_persistence():
    r = _r()
    for w in r.warnings:
        assert message(w, "fa") and message(w, "en")
    p2 = Plant.from_dict(wastewater_demo("fa").to_dict())
    assert p2.node("واحد اسمز معکوس").kind == "wwtp"
    assert analyse_wastewater(p2).reuse_treated == 24_000
