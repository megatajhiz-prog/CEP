import dataclasses

import pytest

from waterprofiler import indicators as K
from waterprofiler.indicator_text import GROUP_TITLE, PROFILE_LABEL, TEXT
from waterprofiler.model import Outlet, Plant, Profile, Source, Subsystem
from waterprofiler.sample import demo_plant
from waterprofiler.storage import load_project, save_project


def small() -> Plant:
    """Two sources, one outlet, two subsystems with round numbers (hand-checkable)."""
    return Plant(
        name="t", production_per_year=1000.0,
        sources=[Source("A", 2.0, metered_m3=800.0), Source("B", 4.0, alternative=True)],
        outlets=[Outlet("S", 3.0, metered_m3=450.0)],
        subsystems=[
            Subsystem("X", "process", intake={"A": 600.0}, recirculated=200.0, product=100.0, evaporation=0.0,
                      discharge={"S": 400.0}, to_other=0.0),
            Subsystem("Y", "cooling_tower", intake={"A": 200.0, "B": 200.0}, recirculated=800.0, evaporation=300.0,
                      discharge={"S": 100.0}, params={"mc": 300.0, "bc": 1200.0}),
        ],
    )


def val(p, i):
    return K.compute(p).get(i).value


def test_hand_checked_values():
    p = small()
    # I = 1000, W = 500, E = 300, P = 100 -> L = 100; gross = 1000 + 1000 = 2000
    assert val(p, "sup_intake") == 1000
    assert val(p, "sup_largest_share") == pytest.approx(80.0)          # A = 800 of 1000
    assert val(p, "sup_hhi") == pytest.approx(0.8 ** 2 + 0.2 ** 2)
    assert val(p, "sup_alt_share") == pytest.approx(20.0)
    assert val(p, "sup_avg_cost") == pytest.approx((800 * 2 + 200 * 4) / 1000)
    assert val(p, "sup_meter_cover") == pytest.approx(80.0)
    assert val(p, "use_gross") == 2000
    assert val(p, "use_reuse_factor") == pytest.approx(2.0)
    assert val(p, "use_recirc_ratio") == pytest.approx(50.0)
    assert val(p, "use_consumption") == 500                            # I - W (GRI 303-5)
    assert val(p, "use_loss_m3") == pytest.approx(100.0)
    assert val(p, "use_loss_fraction") == pytest.approx(10.0)
    assert val(p, "use_per_unit") == pytest.approx(1.0)
    assert val(p, "use_consumption_per_unit") == pytest.approx(0.5)
    assert val(p, "ww_fraction") == pytest.approx(50.0)
    assert val(p, "ww_avg_cost") == pytest.approx(3.0)
    assert val(p, "ww_largest_outlet") == pytest.approx(100.0)
    assert val(p, "q_outlet_meter_cover") == pytest.approx(100.0)
    assert val(p, "cost_total") == pytest.approx(800 * 2 + 200 * 4 + 500 * 3)


def test_shares_sum_to_100():
    r = K.compute(demo_plant("en"))
    parts = [r.get("cost_share_" + c).value for c in ("intake", "water_treatment", "pumping",
                                                       "wastewater_treatment", "discharge", "heat")]
    assert sum(parts) == pytest.approx(100.0)
    assert r.get("use_internal_share").value + r.get("use_transfer_share").value == pytest.approx(
        r.get("use_recirc_ratio").value)


def test_missing_inputs_are_reported_not_guessed():
    p = small()
    r = K.compute(p)
    for i in ("sup_storage_days", "use_per_revenue", "ww_cod_removal", "tg_loss", "sup_ili"):
        ind = r.get(i)
        assert ind.value is None and ind.reason == "inputs" and ind.needs
    assert r.get("sup_ili").approx
    assert r.completeness == 0.0
    assert r.get("sup_permit_use").value is None and r.get("sup_permit_use").reason == "permit"   # no source limit is on
    assert 0 < r.computable < 100


