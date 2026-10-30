import json

import pytest
from openpyxl import load_workbook

from waterprofiler import i18n, storage
from waterprofiler.analysis import analyse
from waterprofiler.cost import plant_cost
from waterprofiler.export_xlsx import export_xlsx
from waterprofiler.report_html import build_report_html
from waterprofiler.sample import demo_plant


def test_translations_complete():
    assert i18n.missing_translations() == []
    t = i18n.Translator("fa")
    assert t("save") == "ذخیره" and t.rtl
    assert i18n.Translator("en")("save") == "Save"
    assert t("no_such_key") == "no_such_key"


def test_every_ui_key_used_in_exports_exists():
    keys = set(i18n.all_keys())
    for k in ["st_balanced", "st_unaccounted loss", "st_excess outflow", "pr_both", "pr_volume", "pr_cost", "pr_low"]:
        assert k in keys
    for kind in ("process", "cooling_tower", "boiler", "sanitary", "irrigation", "other"):
        assert "kind_" + kind in keys


def test_project_roundtrip(tmp_path):
    p = demo_plant()
    f = tmp_path / "x.wpj"
    storage.save_project(p, str(f))
    p2 = storage.load_project(str(f))
    assert plant_cost(p2).total == pytest.approx(plant_cost(p).total)
    assert json.loads(f.read_text(encoding="utf-8"))["format"] == storage.FORMAT
    assert not list(tmp_path.glob(".wp_*"))          # no temp files left behind


def test_project_errors(tmp_path):
    bad = tmp_path / "bad.wpj"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(storage.ProjectFileError):
        storage.load_project(str(bad))
    other = tmp_path / "o.wpj"
    other.write_text(json.dumps({"format": "x"}), encoding="utf-8")
    with pytest.raises(storage.ProjectFileError):
        storage.load_project(str(other))
    newer = tmp_path / "n.wpj"
    newer.write_text(json.dumps({"format": storage.FORMAT, "schema": 99, "plant": {}}), encoding="utf-8")
    with pytest.raises(storage.ProjectFileError):
        storage.load_project(str(newer))
    with pytest.raises(storage.ProjectFileError):
        storage.load_project(str(tmp_path / "missing.wpj"))


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_excel_export(tmp_path, lang):
    a = analyse(demo_plant())
    f = tmp_path / "r.xlsx"
    export_xlsx(a, str(f), lang)
    wb = load_workbook(f)
    assert len(wb.sheetnames) >= 4
    cost_ws = wb[i18n.Translator(lang)("tab_cost")]
    assert cost_ws.max_row == len(a.plant.subsystems) + 2
    assert str(cost_ws.cell(row=cost_ws.max_row, column=2).value).startswith("=SUM(")
    assert wb.worksheets[0].sheet_view.rightToLeft == (lang == "fa")


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_report_html(lang):
    a = analyse(demo_plant())
    h = build_report_html(a, lang)
    assert h.startswith("<html") and h.rstrip().endswith("</html>")
    assert ('dir="rtl"' in h) == (lang == "fa")
    for s in a.plant.subsystems:
        assert s.name in h


def test_report_escapes_html():
    p = demo_plant()
    p.name = "<script>x</script>"
    assert "<script>" not in build_report_html(analyse(p), "en")
