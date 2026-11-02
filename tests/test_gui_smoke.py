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
    from waterprofiler.sample import demo_plant
    w = _win("en")
    w.action_demo()
    before = demo_plant().to_dict()
    w.tabs.setCurrentIndex(1)
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
    w.tabs.setCurrentIndex(4)
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
    w.nav[3].click()
    assert w.tabs.currentIndex() == 3
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