def test_profile_indicators():
    p = small()
    p.profile = Profile(storage_m3=500, outage_hours=87.6, revenue=2e6, value_added=5000,
                        cod_raw=800, cod_out=100, tds_intake=300, tds_discharge=1200,
                        target_intake_per_unit=0.8, target_recirc_pct=60, target_loss_pct=4,
                        network_km=1.0, connections=10, pressure_m=40)
    assert val(p, "sup_storage_days") == pytest.approx(500 / (1000 / 365))
    assert val(p, "sup_availability") == pytest.approx(99.0)
    assert val(p, "use_per_revenue") == pytest.approx(500.0)           # 1000 m3 / 2 million
    assert val(p, "use_productivity") == pytest.approx(5.0)
    assert val(p, "ww_cod_raw_load") == pytest.approx(800 * 500 / 1000)
    assert val(p, "ww_cod_removal") == pytest.approx(87.5)
    assert val(p, "ww_tds_load") == pytest.approx((1200 * 500 - 300 * 1000) / 1000)
    assert val(p, "ww_tds_factor") == pytest.approx(4.0)
    assert val(p, "tg_intake_unit") == pytest.approx(0.2)
    assert val(p, "tg_intake_unit_pct") == pytest.approx(25.0)
    assert val(p, "tg_recirc") == pytest.approx(-10.0)
    assert val(p, "tg_loss") == pytest.approx(6.0)
    uarl = (18 * 1 + 0.8 * 10) * 40 * 365 / 1000
    assert val(p, "sup_ili") == pytest.approx(100 / uarl)


def test_sub_production_cycles_and_blowdown():
    p = small()
    p.profile.sub_production = {"X": 400.0}
    rows = {s.name: s.values for s in K.compute(p).subsystems}
    assert rows["X"]["per_unit"] == pytest.approx(600 / 400)
    assert rows["Y"]["cycles"] == pytest.approx(4.0)
    assert rows["Y"]["blowdown"] == pytest.approx(25.0)               # 100 of 400 make-up
    assert rows["X"]["cycles"] is None
    assert rows["X"]["intake_share"] + rows["Y"]["intake_share"] == pytest.approx(100.0)


def test_empty_and_zero_plants_do_not_crash():
    r = K.compute(Plant())
    assert all(i.value is None or isinstance(i.value, float) for i in r.items)
    z = Plant(sources=[Source("A")], subsystems=[Subsystem("X")])
    K.compute(z)


def test_catalogue_is_complete_and_bilingual():
    r = K.compute(demo_plant("en"))
    ids = [i.id for i in r.items]
    assert len(ids) == len(set(ids)) >= 75
    assert set(ids) == set(TEXT)
    assert {i.group for i in r.items} <= set(K.GROUPS) == set(GROUP_TITLE)
    for k, v in TEXT.items():
        assert v[0] and v[1] and v[2], k
    for f in K.PROFILE_FIELDS:
        assert f in PROFILE_LABEL
    for i in r.items:
        for n in i.needs:
            assert n in PROFILE_LABEL


def test_profile_roundtrip_and_old_files(tmp_path):
    p = small()
    p.profile = Profile(employees=120, revenue=5e6, sub_production={"X": 10.0})
    f = tmp_path / "a.wpj"
    save_project(p, str(f))
    q = load_project(str(f))
    assert q.profile == p.profile and q.sources[1].alternative is True
    d = p.to_dict()
    d.pop("profile")
    d["sources"][0].pop("alternative")
    old = Plant.from_dict(d)
    assert old.profile == Profile() and old.sources[0].alternative is False
    assert dataclasses.asdict(Profile()).keys() >= set(K.PROFILE_FIELDS)


def test_excel_and_report_carry_the_indicators(tmp_path):
    from openpyxl import load_workbook

    from waterprofiler.analysis import analyse
    from waterprofiler.export_xlsx import export_xlsx
    from waterprofiler.i18n import Translator
    from waterprofiler.report_html import build_report_html

    p = demo_plant("fa")
    for s in p.sources:
        s.permit_on, s.permit_m3 = True, 60000.0
    a = analyse(p)
    export_xlsx(a, str(tmp_path / "x.xlsx"), "fa")
    wb = load_workbook(tmp_path / "x.xlsx")
    ws = wb[Translator("fa")("sheet_ind")]
    flat = [c.value for row in ws.iter_rows() for c in row]
    assert TEXT["sup_permit_use"][0] in flat and TEXT["use_reuse_factor"][0] in flat
    permit = [r for r in ws.iter_rows(values_only=True) if r[0] == TEXT["sup_permit_use"][0]][0]
    assert permit[1] == pytest.approx(100.0 * K.compute(p).get("sup_intake").value / (60000.0 * len(p.sources)))
    html = build_report_html(a, "fa")
    assert TEXT["use_per_unit"][0] in html and GROUP_TITLE["supply"][0] in html
    assert TEXT["ww_cod_removal"][0] not in html            # not computable -> not printed in the report
    html_en = build_report_html(a, "en")
    assert TEXT["use_per_unit"][1] in html_en
