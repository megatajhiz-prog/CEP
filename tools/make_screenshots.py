"""Render documentation screenshots of the real application (headless Qt).

    python tools/make_screenshots.py docs/img
"""

from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from scenarios import leaky_plant  # noqa: E402
from waterprofiler.app import _load_fonts  # noqa: E402


def main(out: str) -> int:
    os.makedirs(out, exist_ok=True)
    for name in ("question", "warning", "information", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    app = QApplication([])
    _load_fonts(app)
    from waterprofiler.gui.dialogs import EstimateDialog
    from waterprofiler.gui.main_window import MainWindow
    from waterprofiler.sample import demo_plant

    win = MainWindow("fa")
    win.resize(1320, 880)
    win.show()
    app.processEvents()
    done, failed = [], []

    def settle():
        for _ in range(3):
            app.processEvents()

    def shot(widget, name):
        settle()
        path = os.path.join(out, name + ".png")
        ok = widget.grab().save(path)
        (done if ok else failed).append(name)

    def step(fn):
        try:
            fn()
        except Exception:  # noqa: BLE001 - keep going, report at the end
            failed.append(fn.__name__)
            traceback.print_exc()

    def blank():
        win.plant_panel.name.setFocus()
        shot(win, "00_start_blank")

    def plant_tab():
        win._set_plant(demo_plant("fa"), None)
        win.tabs.setCurrentIndex(0)
        shot(win, "01_plant")
        shot(win.plant_panel, "01_plant_panel")

    def file_menu():
        menu = win.menuBar().actions()[0].menu()
        menu.popup(win.mapToGlobal(QPoint(40, 30)))
        settle()
        shot(menu, "02_file_menu")
        menu.hide()

    def lang_menu():
        menu = win.menuBar().actions()[1].menu()
        menu.popup(win.mapToGlobal(QPoint(120, 30)))
        settle()
        shot(menu, "02_language_menu")
        menu.hide()

    def subsystems():
        win.tabs.setCurrentIndex(1)
        win.sub_list.setCurrentRow(1)
        shot(win, "03_subsystems")
        shot(win.sub_editor.widget(), "03_subsystem_editor_full")

    def estimate_dialog():
        s = win.plant.subsystems[1]
        srcs, outs, _t = win._catalog()
        dlg = EstimateDialog(win.t, s.kind, s.params, srcs, outs, next(iter(s.intake), None),
                             next(iter(s.discharge), None), win)
        dlg.show()
        shot(dlg, "04_estimate_dialog")
        dlg.close()

    def balance_ok():
        win.tabs.setCurrentIndex(2)
        shot(win, "05_balance")
        shot(win.balance_tab.widget(), "05_balance_full")

    def cost():
        win.tabs.setCurrentIndex(3)
        shot(win, "06_cost")
        shot(win.cost_tab.widget(), "06_cost_full")

    def savings():
        win.tabs.setCurrentIndex(4)
        st = win.savings_tab
        st.ct_new.setValue(6.0)
        st.ct_capex.setValue(5000.0)
        st._calc_ct()
        st.bo_coc.setValue(20.0)
        st.bo_cond.setValue(70.0)
        st.bo_capex.setValue(12000.0)
        st._calc_boiler()
        st.lk_rate.setValue(2.0)
        st.lk_hours.setValue(8000)
        st.lk_frac.setValue(1.0)
        st.lk_capex.setValue(3000.0)
        st._calc_leak()
        shot(win, "07_savings")
        shot(st.widget(), "07_savings_full")

    def leak_balance():
        win._set_plant(leaky_plant("fa"), None)
        win.tabs.setCurrentIndex(2)
        win._tab_changed(2)
        shot(win, "08_balance_leak")
        shot(win.balance_tab.widget(), "08_balance_leak_full")

    def reconcile():
        win.tabs.setCurrentIndex(5)
        win._tab_changed(5)
        win.reconcile_tab._run()
        shot(win, "09_reconcile")
        shot(win.reconcile_tab.widget(), "09_reconcile_full")

    def english():
        win.set_language("en")
        win._set_plant(demo_plant("en"), None)
        win.tabs.setCurrentIndex(3)
        win._tab_changed(3)
        shot(win, "10_english_cost")

    for fn in (blank, plant_tab, file_menu, lang_menu, subsystems, estimate_dialog, balance_ok, cost,
               savings, leak_balance, reconcile, english):
        step(fn)

    print("saved:", ", ".join(done))
    if failed:
        print("FAILED:", ", ".join(failed))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "docs/img"))
