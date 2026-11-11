import numpy as np
import pytest

from waterprofiler import economics as EC, econrisk as ER
from waterprofiler.model import Plant
from waterprofiler.sample import demo_plant


def _inp(**kw):
    d = dict(saving_m3=10000.0, price=2.0, capex=15000.0, opex=500.0, life=10, rate_pct=10.0, salvage=1000.0,
             repl_year=5, repl_cost=2000.0, price_esc_pct=2.0, degradation_pct=1.0, other_benefit=300.0, opex_esc_pct=1.0)
    d.update(kw)
    return EC.EconInputs(**d)


# ------------------------------------------------------------------ LCC
def test_lcc_identities():
    r = EC.evaluate(_inp())
    assert r.lcc == pytest.approx(sum(r.lcc_parts.values()))
    assert r.lcc == pytest.approx(r.pv_cost - 1000.0 / 1.1 ** 10)
    assert r.lcow == pytest.approx(r.lcc / r.pv_volume)
    assert r.lcc_parts["capex"] == 15000.0 and r.lcc_parts["salvage"] < 0 and r.lcc_parts["repl"] > 0
    ann = (1 - 1.1 ** -10) / 0.1
    assert r.eac == pytest.approx(r.lcc / ann)
    assert sum(a + b + c for a, b, c in r.lcc_years) == pytest.approx(r.lcc + 1000.0 / 1.1 ** 10)


def test_lcc_zero_rate():
    r = EC.evaluate(_inp(rate_pct=0.0, salvage=0.0))
    assert r.eac == pytest.approx(r.lcc / 10)


# ------------------------------------------------------------------ sensitivity
def test_sensitivity_table_and_break_even():
    inp = _inp()
    rows = ER.sensitivity_table(inp, 0.2)
    assert [r.swing for r in rows] == sorted((r.swing for r in rows), reverse=True)
    sav = next(r for r in rows if r.var == "saving_m3")
    assert sav.low.npv < EC.evaluate(inp).npv < sav.high.npv
    be = ER.break_even(inp)
    for var in ("saving_m3", "capex", "price"):
        x = be[var]
        import dataclasses
        v = dataclasses.replace(inp, **{var: getattr(inp, var) * (1 + x)})
        assert EC.evaluate(v).npv == pytest.approx(0.0, abs=1e-4)
    xs, ys = ER.spider(inp)[0], ER.spider(inp)[1]
    assert len(xs) == 7 and all(len(v) == 7 for v in ys.values())
    a, b, grid = ER.two_way(inp)
    assert grid[3][3] == pytest.approx(EC.evaluate(inp).npv)


# ------------------------------------------------------------------ Monte Carlo
def test_vectorised_model_equals_scalar_model_at_base():
    inp = _inp()
    st = ER.RiskSettings(runs=200, ranges={k: (0.0, 0.0) for k in ER.MC_VARS})
    r = ER.simulate_item(inp, st)
    ev = EC.evaluate(inp)
    assert r.npv_stats.sd == pytest.approx(0.0, abs=1e-9)
    assert r.npv_stats.mean == pytest.approx(ev.npv, rel=1e-9)
    assert r.lcow_stats.mean == pytest.approx(ev.lcow, rel=1e-9)
    assert r.lcc_stats.mean == pytest.approx(ev.lcc, rel=1e-9)
    assert r.irr_stats.mean == pytest.approx(ev.irr, rel=1e-6)


def test_vectorised_model_matches_scalar_on_random_draws():
    inp = _inp()
    rng = np.random.default_rng(3)
    s = ER.draw(inp, ER.DEFAULT_RANGES, rng.random((50, len(ER.MC_VARS))))
    v = ER._vec(inp, s)
    for k in (0, 7, 23, 49):
        one = dict(saving_m3=s["saving_m3"][k], price=s["price"][k], capex=s["capex"][k], opex=s["opex"][k],
                   other_benefit=s["other_benefit"][k], rate_pct=s["rate_pct"][k], price_esc_pct=s["price_esc_pct"][k],
                   opex_esc_pct=s["opex_esc_pct"][k], degradation_pct=s["degradation_pct"][k])
        assert EC.evaluate(_inp(**one)).npv == pytest.approx(v["npv"][k], rel=1e-9)


