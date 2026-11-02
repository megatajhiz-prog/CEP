import math

import pytest

from waterprofiler import measures as M
from waterprofiler.model import PlanItem, Plant
from waterprofiler.sample import demo_plant
from waterprofiler.storage import load_project, save_project


def test_database_shape():
    ms = M.all_measures()
    assert [m.id for m in ms] == list(range(1, 81))
    counts = {g: sum(1 for m in ms if m.group == g) for g in range(1, 10)}
    assert counts == {1: 10, 2: 12, 3: 7, 4: 11, 5: 7, 6: 12, 7: 9, 8: 6, 9: 6}
    for m in ms:
        assert m.fa and m.en
        assert m.capex[0] <= m.capex[1] and 1 <= m.capex[0] <= 4 and 1 <= m.capex[1] <= 4
        for r in (m.use, m.fresh):
            if r is not None:
                assert 0 <= r[0] <= r[1] <= 100


@pytest.mark.parametrize("mid,use,capex", [
    (11, (5, 20), (1, 2)), (16, (50, 95), (3, 3)), (19, (70, 95), (4, 4)), (21, (0.1, 1), (1, 1)),
    (23, (10, 40), (2, 2)), (66, (50, 100), (1, 2)), (80, (10, 30), (3, 3)), (5, (1, 15), (1, 1)),
])
def test_values_match_the_study(mid, use, capex):
    m = M.get(mid)
    assert m.use == use and m.capex == capex


def test_non_numeric_entries():
    for i in (9, 55, 59, 65, 71):
        assert not M.get(i).estimable
    for i in (10, 75, 76, 77, 78, 79):
        assert M.get(i).qual == "incremental"
    assert M.get(9).qual == "indirect"


def test_group_seven_fresh_differs_from_use():
    assert M.get(60).use == (10, 30) and M.get(60).fresh == (0.5, 3)


def test_economics_worked_example_from_the_study():
    # 500 000 USD, 200 m3/day, 15 years, 10 %
    assert M.invest_per_daily_capacity(500_000, 200 * 365) == pytest.approx(2500)
    assert M.invest_per_cumulative_m3(500_000, 200 * 365, 15) == pytest.approx(0.4566, abs=1e-4)
    assert M.crf(10, 15) == pytest.approx(0.131474, abs=1e-6)
    assert M.crf(0, 10) == pytest.approx(0.1)
    lcc = M.levelized_cost(500_000, 20_000, 200 * 365, 10, 15)
    assert lcc == pytest.approx((M.crf(10, 15) * 500_000 + 20_000) / 73_000)
    assert M.invest_per_daily_capacity(1, 0) is None
    assert M.payback_years(1000, 100, 100) is None


def test_search_filters():
    assert len(M.search(group=2)) == 12
    assert all("boiler" in m.targets for m in M.search(kind="boiler"))
    assert all(m.capex[0] <= 1 for m in M.search(max_capex=1))
    assert [m.id for m in M.search(text="(MBR)")] == [50]
    assert [m.id for m in M.search(text="۱۱")] == []          # ids are searched as ASCII digits
    assert 11 in [m.id for m in M.search(text="11")]


def test_estimates_for_demo_plant():
    p = demo_plant("en")
    es = M.estimates(p, M.get(11))                            # raise CoC -> cooling tower only
    assert len(es) == 1
    e = es[0]
    ct = [s for s in p.subsystems if s.kind == "cooling_tower"][0]
    assert e.target == ct.name and e.baseline == pytest.approx(ct.total_intake)
    assert e.low == pytest.approx(e.baseline * 0.05) and e.high == pytest.approx(e.baseline * 0.20)
    assert M.estimates(p, M.get(9)) == []                     # indirect: no number
    assert M.estimates(p, M.get(30))[0].baseline == pytest.approx(30000)
    # plant-wide measure uses total intake
    assert M.estimates(p, M.get(1))[0].baseline == pytest.approx(sum(s.total_intake for s in p.subsystems))
    rec = M.recommend(p)
    assert rec == sorted(rec, key=lambda e: e.mid, reverse=True)


