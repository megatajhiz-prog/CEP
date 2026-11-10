import pytest
from waterprofiler import allocation as AL, structure as ST
from waterprofiler.model import Plant, Subsystem, Source, Outlet, Product
from waterprofiler.cost import plant_cost


def _plant():
    p = Plant(name="t", production_unit="t", sources=[Source("W", 2.0)], outlets=[Outlet("O", 0.0)])
    p.site.products = [Product("Tile", "m2", per_year=1000.0), Product("Glaze", "t", per_year=50.0)]
    p.subsystems = [Subsystem(name="Line1", intake={"W": 600.0}, product=100.0, evaporation=200.0, discharge={"O": 300.0}),
                    Subsystem(name="Line2", intake={"W": 300.0}, product=50.0, evaporation=100.0, discharge={"O": 150.0}),
                    Subsystem(name="Utility", kind="sanitary", intake={"W": 100.0}, discharge={"O": 100.0})]
    return p


def test_fractions_split_and_conserve():
    p = _plant()
    AL.set_fractions(p, "Line1", {"Tile": 1.0})
    AL.set_fractions(p, "Line2", {"Tile": 0.4, "Glaze": 0.6})
    r = AL.allocate(p)
    by = {x.name: x for x in r.products}
    assert by["Tile"].intake == pytest.approx(600 + 120)
    assert by["Glaze"].intake == pytest.approx(180)
    assert r.general.intake == pytest.approx(100)                 # the utility is not spread silently
    assert sum(x.intake for x in r.products) + r.general.intake == pytest.approx(r.total_intake)
    assert sum(x.cost for x in r.products) + r.general.cost == pytest.approx(r.total_cost)
    assert r.total_cost == pytest.approx(plant_cost(p).total)
    assert r.allocated_pct == pytest.approx(90.0)


def test_intensity_is_per_product_unit_and_mixed_units_flagged():
    p = _plant()
    AL.set_fractions(p, "Line1", {"Tile": 1.0})
    AL.set_fractions(p, "Line2", {"Glaze": 1.0})
    r = AL.allocate(p)
    by = {x.name: x for x in r.products}
    assert by["Tile"].per_unit_intake == pytest.approx(0.6)       # m3 per m2
    assert by["Glaze"].per_unit_intake == pytest.approx(6.0)      # m3 per t
    assert "alloc_mixed_units" in r.warnings


def test_validation_and_warnings():
    p = _plant()
    with pytest.raises(ValueError):
        AL.set_fractions(p, "Line1", {"Tile": 0.7, "Glaze": 0.5})
    with pytest.raises(ValueError):
        AL.set_fractions(p, "Nope", {"Tile": 1.0})
    p.allocation["Line1"] = {"Ghost": 1.0}
    r = AL.allocate(p)
    assert any(w.startswith("alloc_unknown_product:Line1:Ghost") for w in r.warnings)
    assert r.general.intake == pytest.approx(r.total_intake)       # nothing valid allocated


def test_split_by_weights():
    p = _plant()
    AL.split_by_weights(p, "Line1", {"Tile": 3, "Glaze": 1})
    assert p.allocation["Line1"] == {"Tile": 0.75, "Glaze": 0.25}


def test_equipment_allocation_and_unit_rollup():
    p = _plant()
    AL.set_fractions(p, "Line1", {"Tile": 1.0})
    ST.add_equipment(p, "Line1", "Kiln")                           # data and allocation move to the holder equipment
    assert "Line1" not in p.allocation and p.allocation["Line1 · unallocated"] == {"Tile": 1.0}
    with pytest.raises(ValueError):
        AL.set_fractions(p, "Line1", {"Tile": 1.0})               # a unit with equipment is not allocated itself
    r = AL.allocate(p)
    assert {x.name: x for x in r.products}["Tile"].intake == pytest.approx(600)


def test_rename_remove_and_roundtrip():
    p = _plant()
    AL.set_fractions(p, "Line2", {"Glaze": 0.5})
    ST.rename_node(p, "Line2", "Line B")
    assert p.allocation == {"Line B": {"Glaze": 0.5}}
    q = Plant.from_dict(p.to_dict())
    assert q.allocation == {"Line B": {"Glaze": 0.5}}
    ST.remove_node(q, "Line B")
    assert q.allocation == {}


def test_demo_allocation_and_exports(tmp_path):
    from waterprofiler.analysis import analyse
    from waterprofiler.report_html import build_report_html
    from waterprofiler.export_xlsx import export_xlsx
    from waterprofiler.sample import demo_with_history
    import openpyxl
    p = demo_with_history("en")
    a = analyse(p)
    r = AL.allocate(p, a.cost)
    assert 0 < r.allocated_pct < 100 and r.general.intake > 0 and not r.warnings
    html = build_report_html(a, "en")
    assert "Water by product" in html
    out = tmp_path / "x.xlsx"
    export_xlsx(a, str(out), "en")
    assert "Water by product" in openpyxl.load_workbook(out).sheetnames
