import json
from datetime import date

from openpyxl import load_workbook

from waterprofiler import complex as CX
from waterprofiler.export_xlsx import export_xlsx
from waterprofiler.analysis import analyse
from waterprofiler.model import Plant
from waterprofiler.report_html import build_report_html
from waterprofiler.sample import demo_with_history


def test_area_rows_cover_all_subsystems_and_shares_sum_to_100():
    p = demo_with_history("en")
    rows = CX.area_rows(p)
    assert sum(len(r.subsystems) for r in rows) == len(p.subsystems)
    assert abs(sum(r.share for r in rows) - 100.0) < 1e-9
    assert abs(sum(r.intake for r in rows) - sum(s.total_intake for s in p.subsystems)) < 1e-6
    p.subsystems[0].area = ""
    assert any(r.name == "" and p.subsystems[0].name in r.subsystems for r in CX.area_rows(p))


def test_meter_due():
    assert CX.meter_due("2026-01-01", date(2026, 6, 1)) == (151, False)
    assert CX.meter_due("2024-01-01", date(2026, 6, 1))[1] is True
    assert CX.meter_due("", date(2026, 6, 1)) == (None, True)


def test_old_file_migrates_working_days_and_name():
    p = demo_with_history("en")
    d = json.loads(json.dumps(p.to_dict()))
    d["profile"]["working_days"] = 0
    d["site"]["operating_days"] = 280
    d["site"]["name"] = "another name"
    q = Plant.from_dict(d)
    assert q.profile.working_days == 280 and q.site.operating_days == 0 


def test_exports_contain_the_complex(tmp_path):
    p = demo_with_history("fa")
    a = analyse(p)
    f = tmp_path / "x.xlsx"
    export_xlsx(a, str(f), "fa")
    wb = load_workbook(f)
    assert "مجتمع صنعتی" in wb.sheetnames
    ws = wb["مجتمع صنعتی"]
    text = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
    assert p.site.owner in text and p.site.areas[0].name in text and p.site.meters[0].name in text
    html = build_report_html(a, "fa")
    assert p.site.owner in html and p.site.meters[0].name in html
