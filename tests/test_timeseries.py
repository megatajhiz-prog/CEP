from datetime import date

import pytest

from waterprofiler import indicators as K
from waterprofiler import jcalendar as C
from waterprofiler import timeseries as T
from waterprofiler.indicator_text import GROUP_TITLE, TEXT
from waterprofiler.model import Area, Meter, Outlet, Plant, Point, Product, Site, Source, Subsystem
from waterprofiler.storage import load_project, save_project


def small() -> Plant:
    return Plant(
        name="t", production_per_year=1000.0, production_unit="t",
        site=Site(products=[Product("P", "t", per_year=1000.0)]),
        sources=[Source("A", 2.0), Source("B", 4.0)], outlets=[Outlet("S", 3.0)],
        subsystems=[Subsystem("X", "process", intake={"A": 600.0}, discharge={"S": 400.0}, product=100.0),
                    Subsystem("Y", "cooling_tower", intake={}, discharge={})],
    )


# ----------------------------------------------------------------------------------------------- calendar
def test_jalali_reference_dates():
    assert C.to_jalali(date(2026, 3, 21)) == (1405, 1, 1)
    assert C.to_jalali(date(2026, 11, 3)) == (1405, 8, 12)
    assert C.to_jalali(date(2025, 3, 20)) == (1403, 12, 30)       # 1403 is a leap year
    assert C.to_jalali(date(2025, 3, 21)) == (1404, 1, 1)
    assert C.from_jalali(1405, 1, 1) == date(2026, 3, 21)
    assert [y for y in range(1395, 1415) if C.is_jalali_leap(y)] == [1395, 1399, 1403, 1408, 1412]
    assert [C.jalali_month_days(1404, m) for m in range(1, 13)] == [31] * 6 + [30] * 5 + [29]
    assert C.jalali_month_days(1403, 12) == 30


def test_jalali_roundtrip_over_many_years():
    d = date(1990, 1, 1)
    while d < date(2060, 1, 1):
        assert C.from_jalali(*C.to_jalali(d)) == d
        d = date.fromordinal(d.toordinal() + 37)


def test_slices_months_years_and_partial_ends():
    sl = C.slices(date(2025, 3, 21), date(2026, 3, 20), "month", "jalali", "en")
    assert len(sl) == 12 and not any(s.partial for s in sl)
    assert sum(s.days for s in sl) == 365 and sl[0].label == "Farvardin 1404" and sl[-1].label == "Esfand 1404"
    cut = C.slices(date(2025, 4, 10), date(2025, 6, 30), "month", "jalali", "en")
    assert [s.partial for s in cut] == [True, False, True] or cut[0].partial          # starts mid-month
    assert cut[0].start == date(2025, 4, 10) and cut[-1].end == date(2025, 6, 30)
    assert all(a.end + (date(2025, 1, 2) - date(2025, 1, 1)) == b.start for a, b in zip(cut, cut[1:]))   # contiguous
    yrs = C.slices(date(2025, 5, 10), date(2027, 2, 1), "year", "jalali", "fa")
    assert [s.label for s in yrs] == ["1404", "1405"] and all(s.partial for s in yrs)
    g = C.slices(date(2024, 1, 1), date(2024, 12, 31), "month", "gregorian")
    assert [s.days for s in g][1] == 29 and sum(s.days for s in g) == 366
    with pytest.raises(ValueError):
        C.slices(date(2025, 2, 1), date(2025, 1, 1))


def test_parse_and_format():
    assert C.parse_date("1405/03/01", "jalali") == C.from_jalali(1405, 3, 1)
    assert C.parse_date("2026-05-22", "gregorian") == date(2026, 5, 22)
    assert C.format_date(date(2026, 3, 21), "jalali") == "1405/01/01"
    with pytest.raises(ValueError):
        C.parse_date("1405/03", "jalali")


# --------------------------------------------------------------------------------------------- aggregation
def test_value_in_spreads_sums_and_weights_means():
    pts = [Point("2025-01-01", "2025-01-10", 100.0)]                  # 10 days, 100 units
    v, c = T.value_in(pts, date(2025, 1, 1), date(2025, 1, 5), "sum")
    assert v == pytest.approx(50.0) and c == 1.0
    v, c = T.value_in(pts, date(2025, 1, 6), date(2025, 1, 15), "sum")
    assert v == pytest.approx(50.0) and c == pytest.approx(0.5)
    assert T.value_in(pts, date(2025, 2, 1), date(2025, 2, 5), "sum") == (None, 0.0)
    m = [Point("2025-01-01", "2025-01-10", 10.0), Point("2025-01-11", "2025-01-30", 20.0)]
    v, c = T.value_in(m, date(2025, 1, 1), date(2025, 1, 30), "mean")
    assert v == pytest.approx((10 * 10 + 20 * 20) / 30) and c == 1.0


