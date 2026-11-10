"""Headless GUI smoke test. Skipped where PySide6 is not installed (runs in CI)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))


def _win(lang):
    from waterprofiler.gui.main_window import MainWindow
    w = MainWindow(lang)
    w.show()
    return w


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_all_tabs_with_demo(app, lang, tmp_path):
    w = _win(lang)
    w.action_demo()
    assert len(w.plant.subsystems) == 5
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        app.processEvents()
    assert w.balance_tab.table.rowCount() == 5
    assert w.cost_tab.table.rowCount() == 6        # 5 subsystems + total row
    w.export_xlsx_to(str(tmp_path / "r.xlsx"))
    w.export_pdf_to(str(tmp_path / "r.pdf"))
    assert (tmp_path / "r.xlsx").stat().st_size > 2000
    assert (tmp_path / "r.pdf").stat().st_size > 2000
    w.close()


def test_edit_roundtrip_does_not_change_plant(app):
    from waterprofiler import timeseries as TS
    from waterprofiler.sample import demo_with_history
    w = _win("en")
    w.action_demo()
    base = demo_with_history("en")
    TS.sync(base)                                  # the model carries the series-driven values from the start
    before = base.to_dict()
    w.tabs.setCurrentWidget(w.subs_page)
    for r in range(w.sub_list.count()):
        w.sub_list.setCurrentRow(r)
    w.tabs.setCurrentIndex(0)
    w.collect()
    after = w.plant.to_dict()
    assert after["subsystems"][1]["evaporation"] == pytest.approx(before["subsystems"][1]["evaporation"])
    assert [s["name"] for s in after["subsystems"]] == [s["name"] for s in before["subsystems"]]
    assert after["costs"] == before["costs"]
    from waterprofiler.cost import plant_cost
    from waterprofiler.model import Plant
    assert plant_cost(Plant.from_dict(after)).total == pytest.approx(plant_cost(Plant.from_dict(before)).total, rel=1e-9)
    w.close()


def test_save_open_and_language_switch(app, tmp_path):
    w = _win("fa")
    w.action_demo()
    p = str(tmp_path / "x.wpj")
    assert w._save_to(p)
    w.set_language("en")
    assert w.t.lang == "en" and len(w.plant.subsystems) == 5
    w.set_language("fa")
    assert not w._is_dirty()
    w.close()


def test_add_remove_subsystem_and_reconcile(app):
    w = _win("en")
    w.action_demo()
    w._add_subsystem()
    assert len(w.plant.subsystems) == 6
    w._remove_subsystem()
    assert len(w.plant.subsystems) == 5
    w.plant.subsystems[1].evaporation *= 1.3
    w._load_all(1)
    w.tabs.setCurrentIndex(w.tabs.count() - 1)
    w.reconcile_tab._run()
    assert w.reconcile_tab.table.rowCount() > 0
    w.reconcile_tab._apply()
    from waterprofiler.balance import plant_balance
    assert abs(plant_balance(w.plant).unknown_loss) < 1e-3 * plant_balance(w.plant).sum_intake
    w.close()


def test_savings_tab_computes(app):
    w = _win("en")
    w.action_demo()
    w.tabs.setCurrentWidget(w.savings_tab)
    st = w.savings_tab
    st._calc_ct()
    assert "Water saved" in st.ct_out.text() or "صرفه" in st.ct_out.text()
    st.lk_rate.setValue(2.0)
    st._calc_leak()
    assert st.lk_out.text()
    w.close()


def test_import_from_excel_and_sidebar_navigation(app, tmp_path):
    from waterprofiler.importer import export_input_workbook
    from waterprofiler.sample import demo_plant
    w = _win("fa")
    p = str(tmp_path / "in.xlsx")
    export_input_workbook(demo_plant("fa"), p, "fa")
    assert w.import_from(p) == []
    assert len(w.plant.subsystems) == 5
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        app.processEvents()
        assert w.nav[i].isChecked()
        assert w.page_title.text() == w.t(w._pages[i][1])
    w.nav[w.tabs.indexOf(w.flow_tab)].click()
    assert w.tabs.currentWidget() is w.flow_tab
    assert w.balance_tab.table.rowCount() == 5
    assert w.cost_tab.c_true.value.text() not in ("", "—")
    w.close()


def test_about_dialog_and_branding(app):
    from waterprofiler.gui.dialogs import AboutDialog
    from waterprofiler.i18n import Translator
    for lang in ("fa", "en"):
        d = AboutDialog(Translator(lang))
        d.show()
        d.close()
    w = _win("en")
    assert "CEPWater" in w.windowTitle()
    assert not w.windowIcon().isNull()
    w.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_measures_and_plan_tabs(app, lang):
    from waterprofiler import measures as M
    w = _win(lang)
    w.action_demo()
    w.tabs.setCurrentWidget(w.measures_tab)
    app.processEvents()
    assert w.measures_tab.table.rowCount() == 80
    w.measures_tab.select(11)
    assert w.measures_tab.selected().id == 11
    assert w.measures_tab.target.count() >= 1
    # filters
    w.measures_tab.group.setCurrentIndex(2)             # group 2: cooling
    assert w.measures_tab.table.rowCount() == 12
    # adding a measure goes to the plan and switches page
    before = len(w.plant.plan)
    w.measures_tab.select(12)                           # automatic blowdown control, not in the demo plan
    assert w.measures_tab.selected().id == 12
    w.measures_tab._add()
    assert w.tabs.currentWidget() is w.plan_tab
    assert len(w.plant.plan) == before + 1
    assert w.plan_tab.inputs.rowCount() == len(w.plant.plan)
    assert w.plan_tab.results.rowCount() == len(w.plant.plan)
    # editing a percentage recomputes the result
    sp = w.plan_tab.inputs.cellWidget(0, 2)
    sp.setValue(7.0)
    assert w.plant.plan[0].saving_pct == 7.0
    # removal
    n = len(w.plant.plan)
    w.plan_tab.inputs.cellWidget(0, 7).click()          # per-row delete button
    assert len(w.plant.plan) == n - 1
    assert w.plan_tab.inputs.rowCount() == n - 1
    w.plan_tab._clear()
    assert w.plan_tab.results.rowCount() == 0
    assert M.evaluate_plan(w.plant).saving == 0
    w.close()


def test_cost_tab_suggests_measures(app):
    w = _win("en")
    w.action_demo()
    w.tabs.setCurrentWidget(w.cost_tab)
    app.processEvents()
    assert w.cost_tab.sugg.rowCount() == 8
    w.close()


def test_flow_tab_draws_edits_links_and_exports(app, tmp_path):
    from waterprofiler.gui.flow_tab import render_png
    w = _win("fa")
    w.action_demo()
    w.tabs.setCurrentWidget(w.flow_tab)
    ft = w.flow_tab
    assert ft.diagram.graph.nodes and ft.diagram.graph.edges
    out = tmp_path / "flow.png"
    assert render_png(ft.diagram.graph, str(out), True, w.t)
    assert out.stat().st_size > 5000
    names = [s.name for s in w.plant.subsystems]
    ft.table.add_row([names[1], names[4], 500.0])
    assert [(x.src, x.dst, x.volume) for x in w.plant.links] == [(names[1], names[4], 500.0)]
    assert w.plant.subsystems[1].to_other == 500.0 and w.plant.subsystems[4].from_other == 500.0
    assert any(e.kind == "transfer" for e in ft.diagram.graph.edges)
    ft.table.setCurrentCell(0, 0)
    ft.table.remove_selected()
    assert w.plant.links == [] and w.plant.subsystems[1].to_other == 0.0
    ft.subsystem_requested.emit(names[2])
    assert w.tabs.currentWidget() is w.subs_page and w.sub_list.currentRow() == 2
    w.export_pdf_to(str(tmp_path / "r.pdf"))
    assert (tmp_path / "r.pdf").stat().st_size > 2000
    w.close()


def test_flow_diagram_interactive_editing(app, monkeypatch):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QInputDialog
    from waterprofiler.gui.flow_tab import port_center
    w = _win("fa")
    w.action_demo()
    w.tabs.setCurrentWidget(w.flow_tab)
    ft = w.flow_tab
    plant = w.plant
    boiler = plant.subsystems[2]
    well = plant.sources[1].name
    monkeypatch.setattr(QInputDialog, "getDouble", staticmethod(lambda *a, **k: (500.0, True)))
    # context-menu path: new intake from the second source into the boiler
    before = boiler.intake.get(well, 0.0)
    ft._add_flow(f"source:{well}", f"subsystem:{boiler.name}")
    assert boiler.intake[well] == before + 500.0
    assert ft.undo_btn.isEnabled()
    ft.undo()
    assert plant.subsystems[2].intake.get(well, 0.0) == before
    # edit and delete through edge indices
    i = next(k for k, e in enumerate(ft.diagram.graph.edges) if e.kind == "discharge")
    e = ft.diagram.graph.edges[i]
    ft._edit_edge(i)
    assert plant.subsystems[[s.name for s in plant.subsystems].index(e.sub)].discharge[e.ref] == 500.0
    ft._delete_edge(next(k for k, x in enumerate(ft.diagram.graph.edges) if x.kind == "discharge" and x.sub == e.sub and x.ref == e.ref))
    assert e.ref not in plant.subsystems[[s.name for s in plant.subsystems].index(e.sub)].discharge
    # node reorder is stored in the layout and survives a redraw
    ft._layout_changed({f"subsystem:{plant.subsystems[0].name}": 10_000.0})
    assert plant.layout
    ft._reset_layout()
    assert plant.layout == {}
    # real mouse drag from a source handle onto the boiler node creates / increases the intake
    app.processEvents()
    ft.diagram.repaint()           # refresh the hit boxes for the widget's real size
    hits = {n.id: r for r, n in ft.diagram._hits}
    src_n = next(n for n in ft.diagram.graph.nodes if n.id == f"source:{well}")
    c = port_center(hits[src_n.id], src_n, True)
    t = hits[f"subsystem:{boiler.name}"].center()
    cur = plant.subsystems[2].intake.get(well, 0.0)
    QTest.mouseMove(ft.diagram, QPoint(int(c.x()), int(c.y())))
    QTest.mousePress(ft.diagram, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(c.x()), int(c.y())))
    assert ft.diagram._mode == "connect", (c, hits[src_n.id], ft.diagram._node_at(c), ft.diagram.size())
    QTest.mouseMove(ft.diagram, QPoint(int(t.x()), int(t.y())))
    assert ft.diagram._node_at(t) is not None and ft.diagram._node_at(t).id == f"subsystem:{boiler.name}", (t, ft.diagram.size())
    QTest.mouseRelease(ft.diagram, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(t.x()), int(t.y())))
    assert plant.subsystems[2].intake.get(well, 0.0) == cur + 500.0
    w.close()


def test_econ_tab_shows_indicators_edits_and_exports(app, tmp_path):
    w = _win("fa")
    w.action_demo()
    w.tabs.setCurrentWidget(w.econ_tab)
    et = w.econ_tab
    assert et.combo.count() == len(w.plant.plan) > 0
    assert et.cmp.rowCount() == len(w.plant.plan)
    assert et.flows.rowCount() == int(w.plant.plan[0].life_years) + 1
    assert et.verdict.isVisible() or et.verdict.text()
    assert "%" in et.c_irr.value.text() or "—" in et.c_irr.value.text()
    # editing an input changes the shared plan item and the indicators
    before = et.c_npv.value.text()
    et.spins["capex"].setValue(w.plant.plan[0].capex * 10)
    assert w.plant.plan[0].capex == et.spins["capex"].value()
    assert et.c_npv.value.text() != before
    et.spins["life_years"].setValue(30)
    assert et.flows.rowCount() == 31
    et.spins["repl_year"].setValue(99)                 # outside the life: rejected, no crash
    assert et.msg.text()
    et.spins["repl_year"].setValue(0)
    # another measure through the comparison table
    et.cmp.cellClicked.emit(1, 0)
    assert et.combo.currentIndex() == 1
    # all tabs still switch and the exports carry the economics
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
    w.export_xlsx_to(str(tmp_path / "e.xlsx"))
    from openpyxl import load_workbook
    names = load_workbook(tmp_path / "e.xlsx").sheetnames
    assert w.t("sheet_econ") in names
    w.export_pdf_to(str(tmp_path / "e.pdf"))
    assert (tmp_path / "e.pdf").stat().st_size > 2000
    w.close()


def test_econ_tab_empty_plan_and_english(app):
    w = _win("en")
    w.action_new()
    w.tabs.setCurrentWidget(w.econ_tab)
    assert w.econ_tab.combo.count() == 0 and w.econ_tab.msg.text()
    w.action_demo()
    w.tabs.setCurrentWidget(w.econ_tab)
    assert w.econ_tab.combo.count() > 0 and "NPV" in w.econ_tab.c_npv.title.text()
    w.close()


def test_indicators_tab_shows_inputs_and_exports(app, tmp_path):
    w = _win("fa")
    w.action_demo()
    w.tabs.setCurrentWidget(w.ind_tab)
    it = w.ind_tab
    from waterprofiler import indicators as K
    def txt(x):
        return x.text().replace("\u200e", "").strip()

    assert txt(it.heads[0].value) != "—"
    assert sum(tb.rowCount() for tb in it.tables.values()) == len(K.compute(w.plant).items)
    assert it.sub_tb.columnCount() == len(w.plant.subsystems) + 1
    assert it.prod_tb.rowCount() == len(w.plant.subsystems)
    # entering a missing input fills the indicators that need it, and writes into the project
    r_permit = [i.id for i in K.compute(w.plant).by_group("supply")].index("sup_permit_use")
    tb = it.tables["supply"]
    assert txt(tb.item(r_permit, 1)) == "—"
    w.tabs.setCurrentWidget(w.industrial_tab)                 # fixed (structural) inputs live on the complex page
    w.site_tab.struct.spins["permit_m3"].setValue(100000.0)
    assert w.plant.profile.permit_m3 == 100000.0
    assert "permit_m3" not in it.spins and "employees" in it.spins
    w.tabs.setCurrentWidget(w.ind_tab)
    assert txt(tb.item(r_permit, 1)) != "—"
    # production per subsystem
    first = w.plant.subsystems[0].name
    it.prod_tb.item(0, 1).setText("50000")
    assert w.plant.profile.sub_production[first] == 50000.0
    assert txt(it.sub_tb.item(9, 1)) != "—"             # "intake per unit" row, first subsystem
    # the alternative-source flag survives the Plant page round trip
    w.tabs.setCurrentWidget(w.industrial_tab)
    w.plant_panel.sources.item(0, 3).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CheckState.Checked)
    w.collect()
    assert w.plant.sources[0].alternative is True
    w.tabs.setCurrentWidget(w.ind_tab)
    r_alt = [i.id for i in K.compute(w.plant).by_group("supply")].index("sup_alt_share")
    assert float(txt(w.ind_tab.tables["supply"].item(r_alt, 1)).replace(",", "")) > 0
    w.export_xlsx_to(str(tmp_path / "i.xlsx"))
    from openpyxl import load_workbook
    assert w.t("sheet_ind") in load_workbook(tmp_path / "i.xlsx").sheetnames
    w.export_pdf_to(str(tmp_path / "i.pdf"))
    assert (tmp_path / "i.pdf").stat().st_size > 2000
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
    w.close()


def test_indicators_tab_english_and_blank(app):
    w = _win("en")
    w.action_new()
    w.tabs.setCurrentWidget(w.ind_tab)
    assert w.ind_tab.heads[0].title.text() == "Water intensity"
    w.action_demo()
    w.tabs.setCurrentWidget(w.ind_tab)
    assert "Supply" in [c.text() for c in w.ind_tab.findChildren(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)]
    w.close()


def test_time_tab_presets_defaults_and_entry(app):
    w = _win("en")
    w.action_new()
    w.tabs.setCurrentWidget(w.ts_tab)
    tt = w.ts_tab
    tt.set_checked([])
    assert tt.checked_keys() == []
    w.action_demo()
    w.tabs.setCurrentWidget(w.ts_tab)
    first = w.plant.subsystems[0].name
    tt.set_checked([])
    tt._add_preset("loss")
    assert tt.checked_keys() == ["loss:measured"]
    tt._add_preset("prod")
    assert f"sub:{first}:production" in tt.checked_keys() and any(k.startswith("production:") for k in tt.checked_keys())
    tt._add_preset("water")
    assert f"sub:{first}:intake" in tt.checked_keys() and any(k.startswith("source:") for k in tt.checked_keys())
    tt._add_preset("price")
    assert any(k.startswith("price:source:") for k in tt.checked_keys())
    assert "energy:el" not in tt.checked_keys() or w.plant.series.get("energy:el")
    # entering a monthly loss value writes into the plant
    tt.set_checked(["loss:measured"])
    before = list(w.plant.series["loss:measured"])
    assert tt.set_cell(0, 2, "123", ask=False)
    assert w.plant.series["loss:measured"][0].value == 123.0 and len(w.plant.series["loss:measured"]) >= len(before)
    # the indicators page shows the new time indicators
    w.tabs.setCurrentWidget(w.ind_tab)
    from waterprofiler import indicators as K
    assert K.compute(w.plant).get("ts_loss_measured").value is not None
    w.close()


def test_time_tab_excel_template_buttons(app, tmp_path):
    w = _win("fa")
    w.action_demo()
    w.tabs.setCurrentWidget(w.ts_tab)
    tt = w.ts_tab
    assert tt.cols and tt.slices
    f = str(tmp_path / "tpl.xlsx")
    assert tt.export_xlsx(f) == len(tt.slices)
    before = len(w.plant.series)
    assert tt.import_xlsx(f) > 0                       # the prefilled values come back unchanged
    assert len(w.plant.series) == before
    assert "Excel" in tt.msg.text() or tt.msg.text()
    w.close()


def test_flow_page_time_view_and_balance(app):
    from waterprofiler.sample import demo_with_history
    w = _win("fa")
    w._set_plant(demo_with_history("fa"), None)
    w.tabs.setCurrentWidget(w.flow_tab)
    app.processEvents()
    ft = w.flow_tab
    tb = ft.timebar
    assert w.balance_tab is ft.balance and w.balance_tab.table.rowCount() == 5
    assert "balance" not in [p[0] for p in w._pages]
    import copy
    snap = copy.deepcopy(w.plant.to_dict())
    base_intake = ft.diagram.graph.nodes and sum(n.volume for n in ft.diagram.graph.nodes if n.kind == "source")
    assert not ft.diagram.read_only and tb.period() is None

    tb.mode.setCurrentIndex(1)
    app.processEvents()
    assert tb.period() is not None and len(tb.slices) >= 12
    assert ft.diagram.read_only and not ft.table.isEnabled() and not ft.undo_btn.isEnabled()
    first = sum(n.volume for n in ft.diagram.graph.nodes if n.kind == "source")
    tb.slider.setValue(6)
    app.processEvents()
    assert tb.index == 6 and ft.balance.table.rowCount() == 5
    assert sum(n.volume for n in ft.diagram.graph.nodes if n.kind == "source") != first
    assert ft.diagram.graph.ref_total > 0
    assert w.plant.to_dict() == snap       # the base model is never touched

    tb.next_btn.click()
    assert tb.index == 7
    tb.speed.setCurrentIndex(2)
    tb.toggle_play()
    assert tb.is_playing()
    tb._tick()
    assert tb.index == 8
    tb.toggle_play()
    assert not tb.is_playing()
    tb.slider.setValue(len(tb.slices) - 2)
    tb.loop.setChecked(False)
    tb.play()
    assert tb.is_playing()
    tb._tick()
    assert tb.index == len(tb.slices) - 1 and not tb.is_playing()

    tb.basis.setCurrentIndex(1)
    app.processEvents()
    assert ft.balance.unit == w.t("ft_unit_annual")
    tb.mode.setCurrentIndex(0)
    app.processEvents()
    assert not ft.diagram.read_only and ft.table.isEnabled()
    assert sum(n.volume for n in ft.diagram.graph.nodes if n.kind == "source") == pytest.approx(base_intake)
    w.close()


def test_flow_page_without_series_stays_in_base(app):
    from waterprofiler.sample import demo_plant
    w = _win("en")
    w._set_plant(demo_plant("en"), None)
    w.tabs.setCurrentWidget(w.flow_tab)
    tb = w.flow_tab.timebar
    assert not tb.has_data() and not tb.mode.isEnabled() and tb.period() is None
    tb.play()
    assert not tb.is_playing()
    w.close()


def test_industrial_page_merges_plant_and_site(app):
    from waterprofiler.sample import demo_with_history
    w = _win("fa")
    w._set_plant(demo_with_history("fa"), None)
    ids = [p[0] for p in w._pages]
    assert ids[0] == "plant" and "site" not in ids
    assert w.t(w._pages[0][1]) == "مجتمع صنعتی"
    w.tabs.setCurrentWidget(w.industrial_tab)
    it = w.industrial_tab
    assert it.sections.count() == 2 and w.plant_panel is it.plant_panel and w.site_tab is it.site_tab
    w.plant_panel.name.setText("مجتمع آزمون")
    it.show_site()
    app.processEvents()
    w.collect()
    assert w.plant.name == "مجتمع آزمون" and w.plant.site.name == "مجتمع آزمون"
    assert w.site_tab.areas.rowCount() >= 1 and w.site_tab.meters.rowCount() >= 0
    it.show_plant()
    assert w.plant_panel.sources.rowCount() == len(w.plant.sources)
    w.close()


def test_series_driven_fields_are_locked_everywhere(app):
    from PySide6.QtCore import Qt
    from waterprofiler.sample import demo_with_history
    w = _win("fa")
    w._set_plant(demo_with_history("fa"), None)
    w.collect()
    pp = w.plant_panel
    assert not pp.production.isEnabled()                            # total production = sum of the products: display only
    assert pp.elec.isEnabled() and pp.heat_eff.isEnabled()          # no series for these: still typed here
    assert not (pp.sources.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable)
    assert pp.sources.item(0, 3).flags() & Qt.ItemFlag.ItemIsUserCheckable
    w.tabs.setCurrentWidget(w.ind_tab)
    assert not w.ind_tab.spins["employees"].isEnabled() and w.ind_tab.spins["revenue"].isEnabled()
    first = w.plant.subsystems[0].name
    assert not (w.ind_tab.prod_tb.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable) or f"subprod:{first}" not in __import__(
        "waterprofiler.timeseries", fromlist=["x"]).driven(w.plant)
    w.tabs.setCurrentWidget(w.subs_page)
    names = [s.name for s in w.plant.subsystems]
    w.sub_list.setCurrentRow(names.index("فرایند") if "فرایند" in names else 0)
    ed = w.sub_editor
    if "intake" in ed._locked:
        assert not (ed.intake.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable)
    # the base model carries the series value, and the page shows it
    assert abs(pp.production.value() - w.plant.production_per_year) < 0.01
    # no series any more: everything is editable again
    w.plant.series.clear()
    w.tabs.setCurrentWidget(w.industrial_tab)
    assert not pp.production.isEnabled() and pp.sources.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable
    w.close()


def test_trend_views_under_entry_areas_and_in_indicators(app):
    from waterprofiler.sample import demo_with_history
    w = _win("fa")
    w._set_plant(demo_with_history("fa"), None)
    w.collect()
    pk = w.plant_panel.peek_src
    assert pk.isVisibleTo(w.plant_panel) or pk.var.count() > 0
    pk.btn.setChecked(True)
    assert pk.tb.rowCount() > 12 and pk.chart.mode == "bar"
    pk.mode.setCurrentIndex(pk.mode.findData("line"))
    assert pk.chart.mode == "line"
    assert w.plant_panel.peek_prod.var.findData("total:production") >= 0       # total production: result only
    w.tabs.setCurrentWidget(w.ind_tab)
    tr = w.ind_tab.trend
    assert tr.var.count() >= 3 and tr.tb.rowCount() > 12 and tr.var.findData("per_unit") >= 0
    tr.mode.setCurrentIndex(tr.mode.findData("line"))
    assert tr.chart.mode == "line"
    w.tabs.setCurrentWidget(w.ts_tab)
    ct = w.ts_tab
    ct.set_checked([f"production:{p.name}" for p in w.plant.site.products])
    assert ct.chart_var.findData("total:production") >= 0
    w.close()


def test_estimator_asks_staff_once(app):
    from waterprofiler.gui.dialogs import EstimateDialog
    w = _win("en")
    d = EstimateDialog(w.t, "sanitary", {"employees": 10.0}, ["A"], ["B"], "A", "B", None, locked={"employees": 250.0, "days": 300.0})
    assert d.fields["employees"].value() == 250.0 and not d.fields["employees"].isEnabled()
    assert d.fields["lpd"].isEnabled()
    w.close()


def test_unit_equipment_tree_in_the_window(app, tmp_path):
    from waterprofiler import timeseries as TS
    from waterprofiler.sample import demo_with_history
    w = _win("en")
    w.plant = demo_with_history("en")
    w._load_all(0)
    n0 = len(w.plant.subsystems)
    intake0 = sum(s.total_intake for s in w.plant.leaves())
    w.sub_list.setCurrentRow(0)
    unit = w.plant.subsystems[0].name
    w._add_equipment()                                    # first equipment: the unit's own data moves to a holder
    w._add_equipment()
    assert len(w.plant.subsystems) == n0 + 3
    assert w.plant.has_children(unit)
    assert w.sub_list.count() == n0 + 3
    assert w.sub_list.item(1).text().strip().startswith("↳")
    assert sum(s.total_intake for s in w.plant.leaves()) == pytest.approx(intake0)
    # the unit's editor is read-only; equipment's is not
    w.sub_list.setCurrentRow(0)
    assert not w.sub_editor.intake.isEnabled() and w.sub_editor.derived_note.isVisibleTo(w.sub_editor)
    w.sub_list.setCurrentRow(2)
    assert w.sub_editor.intake.isEnabled() and not w.sub_editor.derived_note.isVisibleTo(w.sub_editor)
    # rename the equipment through the editor: links, series and parent follow
    old = w.plant.subsystems[2].name
    w.sub_editor.name.setText("Line A")
    w.collect()
    assert w.plant.node("Line A") is not None and w.plant.node(old) is None
    for i in range(w.tabs.count()):                       # every page opens on a tree
        w.tabs.setCurrentIndex(i)
        app.processEvents()
    assert w.balance_tab.table.rowCount() == len(w.plant.ordered())
    w.export_xlsx_to(str(tmp_path / "r.xlsx"))
    w.export_pdf_to(str(tmp_path / "r.pdf"))
    # removing the unit asks and removes its equipment
    w.sub_list.setCurrentRow(0)
    w._remove_subsystem()
    assert w.plant.node(unit) is None and not [s for s in w.plant.subsystems if s.parent == unit]
    w.close()


def test_storage_change_and_uncertainty_in_the_window(app, tmp_path):
    from waterprofiler.sample import demo_with_history
    w = _win("en")
    w.plant = demo_with_history("en")
    w._load_all(0)
    w.sub_list.setCurrentRow(0)
    assert w.sub_editor.storage.minimum() < 0
    w.sub_editor.storage.setValue(-250.0)
    w.collect()
    assert w.plant.subsystems[0].storage_change == pytest.approx(-250.0)
    app.processEvents()
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        app.processEvents()
    t = w.balance_tab.table
    assert t.columnCount() == 9 and t.rowCount() == len(w.plant.ordered())
    assert t.item(0, 6) is not None and t.item(0, 6).text() != ""
    w.ind_tab.inputs.load(w.plant)
    w.ind_tab.inputs.spins["unmetered_unc_pct"].setValue(25.0)
    assert w.plant.profile.unmetered_unc_pct == pytest.approx(25.0)
    w.export_xlsx_to(str(tmp_path / "r.xlsx"))
    w.export_pdf_to(str(tmp_path / "r.pdf"))
    w.close()


def test_water_by_product_page(app):
    from waterprofiler.sample import demo_with_history
    w = _win("en")
    w.plant = demo_with_history("en")
    w._load_all(0)
    w.tabs.setCurrentWidget(w.product_tab)
    app.processEvents()
    tab = w.product_tab
    assert tab.matrix.rowCount() == len(w.plant.ordered())
    assert tab.result.rowCount() >= len(w.plant.site.products)
    p0 = w.plant.site.products[0].name
    r = next(i for i, s in enumerate(tab._nodes) if s.name not in w.plant.allocation and not w.plant.has_children(s.name))
    tab.matrix.item(r, 1).setText("100")                  # allocate a general node wholly to product 1
    assert w.plant.allocation[tab._nodes[r].name] == {p0: 1.0}
    tab.matrix.item(r, 2).setText("50")                   # 150 % is refused, the row keeps its old values
    assert w.plant.allocation[tab._nodes[r].name] == {p0: 1.0}
    assert tab.msg.text()
