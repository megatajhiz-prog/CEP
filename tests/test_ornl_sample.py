"""The ORNL worked example (Malhotra 2021, pilot training 3) must reproduce the report's published numbers."""

from pytest import approx

from waterprofiler.analysis import analyse
from waterprofiler.sample import ornl_pilot3

PCT = 100 * 100_000 * 3.78541 / 100   # m3 of 100 % of plant-level intake


def _a(lang="en"):
    return analyse(ornl_pilot3(lang))


def test_balance_matches_report_fig11():
    b = _a().balance
    p = lambda x: 100 * x / PCT                                   # noqa: E731
    assert p(b.sum_intake) == approx(101.7, abs=0.05)
    assert p(b.sum_evaporation) == approx(12.4, abs=0.05)
    assert p(b.sum_discharge) == approx(89.3, abs=0.05)
    assert p(b.source_side_imbalance) == approx(-1.7, abs=0.05)   # sign: metered minus allocated
    assert p(b.discharge_side_imbalance) == approx(-8.9, abs=0.05)
    assert p(b.plant_imbalance) == approx(7.2, abs=0.05)
    assert all(s.status == "balanced" for s in b.subsystems)      # each subsystem closes on its own


def test_true_cost_matches_report_fig12_13():
    a = _a()
    c = a.cost
    assert c.true_cost_per_m3_intake * 3.78541 == approx(8.01, abs=0.03)   # $/kGal
    assert c.true_to_direct_ratio == approx(1.45, abs=0.01)
    share = {s.name: 100 * c.cost_share[s.name] for s in c.subsystems}
    vals = sorted(share.values(), reverse=True)
    assert vals[0] == approx(35, abs=1.5) and vals[1] == approx(31, abs=1.5) and vals[2] == approx(19, abs=1.5)
    comp = {k: 100 * x / c.total for k, x in c.by_component.items()}
    assert comp["intake"] == approx(40, abs=1.5) and comp["pumping"] == approx(26, abs=1.5)
    assert comp["water_treatment"] == approx(4, abs=1.0)
    assert comp["discharge"] == approx(28, abs=1.5)                        # municipal 24 + third-party 4


def test_both_languages_and_plan():
    en, fa = ornl_pilot3("en"), ornl_pilot3("fa")
    assert len(en.subsystems) == len(fa.subsystems) == 6 and en.site.note and fa.site.note
    from waterprofiler.measures import evaluate_plan
    r = evaluate_plan(en)
    assert 5 < r.saving_pct < 15 and r.payback is not None
    assert en.production_per_year == approx(308272.7, rel=1e-4)            # 0.33 kGal per 1000 lb