def test_set_value_conserves_data_outside_the_slice():
    base = [Point("2025-01-01", "2025-01-31", 310.0)]                  # 10 per day
    out = T.set_value(base, date(2025, 1, 11), date(2025, 1, 20), 999.0, "sum")
    assert [(p.start, p.end) for p in out] == [("2025-01-01", "2025-01-10"), ("2025-01-11", "2025-01-20"),
                                               ("2025-01-21", "2025-01-31")]
    assert [round(p.value, 6) for p in out] == [100.0, 999.0, 110.0]
    gone = T.set_value(out, date(2025, 1, 11), date(2025, 1, 20), None, "sum")
    assert len(gone) == 2 and T.value_in(gone, date(2025, 1, 11), date(2025, 1, 20), "sum") == (None, 0.0)
    lvl = T.set_value([Point("2025-01-01", "2025-01-31", 7.0)], date(2025, 1, 11), date(2025, 1, 20), 9.0, "mean")
    assert [p.value for p in lvl] == [7.0, 9.0, 7.0]                   # levels keep their value outside


def test_put_uses_catalog_aggregation_and_unknown_keys_are_rejected():
    p = small()
    keys = {s.key for s in T.catalog(p)}
    assert {"production:P", "source:A", "outlet:S", "sub:X:intake", "sub:Y:evaporation", "energy:el", "price:source:B",
            "env:temp", "quality:cod_raw"} <= keys
    ok, bad = T.from_rows(p, [("source:A", "2025-01-01", "2025-01-31", "310"), ("source:ZZ", "2025-01-01", "2025-01-31", "1"),
                              ("source:A", "2025-02-01", "bad", "1")])
    assert ok == 1 and len(bad) == 2
    assert T.to_rows(p) == [("source:A", "2025-01-01", "2025-01-31", 310.0)]


# ----------------------------------------------------------------------- applying a period to the annual model
def _fill_months(p, key, values, start=date(2025, 3, 21)):
    for sl, v in zip(C.slices(start, date(2026, 3, 20), "month", "jalali")[:len(values)], values):
        T.put(p, key, sl.start, sl.end, v)


def test_plan_and_commit_full_year():
    p = small()
    _fill_months(p, "source:A", [100.0] * 12)
    _fill_months(p, "production:P", [50.0] * 12)
    _fill_months(p, "price:source:A", [2.0] * 6 + [4.0] * 6)
    _fill_months(p, "sub:X:intake", [60.0] * 12)
    ch = {c.key: c for c in T.plan_changes(p, date(2025, 3, 21), date(2026, 3, 20))}
    assert ch["source:A"].new == pytest.approx(1200.0) and ch["source:A"].note == ""
    assert ch["production:P"].new == pytest.approx(600.0) and ch["production:P"].old == 1000.0
    assert ch["price:source:A"].new == pytest.approx((2 * 186 + 4 * 179) / 365)       # day-weighted mean
    assert ch["sub:X:intake"].new == pytest.approx(720.0)
    n = T.commit(p, list(ch.values()))
    assert p.production_per_year == pytest.approx(600.0)                     # total = sum of products
    assert n == 4 and p.sources[0].metered_m3 == pytest.approx(1200.0) and p.production_per_year == pytest.approx(600.0)
    assert p.subsystems[0].intake["A"] == pytest.approx(720.0)         # scaled, source split kept


def test_partial_coverage_is_extrapolated_and_flagged_or_skipped():
    p = small()
    _fill_months(p, "source:A", [100.0] * 6)                           # Farvardin..Shahrivar = 186 days
    ch = T.plan_changes(p, date(2025, 3, 21), date(2026, 3, 20))[0]
    assert ch.note == "extrapolated" and ch.coverage == pytest.approx(186 / 365)
    assert ch.new == pytest.approx(600.0 / 186 * 365)
    q = small()
    _fill_months(q, "source:A", [100.0] * 2)
    low = T.plan_changes(q, date(2025, 3, 21), date(2026, 3, 20))[0]
    assert low.note == "low_coverage" and low.new is None
    assert T.commit(q, [low]) == 0 and q.sources[0].metered_m3 is None