def test_plan_combines_without_double_counting():
    p = demo_plant("en")
    ct = [s for s in p.subsystems if s.kind == "cooling_tower"][0]
    p.plan = [PlanItem(11, ct.name, 10.0, 1000, 0), PlanItem(12, ct.name, 10.0, 500, 0)]
    r = M.evaluate_plan(p)
    assert r.saving == pytest.approx(ct.total_intake * (1 - 0.9 * 0.9))      # 19 %, not 20 %
    assert sum(l.saving for l in r.lines) == pytest.approx(r.saving)
    assert "overlap:" + ct.name in r.warnings
    assert all(l.standalone == pytest.approx(ct.total_intake * 0.1) for l in r.lines)


def test_plan_plant_wide_acts_on_remaining_intake():
    p = demo_plant("en")
    tot = sum(s.total_intake for s in p.subsystems)
    proc = [s for s in p.subsystems if s.kind == "process"][0]
    p.plan = [PlanItem(30, proc.name, 20.0, 0, 0), PlanItem(48, "", 10.0, 0, 0)]
    r = M.evaluate_plan(p)
    expect = proc.total_intake * 0.2 + (tot - proc.total_intake * 0.2) * 0.1
    assert r.saving == pytest.approx(expect)
    assert r.saving < tot and 0 < r.saving_pct < 100


def test_plan_economics_and_flags():
    p = demo_plant("en")
    ct = [s for s in p.subsystems if s.kind == "cooling_tower"][0]
    p.plan = [PlanItem(11, ct.name, 12.5, 20000, 100, life_years=15, rate_pct=10)]
    r = M.evaluate_plan(p)
    l = r.lines[0]
    assert l.saving == pytest.approx(ct.total_intake * 0.125)
    assert l.i1 == pytest.approx(20000 / (l.saving / 365))
    assert l.i2 == pytest.approx(20000 / (l.saving * 15))
    assert l.lcc == pytest.approx((M.crf(10, 15) * 20000 + 100) / l.saving)
    assert l.payback == pytest.approx(20000 / (l.annual_value - 100))
    assert l.flags == []
    p.plan[0].saving_pct = 50                                  # outside the study's 5-20 % range
    assert "range" in M.evaluate_plan(p).lines[0].flags
    p.plan[0].target = "gone"
    assert "missing" in M.evaluate_plan(p).lines[0].flags
    assert M.evaluate_plan(Plant()).saving == 0


def test_plan_survives_save_and_load(tmp_path):
    p = demo_plant("en")
    p.plan = [PlanItem(11, p.subsystems[1].name, 12.5, 20000, 300, 15, 10, "note")]
    f = tmp_path / "a.wpj"
    save_project(p, str(f))
    q = load_project(str(f))
    assert q.plan == p.plan
    d = p.to_dict()
    d.pop("plan")                                              # project saved by an older version
    assert Plant.from_dict(d).plan == []


def test_cautions_are_text():
    for m in M.all_measures():
        for lang in ("fa", "en"):
            assert all(isinstance(c, str) and c for c in m.cautions(lang))
    assert M.get(52).cautions("en") and M.get(11).cautions("en") == []


def test_exports_include_the_plan(tmp_path):
    from openpyxl import load_workbook
    from waterprofiler.analysis import analyse
    from waterprofiler.export_xlsx import export_xlsx
    from waterprofiler.report_html import build_report_html
    plant = demo_plant("en")
    a = analyse(plant)
    path = str(tmp_path / "r.xlsx")
    export_xlsx(a, path, "en")
    wb = load_workbook(path)
    assert "Saving plan" in wb.sheetnames
    ws = wb["Saving plan"]
    assert ws.max_row >= len(plant.plan) + 1
    html = build_report_html(a, "en")
    assert "Saving plan" in html and "Cooling tower" in html
    plant.plan = []
    assert "Saving plan" not in build_report_html(analyse(plant), "en")


def test_demo_plan_is_consistent():
    plant = demo_plant("fa")
    res = M.evaluate_plan(plant)
    assert len(res.lines) == 4 and res.saving > 0
    assert all(not l.flags for l in res.lines)
    assert res.saving < sum(l.standalone for l in res.lines) + 1e-9
