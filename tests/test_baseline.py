import numpy as np
import pytest
from datetime import date
from waterprofiler import baseline as BL, jcalendar as cal, timeseries as TS
from waterprofiler.model import Plant, Source, Product


def _plant(n=24, units=("t", "t"), seed=6, noise=20.0, hours=True):
    rng = np.random.default_rng(seed)
    p = Plant(name="t", production_unit="t", sources=[Source("W", 1.0)])
    p.site.calendar = "gregorian"
    p.site.products = [Product("A", units[0], per_year=1.0), Product("B", units[1], per_year=1.0)]
    sl = cal.slices(date(2023, 1, 1), date(2024, 12, 31), "month", "gregorian", "en")[:n]
    for m in sl:
        a, b = rng.uniform(500, 1500), rng.uniform(200, 800)
        h = rng.uniform(400, 700)
        temp = rng.uniform(5, 35)                    # unrelated to the water use
        w = 300 + 0.8 * a + 1.5 * b + (0.0 if not hours else 0.0 * h) + rng.normal(0, noise)
        TS.put(p, "production:A", m.start, m.end, a)
        TS.put(p, "production:B", m.start, m.end, b)
        TS.put(p, "site:operating_hours", m.start, m.end, h)
        TS.put(p, "env:temp", m.start, m.end, temp)
        TS.put(p, "source:W", m.start, m.end, w)
    return p


def test_pvalue_matches_tables():
    assert BL.t_pvalue(2.228, 10) == pytest.approx(0.05, abs=5e-4)
    assert BL.t_pvalue(0.0, 10) == pytest.approx(1.0)
    assert BL.t_pvalue(12.706, 1) == pytest.approx(0.05, abs=5e-4)


def test_mixed_units_use_each_product_as_driver_and_recover_coefficients():
    r = BL.evaluate(_plant(units=("m2", "t")))
    m = r.model
    keys = {d.key for d in m.drivers}
    assert keys == {"production:A", "production:B"}                  # irrelevant temperature / hours are not chosen
    c = dict(zip(["b0"] + [d.key for d in m.drivers], m.coef))
    assert c["production:A"] == pytest.approx(0.8, abs=0.05) and c["production:B"] == pytest.approx(1.5, abs=0.1)
    assert m.r2 > 0.99 and m.good and not r.warnings


def test_same_units_offer_the_total_and_the_products():
    ds = BL.dataset(_plant(units=("t", "t")))
    assert "production" in ds.cols and "production:A" in ds.cols
    assert "production" not in BL.dataset(_plant(units=("m2", "t"))).cols      # different units are never summed


def test_report_split_saving_and_cusum():
    p = _plant()
    sl = cal.slices(date(2023, 1, 1), date(2024, 12, 31), "month", "gregorian", "en")
    for m in sl[-6:]:                                                 # a 100 m3/month saving in the last 6 months
        v, _ = TS.value_in(p.series["source:W"], m.start, m.end, "sum")
        TS.put(p, "source:W", m.start, m.end, v - 100.0)
    r = BL.evaluate(p, n_report=6)
    assert r.n_report == 6 and r.n_train == 18
    assert r.saving_total == pytest.approx(600.0, abs=120.0)
    assert r.significant and r.saving_pct > 0
    assert r.months[-1].cusum == pytest.approx(sum(x.saving for x in r.months))
    assert all(m.in_report for m in r.months[-6:]) and not any(m.in_report for m in r.months[:-6])
    false_pos = sum(BL.evaluate(_plant(seed=s), n_report=6).significant for s in range(20, 40))
    assert false_pos <= 3                                               # no real saving: about 5 % false alarms at 95 %
    assert all(abs(BL.evaluate(_plant(seed=s), n_report=6).saving_pct) < 3 for s in range(20, 30))


def test_no_relationship_falls_back_to_the_mean():
    p = _plant()
    rng = np.random.default_rng(5)
    for m in cal.slices(date(2023, 1, 1), date(2024, 12, 31), "month", "gregorian", "en"):
        TS.put(p, "source:W", m.start, m.end, 1000 + rng.normal(0, 50))
    r = BL.evaluate(p)
    assert r.model.intercept_only and "bl_no_driver" in r.warnings


def test_too_few_months():
    r = BL.evaluate(_plant(n=5))
    assert r.model is None and "bl_too_few" in r.warnings