def test_subsystem_without_split_is_not_guessed():
    p = small()
    _fill_months(p, "sub:Y:intake", [10.0] * 12)                       # two sources and no split known
    c = T.plan_changes(p, date(2025, 3, 21), date(2026, 3, 20))[0]
    assert c.note == "split" and c.new is None
    one = small()
    one.sources = one.sources[:1]
    _fill_months(one, "sub:Y:intake", [10.0] * 12)
    c1 = T.plan_changes(one, date(2025, 3, 21), date(2026, 3, 20))[0]
    T.commit(one, [c1])
    assert one.subsystems[1].intake == {"A": pytest.approx(120.0)}


def test_total_production_is_the_sum_of_products():
    p = small()
    p.site.products = [Product("P1", "t", per_year=300.0), Product("P2", "t", per_year=200.0)]
    assert p.sync_production() == 500.0 and "production" not in {s.key for s in T.catalog(p)}
    _fill_months(p, "production:P1", [10.0] * 12)
    _fill_months(p, "production:P2", [20.0] * 12)
    ch = {x.key: x for x in T.plan_changes(p, date(2025, 3, 21), date(2026, 3, 20))}
    assert ch["production:P1"].new == pytest.approx(120.0) and ch["production:P2"].new == pytest.approx(240.0)
    T.commit(p, list(ch.values()))
    assert p.production_per_year == pytest.approx(360.0)
    sl = C.slices(date(2025, 3, 21), date(2026, 3, 20), "month", "jalali")
    assert T.total_production_slices(p, sl)[0] == pytest.approx(30.0)


def test_old_file_with_only_a_total_gets_one_product():
    from waterprofiler.model import Plant as P
    d = {"name": "x", "production_per_year": 800.0, "production_unit": "t",
         "series": {"production": [{"start": "2025-01-01", "end": "2025-01-31", "value": 70.0}]}}
    q = P.from_dict(d)
    assert len(q.site.products) == 1 and q.site.products[0].per_year == 800.0 and q.production_per_year == 800.0
    assert "production" not in q.series and q.series["production:" + q.site.products[0].name][0].value == 70.0


# ------------------------------------------------------------------------------------------ time indicators
def monthly_plant(n=24, spike=None):
    p = small()
    p.site.calendar = "gregorian"
    p.window = {"start": "2024-01-01", "end": "2025-12-31"}
    sl = C.slices(date(2024, 1, 1), date(2025, 12, 31), "month", "gregorian")[:n]
    for i, s in enumerate(sl):
        q = 100.0 + 10.0 * (i % 6)
        v = 50.0 + 2.0 * q + (400.0 if spike == i else 0.0)
        T.put(p, "production:P", s.start, s.end, q)
        T.put(p, "source:A", s.start, s.end, v)
        T.put(p, "energy:el", s.start, s.end, v * 3.0)
    return p


def test_time_indicators_recover_base_load_and_slope():
    r = K.compute(monthly_plant())
    g = lambda i: r.get(i).value
    assert g("ts_months") == 24 and g("ts_coverage") == pytest.approx(100.0)
    assert g("ts_base_load") == pytest.approx(50.0) and g("ts_slope") == pytest.approx(2.0) and g("ts_r2") == pytest.approx(1.0)
    assert g("ts_anomalies") == 0
    assert g("ts_energy_per_m3") == pytest.approx(3.0)
    assert g("ts_peak_factor") > 1.0 and g("ts_yoy") == pytest.approx(0.0, abs=1e-9)
    assert r.get("ts_temp_corr").value is None and r.get("ts_temp_corr").reason == "series"
    assert r.get("ts_base_share").value == pytest.approx(100 * 50 / g("ts_intake_mean"))


def test_anomaly_month_is_found():
    r = K.compute(monthly_plant(spike=10))
    assert r.get("ts_anomalies").value >= 1


def test_not_enough_data_is_reported_not_guessed():
    r = K.compute(monthly_plant(n=4))
    assert r.get("ts_peak_factor").value is None and r.get("ts_peak_factor").reason == "data"
    assert r.get("ts_base_load").value is None
    none = K.compute(small())
    assert none.get("ts_months").reason == "series" and none.get("ts_months").value is None
    assert {i.group for i in none.items} == set(K.GROUPS) == set(GROUP_TITLE)
    assert all(i.id in TEXT for i in none.items)


