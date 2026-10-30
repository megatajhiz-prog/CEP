"""Main application window."""

from __future__ import annotations

import copy
import os
from typing import Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence, QPageSize, QPdfWriter, QTextDocument, QTextOption
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..analysis import Analysis, analyse
from ..estimate_apply import apply_estimate
from ..estimators import InputError
from ..export_xlsx import export_xlsx
from ..i18n import Translator
from ..model import Plant, Subsystem
from ..report_html import build_report_html
from ..sample import demo_plant
from ..storage import EXTENSION, ProjectFileError, load_project, save_project
from .dialogs import EstimateDialog
from .editor import PlantPanel, SubsystemEditor
from .tabs import BalanceTab, CostTab, ReconcileTab, SavingsTab

ORG = "WaterProfiler"
APP = "WaterProfiler"


def new_plant(t: Translator) -> Plant:
    return Plant(name=t("app_title"), currency="IRR" if t.lang == "fa" else "USD")


class MainWindow(QMainWindow):
    def __init__(self, lang: str = "fa"):
        super().__init__()
        self.t = Translator(lang)
        self.plant = new_plant(self.t)
        self.path: Optional[str] = None
        self._snapshot = copy.deepcopy(self.plant.to_dict())
        self._cur = -1
        self.resize(1180, 760)
        self._build()
        self._load_all()

    # ============================================================ construction
    def _build(self) -> None:
        t = self.t
        QApplication.instance().setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if t.rtl else Qt.LayoutDirection.LeftToRight)
        self.setWindowTitle(t("app_title"))
        self._build_menu()

        self.tabs = QTabWidget()
        self.plant_panel = PlantPanel(t)
        self.sub_editor = SubsystemEditor(t)
        self.sub_editor.estimate_requested.connect(self._estimate)
        self.sub_list = QListWidget()
        self.balance_tab = BalanceTab(t)
        self.cost_tab = CostTab(t)
        self.savings_tab = SavingsTab(t)
        self.reconcile_tab = ReconcileTab(t)
        self.reconcile_tab.applied.connect(self._apply_reconciled)

        subs = QWidget()
        sl = QHBoxLayout(subs)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(self.sub_list, 1)
        add, rem = QPushButton(t("add")), QPushButton(t("remove"))
        add.clicked.connect(self._add_subsystem)
        rem.clicked.connect(self._remove_subsystem)
        ll.addWidget(add)
        ll.addWidget(rem)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.sub_editor)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)
        sl.addWidget(split)

        self.tabs.addTab(self.plant_panel, t("tab_plant"))
        self.tabs.addTab(subs, t("tab_subsystems"))
        self.tabs.addTab(self.balance_tab, t("tab_balance"))
        self.tabs.addTab(self.cost_tab, t("tab_cost"))
        self.tabs.addTab(self.savings_tab, t("tab_savings"))
        self.tabs.addTab(self.reconcile_tab, t("tab_reconcile"))
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.sub_list.currentRowChanged.connect(self._row_changed)

    def _build_menu(self) -> None:
        t = self.t
        mb = self.menuBar()
        mb.clear()
        m = mb.addMenu(t("file"))

        def act(menu, key, fn, shortcut=None):
            a = QAction(t(key), self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(lambda _=False: fn())
            menu.addAction(a)
            return a

        act(m, "new", self.action_new, QKeySequence.StandardKey.New)
        act(m, "open", self.action_open, QKeySequence.StandardKey.Open)
        act(m, "save", self.action_save, QKeySequence.StandardKey.Save)
        act(m, "save_as", self.action_save_as, QKeySequence.StandardKey.SaveAs)
        m.addSeparator()
        act(m, "load_demo", self.action_demo)
        m.addSeparator()
        act(m, "export_xlsx", self.action_export_xlsx)
        act(m, "export_pdf", self.action_export_pdf)
        m.addSeparator()
        act(m, "exit", self.close)

        lm = mb.addMenu(t("language"))
        act(lm, "lang_fa", lambda: self.set_language("fa"))
        act(lm, "lang_en", lambda: self.set_language("en"))
        hm = mb.addMenu(t("help"))
        act(hm, "about", self.action_about)

    # ===================================================== model <-> UI sync
    def _catalog(self):
        return ([s.name for s in self.plant.sources], [o.name for o in self.plant.outlets],
                [x.name for x in self.plant.treatments])

    def collect(self) -> Plant:
        """Pull every editor's content into self.plant."""
        self.plant_panel.store(self.plant)
        if 0 <= self._cur < len(self.plant.subsystems):
            self.sub_editor.store(self.plant.subsystems[self._cur])
            item = self.sub_list.item(self._cur)
            if item is not None:
                item.setText(self.plant.subsystems[self._cur].name)
        return self.plant

    def _refresh_sub_list(self, select: int) -> None:
        self.sub_list.blockSignals(True)
        self.sub_list.clear()
        for s in self.plant.subsystems:
            self.sub_list.addItem(s.name)
        self.sub_list.blockSignals(False)
        self._cur = -1
        if self.plant.subsystems:
            select = max(0, min(select, len(self.plant.subsystems) - 1))
            self.sub_list.setCurrentRow(select)      # triggers _row_changed
            if self._cur != select:
                self._row_changed(select)
        self.sub_editor.setEnabled(bool(self.plant.subsystems))

    def _load_all(self, select: int = 0) -> None:
        self.plant_panel.load(self.plant)
        self.sub_editor.set_catalog(*self._catalog())
        self._refresh_sub_list(select)

    def _row_changed(self, row: int) -> None:
        if 0 <= self._cur < len(self.plant.subsystems):
            self.sub_editor.store(self.plant.subsystems[self._cur])
            item = self.sub_list.item(self._cur)
            if item is not None:
                item.setText(self.plant.subsystems[self._cur].name)
        self._cur = row
        if 0 <= row < len(self.plant.subsystems):
            self.sub_editor.load(self.plant.subsystems[row])

    def _tab_changed(self, idx: int) -> None:
        self.collect()
        w = self.tabs.widget(idx)
        if w is self.balance_tab or w is self.cost_tab:
            self._run_analysis()
        elif w is self.savings_tab:
            self.savings_tab.refresh(self.plant)
        elif w is self.reconcile_tab:
            self.reconcile_tab.refresh(self.plant)
        elif w is not self.plant_panel:
            # subsystems tab: pick up renamed sources / outlets / treatments
            self.sub_editor.set_catalog(*self._catalog())
            if 0 <= self._cur < len(self.plant.subsystems):
                self.sub_editor.load(self.plant.subsystems[self._cur])

    def _analyse(self) -> Analysis:
        return analyse(self.plant)

    def _run_analysis(self) -> Optional[Analysis]:
        t = self.t
        try:
            a = self._analyse()
        except KeyError as e:
            msg = t("missing_ref", name=str(e).strip("'\""))
            self.balance_tab.show_error(msg)
            self.cost_tab.show_error(msg)
            return None
        except Exception as e:  # noqa: BLE001 - shown to the user, never crash
            msg = f"{t('analysis_error')}: {e}"
            self.balance_tab.show_error(msg)
            self.cost_tab.show_error(msg)
            return None
        self.balance_tab.refresh(a)
        self.cost_tab.refresh(a)
        return a

    # ================================================================ actions
    def _is_dirty(self) -> bool:
        self.collect()
        return self.plant.to_dict() != self._snapshot

    def _mark_clean(self) -> None:
        self._snapshot = copy.deepcopy(self.plant.to_dict())

    def _confirm_discard(self) -> bool:
        if not self._is_dirty():
            return True
        r = QMessageBox.question(self, self.t("app_title"), self.t("unsaved"),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return r == QMessageBox.StandardButton.Yes

    def _set_plant(self, plant: Plant, path: Optional[str]) -> None:
        self.plant = plant
        self.path = path
        self._load_all()
        self._mark_clean()
        self._update_title()

    def _update_title(self) -> None:
        name = os.path.basename(self.path) if self.path else ""
        self.setWindowTitle(f"{self.t('app_title')}" + (f" — {name}" if name else ""))

    def action_new(self) -> None:
        if self._confirm_discard():
            self._set_plant(new_plant(self.t), None)

    def action_demo(self) -> None:
        if self._confirm_discard():
            self._set_plant(demo_plant(), None)
            self.statusBar().showMessage(self.t("demo_loaded"), 4000)

    def action_open(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, self.t("open"), "", self.t("file_project"))
        if not path:
            return
        try:
            plant = load_project(path)
        except ProjectFileError as e:
            QMessageBox.critical(self, self.t("error"), str(e))
            return
        self._set_plant(plant, path)

    def action_save(self) -> bool:
        if not self.path:
            return self.action_save_as()
        return self._save_to(self.path)

    def action_save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, self.t("save_as"), self.plant.name + EXTENSION,
                                              self.t("file_project"))
        if not path:
            return False
        if not path.lower().endswith(EXTENSION):
            path += EXTENSION
        return self._save_to(path)

    def _save_to(self, path: str) -> bool:
        self.collect()
        try:
            save_project(self.plant, path)
        except OSError as e:
            QMessageBox.critical(self, self.t("error"), str(e))
            return False
        self.path = path
        self._mark_clean()
        self._update_title()
        self.statusBar().showMessage(self.t("saved"), 3000)
        return True

    def _need_analysis(self) -> Optional[Analysis]:
        self.collect()
        a = self._run_analysis()
        if a is None:
            QMessageBox.warning(self, self.t("error"), self.t("analysis_error"))
        return a

    def export_xlsx_to(self, path: str) -> None:
        a = self._analyse_or_raise()
        export_xlsx(a, path, self.t.lang)

    def export_pdf_to(self, path: str) -> None:
        a = self._analyse_or_raise()
        html = build_report_html(a, self.t.lang)
        doc = QTextDocument()
        if self.t.rtl:
            opt = QTextOption()
            opt.setTextDirection(Qt.LayoutDirection.RightToLeft)
            doc.setDefaultTextOption(opt)
        doc.setHtml(html)
        w = QPdfWriter(path)
        w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        w.setResolution(120)
        doc.print_(w)

    def _analyse_or_raise(self) -> Analysis:
        self.collect()
        return self._analyse()

    def action_export_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.t("export_xlsx"), self.plant.name + ".xlsx",
                                              self.t("file_xlsx"))
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            self.export_xlsx_to(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, self.t("error"), str(e))
            return
        self.statusBar().showMessage(self.t("export_done"), 4000)

    def action_export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.t("export_pdf"), self.plant.name + ".pdf",
                                              self.t("file_pdf"))
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.export_pdf_to(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, self.t("error"), str(e))
            return
        self.statusBar().showMessage(self.t("export_done"), 4000)

    def action_about(self) -> None:
        QMessageBox.about(self, self.t("about"), self.t("about_text", v=__version__))

    # ------------------------------------------------------------ subsystems
    def _add_subsystem(self) -> None:
        self.collect()
        base = self.t("new_subsystem")
        names = {s.name for s in self.plant.subsystems}
        name, i = base, 2
        while name in names:
            name, i = f"{base} {i}", i + 1
        self.plant.subsystems.append(Subsystem(name))
        self._load_all(select=len(self.plant.subsystems) - 1)

    def _remove_subsystem(self) -> None:
        if not (0 <= self._cur < len(self.plant.subsystems)):
            return
        self.collect()
        del self.plant.subsystems[self._cur]
        self._load_all(select=max(0, self._cur - 1))

    def _estimate(self) -> None:
        t = self.t
        self.collect()
        if not (0 <= self._cur < len(self.plant.subsystems)):
            return
        s = self.plant.subsystems[self._cur]
        if s.kind not in ("process", "cooling_tower", "boiler", "sanitary", "irrigation"):
            QMessageBox.information(self, t("estimate"), t("select_kind_first"))
            return
        srcs, outs, _tr = self._catalog()
        if not srcs:
            QMessageBox.information(self, t("estimate"), t("catalog_hint"))
            return
        dlg = EstimateDialog(t, s.kind, s.params, srcs, outs,
                             next(iter(s.intake), None), next(iter(s.discharge), None), self)
        if dlg.exec():
            try:
                apply_estimate(s, s.kind, dlg.values(), dlg.selected_source(), dlg.selected_outlet())
            except (InputError, KeyError) as e:
                QMessageBox.warning(self, t("error"), str(e))
                return
            self.sub_editor.load(s)

    def _apply_reconciled(self, plant: Plant) -> None:
        self.plant = plant
        sel = self._cur
        self._load_all(select=max(0, sel))
        self.reconcile_tab.refresh(self.plant)

    # -------------------------------------------------------------- language
    def set_language(self, lang: str) -> None:
        if lang == self.t.lang:
            return
        self.collect()
        QSettings(ORG, APP).setValue("lang", lang)
        sel, tab = self._cur, self.tabs.currentIndex()
        self.t = Translator(lang)
        self._build()
        self._load_all(select=max(0, sel))
        self.tabs.setCurrentIndex(tab)
        self._update_title()

    # ----------------------------------------------------------------- close
    def closeEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        if self._confirm_discard():
            ev.accept()
        else:
            ev.ignore()