def test_distribution_stays_inside_ranges_and_is_reproducible():
    inp = _inp()
    u = np.random.default_rng(1).random((5000, len(ER.MC_VARS)))
    s = ER.draw(inp, ER.DEFAULT_RANGES, u)
    assert s["capex"].min() >= 15000 * 0.9 - 1e-6 and s["capex"].max() <= 15000 * 1.3 + 1e-6
    assert s["rate_pct"].min() >= 8.0 - 1e-9 and s["rate_pct"].max() <= 13.0 + 1e-9
    tri_mean = (15000 * 0.9 + 15000 + 15000 * 1.3) / 3
    assert s["capex"].mean() == pytest.approx(tri_mean, rel=0.01)
    a, b = ER.simulate_item(inp, ER.RiskSettings(runs=800, seed=5)), ER.simulate_item(inp, ER.RiskSettings(runs=800, seed=5))
    assert np.array_equal(a.npv, b.npv)


def test_risk_summary_consistency():
    r = ER.simulate_item(_inp(capex=100000.0), ER.RiskSettings(runs=3000))       # a weak project: some losses
    s = r.npv_stats
    assert s.minimum <= s.p5 <= s.p50 <= s.p95 <= s.maximum
    assert 0.0 < r.p_loss < 1.0 and r.p_loss == pytest.approx(float((r.npv < 0).mean()))
    assert r.var5 == pytest.approx(max(0.0, -s.p5)) and r.shortfall <= s.p5 + 1e-9
    assert sum(r.hist_counts) == 3000 and len(r.hist_edges) == 31 and len(r.cdf_x) == 101
    assert r.cdf_x == sorted(r.cdf_x)
    assert abs(r.drivers[0][1]) >= abs(r.drivers[-1][1])


def test_wider_capex_range_raises_the_risk():
    base = {k: (0.0, 0.0) for k in ER.MC_VARS}
    tight = ER.simulate_item(_inp(capex=30000.0), ER.RiskSettings(runs=3000, ranges={**base, "capex": (0.0, 5.0)}))
    wide = ER.simulate_item(_inp(capex=30000.0), ER.RiskSettings(runs=3000, ranges={**base, "capex": (0.0, 80.0)}))
    assert wide.npv_stats.sd > tight.npv_stats.sd and wide.p_loss >= tight.p_loss


def test_plan_scope_sums_items_and_shares_price_and_rate():
    p = demo_plant("en")
    zero = ER.RiskSettings(runs=100, ranges={k: (0.0, 0.0) for k in ER.MC_VARS})
    r = ER.simulate_plan(p, zero)
    assert r.npv_stats.mean == pytest.approx(sum(ie.result.npv for ie in EC.evaluate_plan_economics(p) if ie.result), rel=1e-9)
    full = ER.simulate_plan(p, ER.RiskSettings(runs=2000))
    assert all(d[0].startswith("item:") for d in full.drivers) and len(full.items) == len(p.plan)
    only = ER.simulate(p, ER.RiskSettings(runs=500, scope="item:1"))
    assert only.items == [1] and only.scope == "item:1"
    assert ER.simulate(Plant()) is None


def test_settings_roundtrip_and_clamping():
    p = demo_plant("en")
    ER.RiskSettings(runs=10 ** 9, seed=9, ranges={**ER.DEFAULT_RANGES, "capex": (40.0, -5.0)}, scope="item:2").store(p)
    q = Plant.from_dict(p.to_dict())
    s = ER.RiskSettings.of(q)
    assert s.runs == ER.MAX_RUNS and s.seed == 9 and s.scope == "item:2" and s.ranges["capex"] == (-5.0, 40.0)
    assert ER.RiskSettings.of(Plant()).runs == 5000