# --------------------------------------------------------------------------------------------- persistence
def test_site_and_series_roundtrip_and_old_files(tmp_path):
    p = monthly_plant(6)
    p.site = Site(name="Pasargad Plant", province="Tehran", calendar="jalali", commissioning_year=1390,
                  areas=[Area("Hall A", "production")], products=[Product("Cement", "t", per_year=1000.0)],
                  meters=[Meter("M1", "source:A", "flow", "m3", 1.5, "2020-01-01", "2025-01-01")])
    p.subsystems[0].area = "Hall A"
    f = tmp_path / "a.wpj"
    save_project(p, str(f))
    q = load_project(str(f))
    assert q == p and q.site.meters[0].accuracy_pct == 1.5 and q.series["production:P"][0].value == 100.0
    d = p.to_dict()
    for k in ("site", "series", "window"):
        d.pop(k)
    d["subsystems"][0].pop("area")
    old = Plant.from_dict(d)
    assert old.site == Site(products=[Product("محصول", "t", per_year=1000.0)]) and old.series == {} and old.window == {} and old.subsystems[0].area == ""


def test_trend_of_a_linear_series_is_exact():
    p = small()
    p.site.calendar = "gregorian"
    p.window = {"start": "2024-01-01", "end": "2025-12-31"}
    vals = []
    for i, s in enumerate(C.slices(date(2024, 1, 1), date(2025, 12, 31), "month", "gregorian")):
        vals.append(1000.0 + 10.0 * i)
        T.put(p, "source:A", s.start, s.end, vals[-1])
    r = K.compute(p)
    mean = sum(vals) / len(vals)
    assert r.get("ts_trend").value == pytest.approx(100 * 10.0 * 12 / mean)       # 10 m3 per month, per year
    assert r.get("ts_yoy").value == pytest.approx(100 * (sum(vals[12:]) / sum(vals[:12]) - 1))
    assert r.get("ts_peak_factor").value == pytest.approx(max(vals) / mean)


def test_demo_with_history_is_consistent():
    from waterprofiler.sample import demo_with_history
    from waterprofiler.storage import load_project, save_project  # noqa: F401
    for lang in ("fa", "en"):
        p = demo_with_history(lang)
        assert p.site.areas and p.site.products and p.site.meters
        assert all(s.area for s in p.subsystems)
        keys = {sp.key for sp in T.catalog(p)}
        assert set(p.series) <= keys                          # every series belongs to a catalogued variable
        span = T.data_span(p)
        assert span and (span[1] - span[0]).days > 540
        ind = {i: v for i, _u, v, _r in T.time_indicators(p)}
        assert ind["ts_months"] >= 18 and ind["ts_anomalies"] >= 1 and 1.0 < ind["ts_peak_factor"] < 2.0


# ------------------------------------------------------------------ losses, unit production and water price
def test_catalog_has_losses_unit_production_and_price_before_the_rest():
    p = small()
    keys = [s.key for s in T.catalog(p)]
    assert "loss:measured" in keys
    assert all(f"sub:{s.name}:production" in keys for s in p.subsystems)
    groups = []
    for s in T.catalog(p):
        if not groups or groups[-1] != s.group:
            groups.append(s.group)
    assert len(groups) == len(set(groups))                                  # groups are contiguous in the list
    assert groups.index("price") < groups.index("subsystem") < groups.index("energy")
    assert groups.index("loss") < groups.index("price")


def test_unit_production_is_applied_to_the_model():
    p = small()
    sub = p.subsystems[0].name
    _fill_months(p, f"sub:{sub}:production", [10.0] * 12)
    ch = [c for c in T.plan_changes(p, date(2025, 3, 21), date(2026, 3, 20)) if c.key == f"sub:{sub}:production"]
    assert len(ch) == 1 and ch[0].new == pytest.approx(120.0)
    assert T.commit(p, ch) == 1 and p.profile.sub_production[sub] == pytest.approx(120.0)


