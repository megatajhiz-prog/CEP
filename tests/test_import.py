"""Excel import/export of plant inputs."""

import pytest

from waterprofiler.cost import plant_cost
from waterprofiler.importer import ImportProblem, export_input_workbook, import_workbook, write_template
from waterprofiler.model import Plant
from waterprofiler.sample import demo_plant


def same(a, b):
    """Plant dicts equal up to the 15-16 significant digits an Excel cell keeps (the saving plan is not part of the input workbook)."""
    if isinstance(a, dict) and isinstance(b, dict):
        a, b = {k: v for k, v in a.items() if k != "plan"}, {k: v for k, v in b.items() if k != "plan"}
    return a == pytest.approx(b, rel=1e-12) if not isinstance(a, (dict, list)) else _walk(a, b)


def _walk(a, b):
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_walk(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_walk(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return a == pytest.approx(b, rel=1e-12)
    return a == b


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_roundtrip_demo(tmp_path, lang):
    plant = demo_plant(lang)
    p = str(tmp_path / "in.xlsx")
    export_input_workbook(plant, p, lang)
    back, warns = import_workbook(p, lang)
    assert warns == []
    assert same(back.to_dict(), plant.to_dict())
    assert plant_cost(back).total == pytest.approx(plant_cost(plant).total, rel=1e-12)


def test_cross_language_headers(tmp_path):
    """A file written with Persian headers imports fine while the UI is English, and vice versa."""
    plant = demo_plant("fa")
    p = str(tmp_path / "in.xlsx")
    export_input_workbook(plant, p, "fa")
    back, warns = import_workbook(p, "en")
    back.site.products[0].name = plant.site.products[0].name        # the default product is named in the UI language
    assert same(back.to_dict(), plant.to_dict())
    assert warns == []


def test_template_is_importable(tmp_path):
    for lang in ("fa", "en"):
        p = str(tmp_path / f"t_{lang}.xlsx")
        write_template(p, lang)
        plant, warns = import_workbook(p, lang)
        assert warns == []
        assert len(plant.subsystems) == 1 and plant.subsystems[0].total_intake == 5000.0
        assert plant_cost(plant).total > 0


def test_problems_are_reported_not_raised(tmp_path):
    from openpyxl import load_workbook
    p = str(tmp_path / "in.xlsx")
    export_input_workbook(demo_plant("en"), p, "en")
    wb = load_workbook(p)
    flows = wb.worksheets[5]
    flows.append(["Nope", "intake", "Municipal", 5])             # unknown subsystem
    flows.append(["Process", "intake", "No such source", 5])      # unknown source
    flows.append(["Process", "evaporation", None, "abc"])         # not a number
    flows.append(["Process", "teleport", None, 1])                # unknown flow type
    wb.save(p)
    plant, warns = import_workbook(p, "en")
    assert len(warns) == 4
    assert same(plant.to_dict(), demo_plant("en").to_dict())          # bad rows changed nothing


def test_persian_digits_and_bad_file(tmp_path):
    from openpyxl import load_workbook
    p = str(tmp_path / "in.xlsx")
    export_input_workbook(demo_plant("en"), p, "en")
    wb = load_workbook(p)
    wb.worksheets[1]["B2"] = "۱٫۴"                                 # Persian digits and decimal mark
    wb.save(p)
    plant, _ = import_workbook(p, "en")
    assert plant.sources[0].unit_cost == pytest.approx(1.4)
    bad = tmp_path / "bad.xlsx"
    bad.write_text("not a workbook")
    with pytest.raises(ImportProblem):
        import_workbook(str(bad), "en")
