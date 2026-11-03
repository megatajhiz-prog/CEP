import dataclasses
import math

import pytest

from waterprofiler import economics as E
from waterprofiler.measures import evaluate_plan
from waterprofiler.sample import demo_plant
from waterprofiler.storage import load_project, save_project


def base(**kw):
    d = dict(saving_m3=1.0, price=300.0, capex=1000.0, life=5, rate_pct=10.0)
    d.update(kw)
    return E.EconInputs(**d)


def test_textbook_annuity():
    r = E.evaluate(base())
    ann = sum(1 / 1.1 ** t for t in range(1, 6))               # 3.790787...
    assert r.npv == pytest.approx(300 * ann - 1000, abs=1e-9)
    assert r.irr == pytest.approx(15.2382, abs=1e-3)
    assert r.payback == pytest.approx(1000 / 300, abs=1e-9)
    assert r.dpayback == pytest.approx(4.2633, abs=1e-3)
    assert r.bcr == pytest.approx(300 * ann / 1000, abs=1e-9)
    assert r.pi == pytest.approx(r.npv / 1000)
    assert r.verdict == "good" or r.verdict == "marginal"
    assert abs(E.npv_of(r.irr / 100, r.net)) < 1e-6          # IRR zeroes the NPV


def test_study_example_levelised_cost():
    # study 4-3: 500 000 invested, 200 m3/day, 15 years, 10 %  -> discounted-volume cost per m3
    r = E.evaluate(E.EconInputs(saving_m3=200 * 365, price=0.0, capex=500_000, life=15, rate_pct=10.0))
    pv = 73_000 * sum(1 / 1.1 ** t for t in range(1, 16))
    assert r.lcow == pytest.approx(500_000 / pv, rel=1e-12)
    assert 500_000 / (200 * 365 * 15) == pytest.approx(0.4566, abs=1e-4)      # undiscounted I2 of the study


def test_breakeven_price_equals_lcow():
    r = E.evaluate(base(price=0.0, saving_m3=100, opex=50))
    p = r.lcow
    r2 = E.evaluate(base(price=p, saving_m3=100, opex=50))
    assert r2.npv == pytest.approx(0.0, abs=1e-8)
    assert r2.bcr == pytest.approx(1.0, abs=1e-12)


def test_escalation_degradation_salvage_replacement():
    r = E.evaluate(base(saving_m3=1, price=300, price_esc_pct=10, degradation_pct=0, rate_pct=10))
    # benefits grow exactly at the discount rate -> every discounted benefit is 300 / 1.1
    assert r.pv_benefit == pytest.approx(5 * 300 / 1.1)
    r = E.evaluate(base(salvage=500, repl_year=3, repl_cost=200, opex=10, opex_esc_pct=5, degradation_pct=10))
    assert r.volume[2] == pytest.approx(0.9)
    assert r.net[5] == pytest.approx(300 * 0 + (0.9 ** 4) * 300 + 500 - 10 * 1.05 ** 4)
    assert r.cost[3] == pytest.approx(10 * 1.05 ** 2 + 200)
    assert r.lcow is not None and r.lcow > 0


def test_no_payback_and_no_irr_cases():
    r = E.evaluate(base(price=10.0))               # never recovers
    assert r.payback is None and r.dpayback is None and r.npv < 0 and r.verdict == "poor"
    assert r.irr is None or r.irr < 10
    r = E.evaluate(base(capex=0.0))                # nothing invested: no IRR, payback 0
    assert r.irr is None and r.payback == 0.0 and r.pi is None
    r = E.evaluate(base(saving_m3=0.0))
    assert r.verdict == "invalid"


def test_irr_negative_and_zero_rate():
    r = E.evaluate(base(price=150.0))              # 5*150 = 750 < 1000 : negative IRR
    assert r.irr is not None and r.irr < 0
    assert abs(E.npv_of(r.irr / 100, r.net)) < 1e-6
    r = E.evaluate(base(rate_pct=0.0))
    assert r.npv == pytest.approx(500.0) and r.dpayback == pytest.approx(r.payback)


def test_validation():
    for kw in ({"life": 0}, {"capex": -1}, {"degradation_pct": 100}, {"repl_year": 9}, {"rate_pct": -80}):
        with pytest.raises(E.EconError):
            E.evaluate(base(**kw))


def test_sensitivity_orders_by_swing():
    rows = E.sensitivity(base(saving_m3=2, price=300, opex=20))
    assert {r[0] for r in rows} == set(E.SENS_VARS)
    assert [r[3] for r in rows] == sorted((r[3] for r in rows), reverse=True)
    price_row = next(r for r in rows if r[0] == "price")
    assert price_row[2] > price_row[1]            # higher price, higher NPV
    capex_row = next(r for r in rows if r[0] == "capex")
    assert capex_row[2] < capex_row[1]


def test_plan_items_use_their_share_and_plant_prices():
    p = demo_plant("en")
    assert p.plan
    items = E.evaluate_plan_economics(p)
    assert len(items) == len(p.plan)
    lines = {id(l.item): l for l in evaluate_plan(p).lines}
    for ie in items:
        assert ie.result is not None
        assert ie.result.inputs.saving_m3 == pytest.approx(lines[id(ie.item)].saving)
        assert ie.result.inputs.price == pytest.approx(E.default_price(p, ie.item.target))
        assert ie.result.inputs.price > 0
    # an explicit water price overrides the automatic one
    it = p.plan[0]
    it.water_price = 9.99
    assert E.inputs_from_item(p, it).price == 9.99


def test_economic_fields_roundtrip_and_old_files_load(tmp_path):
    p = demo_plant("en")
    it = p.plan[0]
    it.water_price, it.price_esc_pct, it.salvage, it.repl_year, it.repl_cost = 2.5, 4.0, 100.0, 7, 300.0
    f = tmp_path / "p.wpj"
    save_project(p, str(f))
    q = load_project(str(f))
    assert dataclasses.asdict(q.plan[0]) == dataclasses.asdict(it)
    # a project saved before the economic fields existed still opens
    import json
    d = json.loads(f.read_text(encoding="utf8"))
    for pi in d["plant"]["plan"]:
        for k in ("water_price", "price_esc_pct", "opex_esc_pct", "degradation_pct", "other_benefit", "salvage",
                  "repl_year", "repl_cost"):
            pi.pop(k)
    f.write_text(json.dumps(d), encoding="utf8")
    assert load_project(str(f)).plan[0].water_price == 0.0
    assert not math.isnan(E.evaluate(E.inputs_from_item(q, q.plan[0])).npv)


def test_excel_and_report_include_economics(tmp_path):
    from openpyxl import load_workbook
    from waterprofiler.analysis import analyse
    from waterprofiler.export_xlsx import export_xlsx
    from waterprofiler.report_html import build_report_html
    a = analyse(demo_plant("fa"))
    export_xlsx(a, str(tmp_path / "x.xlsx"), "fa")
    wb = load_workbook(tmp_path / "x.xlsx")
    ws = wb["ارزیابی اقتصادی"]
    assert ws.max_row > len(a.plant.plan) + 4
    npvs = [ws.cell(row=i, column=8).value for i in range(2, 2 + len(a.plant.plan))]
    assert all(isinstance(v, float) for v in npvs)
    html = build_report_html(a, "fa")
    assert "ارزیابی اقتصادی" in html and "NPV" in html