def test_loss_and_price_indicators():
    p = monthly_plant()
    sl = C.slices(date(2024, 1, 1), date(2025, 12, 31), "month", "gregorian")
    for i, s in enumerate(sl):
        v = 50.0 + 2.0 * (100.0 + 10.0 * (i % 6))
        T.put(p, "loss:measured", s.start, s.end, v * 0.05)                 # 5 % of the intake every month
        T.put(p, "price:source:A", s.start, s.end, 2.0 if i < 12 else 3.0)  # price rises 50 % in year 2
    g = {i: v for i, _u, v, _r in T.time_indicators(p)}
    assert g["ts_loss_measured"] == pytest.approx(5.0)
    assert g["ts_price_mean"] == pytest.approx(2.5, rel=0.05) and g["ts_price_change"] == pytest.approx(50.0)
    nothing = {i: (v, r) for i, _u, v, r in T.time_indicators(small())}
    assert nothing["ts_loss_measured"] == (None, "series") and nothing["ts_price_change"] == (None, "series")


def test_demo_history_has_loss_price_and_unit_production():
    from waterprofiler.sample import demo_with_history
    p = demo_with_history("en")
    assert p.series.get("loss:measured") and any(k.startswith("price:source:") for k in p.series)
    assert any(k.endswith(":production") and k.startswith("sub:") for k in p.series)
    g = {i: v for i, _u, v, _r in T.time_indicators(p)}
    assert 0 < g["ts_loss_measured"] < 10 and g["ts_price_change"] > 0


def test_excel_template_roundtrip_blank_cells_and_bad_rows(tmp_path):
    from openpyxl import load_workbook

    from waterprofiler import ts_excel as X
    from waterprofiler.sample import demo_with_history

    p = demo_with_history("fa")
    sl = C.slices(date(2025, 3, 21), date(2026, 3, 20), "month", "jalali", "fa")
    keys = ["production:" + p.site.products[0].name, f"source:{p.sources[0].name}", f"sub:{p.subsystems[0].name}:production", "site:steam_t",
            f"price:source:{p.sources[0].name}"]
    specs = [T.spec_of(p, k) for k in keys]
    f = tmp_path / "t.xlsx"
    assert X.export_template(p, str(f), sl, specs, "fa") == 12
    ws = load_workbook(f)["داده"]
    assert [c.value for c in ws[2]][3:] == keys and ws.cell(row=3, column=2).value == "2025-03-21"
    assert ws.cell(row=3, column=4).value is not None            # production is prefilled
    assert ws.cell(row=3, column=7).value is None                # no steam data in the demo: left blank
    # fill the blanks, break one row, import into a plant that has none of this data
    wb = load_workbook(f)
    w = wb["داده"]
    w.cell(row=3, column=7, value=150)
    w.cell(row=4, column=7, value=None)
    w.cell(row=5, column=3, value="not a date")
    w.cell(row=6, column=5, value="abc")
    wb.save(f)
    q = demo_with_history("fa")
    for k in ("site:steam_t", "production:" + p.site.products[0].name):
        q.series.pop(k, None)
    ok, bad = X.import_template(q, str(f))
    assert len(bad) == 2 and ok > 40
    assert T.value_in(q.series["site:steam_t"], date(2025, 3, 21), date(2025, 4, 20), "sum")[0] == pytest.approx(150)
    assert len(q.series["site:steam_t"]) == 1                    # blanks and bad rows were skipped, nothing invented
    # production of the untouched months is back and equals the original
    a = T.value_in(p.series["production:" + p.site.products[0].name], date(2025, 4, 21), date(2025, 5, 21), "sum")[0]
    b = T.value_in(q.series["production:" + p.site.products[0].name], date(2025, 4, 21), date(2025, 5, 21), "sum")[0]
    assert b == pytest.approx(a, abs=1e-4)
    # a file without the key row is reported, not guessed
    from openpyxl import Workbook
    w2 = Workbook()
    w2.active.append(["a", "b"])
    w2.save(tmp_path / "x.xlsx")
    assert X.import_template(q, str(tmp_path / "x.xlsx")) == (0, ["no key row"])


def test_retired_series_dropped_on_load():
    d = {"name": "x", "series": {"energy:th": [{"start": "2025-01-01", "end": "2025-01-31", "value": 5.0}],
                                 "env:rain": [{"start": "2025-01-01", "end": "2025-01-31", "value": 7.0}],
                                 "energy:el": [{"start": "2025-01-01", "end": "2025-01-31", "value": 9.0}]}}
    from waterprofiler.model import Plant
    q = Plant.from_dict(d)
    assert set(q.series) == {"energy:el"}
    assert not {"energy:th", "env:rain"} & {s.key for s in T.catalog(q)}
