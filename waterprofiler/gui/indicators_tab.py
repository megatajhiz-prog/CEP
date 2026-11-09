"""Indicators page: ~80 supply / use / wastewater / cost / quality indicators with formulas and inputs."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import indicators as K
from .. import timeseries as TS
from ..indicator_text import (
    GROUP_TITLE, PROFILE_GROUPS, PROFILE_LABEL, STRUCT_FIELDS, SUB_COLS, TEXT, format_value, unit_label,
)
from ..i18n import Translator
from ..model import Plant
from .tabs import _Scroll, _message_label, make_table, put, stat_row
from .theme import COL
from .profile_inputs import ProfileInputs
from .trend import IndicatorTrend, TrendPeek, with_data
from .widgets import StatCard, card, dspin

MUTED = QColor("#8A94A6")
HEADLINE = ("use_per_unit", "use_reuse_factor", "use_recirc_ratio", "use_consumption", "cost_per_m3", "use_loss_fraction")
HEAD_ACCENT = (COL["blue"], COL["green"], COL["navy"], COL["orange"], COL["navy"], COL["red"])


def _fit(tb: QTableWidget, min_rows: int = 0) -> None:
    """Make the table exactly as tall as its content so the page scrolls, not the table."""
    tb.resizeRowsToContents()
    h = tb.horizontalHeader().height() + 2 * tb.frameWidth() + 6
    for r in range(tb.rowCount()):
        h += tb.rowHeight(r)
    tb.setFixedHeight(max(h, 60))


class IndicatorsTab(_Scroll):
    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False
        self.msg = _message_label()
        self.lay.addWidget(self.msg)

        # headline tiles
        self.heads: List[StatCard] = []
        for i in range(0, 6, 3):
            row = []
            for j in range(3):
                k = i + j
                sc = StatCard(TEXT[HEADLINE[k]][0 if t.lang == "fa" else 1], HEAD_ACCENT[k])
                row.append(sc)
                self.heads.append(sc)
            self.lay.addLayout(stat_row(*row))
        self.c_comp = StatCard(t("in_computed"), COL["green"])
        self.c_inputs = StatCard(t("in_complete"), COL["orange"])
        self.lay.addLayout(stat_row(self.c_comp, self.c_inputs))

        # supplementary inputs (those that vary with time, and the targets); structural ones are on the complex page
        self.inputs = ProfileInputs(t, PROFILE_GROUPS)
        self.spins = self.inputs.spins
        self.inputs.changed.connect(self._recalc)
        self.lay.addWidget(card(t("in_inputs"), self.inputs, note=t("in_inputs_note")))

        self.prod_tb = QTableWidget(0, 2)
        self.prod_tb.setHorizontalHeaderLabels([t("subsystem"), t("in_sub_prod")])
        self.prod_tb.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.prod_tb.verticalHeader().setVisible(False)
        self.prod_tb.verticalHeader().setDefaultSectionSize(36)
        self.prod_tb.setShowGrid(False)
        self.prod_tb.setAlternatingRowColors(True)
        self.prod_tb.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.AnyKeyPressed
                                     | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.prod_tb.itemChanged.connect(self._prod_changed)
        self.peek_sub = TrendPeek(t, lambda p: with_data(p, [f"sub:{x.name}:production" for x in p.subsystems]))
        self.lay.addWidget(card(t("in_sub_prod"), self.prod_tb, self.peek_sub, note=t("in_sub_prod_note")))
        self.trend = IndicatorTrend(t)
        self.lay.addWidget(card(t("in_trend"), self.trend, note=t("in_trend_note")))

        fa = t.lang == "fa"
        # one table per group
        self.tables: Dict[str, QTableWidget] = {}
        for g in K.GROUPS:
            tb = make_table([t("in_col_name"), t("in_col_value"), t("in_col_unit"), t("in_col_formula"), t("in_col_note")])
            hh = tb.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            tb.setWordWrap(True)
            tb.setTextElideMode(Qt.TextElideMode.ElideNone)
            tb.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            tb.verticalHeader().setDefaultSectionSize(34)
            self.tables[g] = tb
            title = GROUP_TITLE[g][0 if fa else 1]
            self.lay.addWidget(card(title, tb))

        self.sub_tb = make_table([t("subsystem")])
        self.sub_tb.setWordWrap(True)
        self.sub_tb.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.lay.addWidget(card(t("in_sub_title"), self.sub_tb, note=t("in_sub_note")))

        meth = QLabel(f"<b>{t('in_method')}</b><br>{t('in_method_text')}")
        meth.setWordWrap(True)
        meth.setTextFormat(Qt.TextFormat.RichText)
        meth.setObjectName("cardnote")
        self.lay.addWidget(card("", meth))
        self.lay.addStretch(1)

    # ------------------------------------------------------------------ data
    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        self._loading = True
        pf = plant.profile
        self.inputs.load(plant)
        self.peek_sub.set_plant(plant)
        self.trend.set_plant(plant)
        drv = TS.driven(plant)
        self.prod_tb.blockSignals(True)
        self.prod_tb.setRowCount(len(plant.subsystems))
        for r, s in enumerate(plant.subsystems):
            name_it = QTableWidgetItem(s.name)
            name_it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.prod_tb.setItem(r, 0, name_it)
            it = QTableWidgetItem(f"{pf.sub_production.get(s.name, 0.0):g}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if f"subprod:{s.name}" in drv:                      # taken from the time series: shown, not typed
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setToolTip(self.t("ft_driven"))
            self.prod_tb.setItem(r, 1, it)
        self.prod_tb.blockSignals(False)
        _fit(self.prod_tb)
        self._loading = False
        self._recalc()

    def _prod_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self.plant is None or item.column() != 1:
            return
        name = self.prod_tb.item(item.row(), 0).text()
        try:
            v = float(item.text().replace(",", "").replace("٫", "."))
        except ValueError:
            v = 0.0
        if v > 0:
            self.plant.profile.sub_production[name] = v
        else:
            self.plant.profile.sub_production.pop(name, None)
        self._recalc()

    def _recalc(self) -> None:
        if self.plant is None:
            return
        t, plant = self.t, self.plant
        fa = t.lang == "fa"
        try:
            res = K.compute(plant)
        except Exception as e:      # noqa: BLE001 - show the problem, keep the page alive
            self.msg.setText(str(e))
            return
        self.msg.setText("")
        cur, unit = plant.currency, plant.production_unit

        for card_, key in zip(self.heads, HEADLINE):
            ind = res.get(key)
            card_.set(format_value(ind.value, ind.unit), unit_label(ind.unit, t.lang, cur, unit))
        n_ok = sum(1 for i in res.items if i.value is not None)
        self.c_comp.set(f"{res.computable:.0f}%", t("in_computed_hint", n=n_ok, m=len(res.items)))
        done = round(res.completeness * len(K.PROFILE_FIELDS) / 100)
        self.c_inputs.set(f"{res.completeness:.0f}%", t("in_complete_hint", n=done, m=len(K.PROFILE_FIELDS)))

        for g, tb in self.tables.items():
            items = res.by_group(g)
            tb.setRowCount(len(items))
            for r, ind in enumerate(items):
                tx = TEXT[ind.id]
                name = tx[0] if fa else tx[1]
                if ind.approx:
                    name += f"  ({t('in_approx')})"
                missing = ind.value is None
                put(tb, r, 0, name, bold=not missing)
                put(tb, r, 1, format_value(ind.value, ind.unit), True, bold=not missing)
                put(tb, r, 2, unit_label(ind.unit, t.lang, cur, unit))
                put(tb, r, 3, tx[2], True)
                if ind.reason == "inputs":
                    names = [PROFILE_LABEL[n][0 if fa else 1] + (f" ({t('tab_industrial')})" if n in STRUCT_FIELDS else "")
                             for n in ind.needs]
                    note = t("in_needs", x=("، " if fa else ", ").join(names))
                elif ind.reason == "data":
                    note = t("in_nodata")
                else:
                    note = tx[3] if fa else tx[4]
                put(tb, r, 4, note)
                if missing:
                    for c in range(5):
                        it = tb.item(r, c)
                        if it is not None:
                            it.setForeground(MUTED)
            _fit(tb)

        # metrics down the side, one column per subsystem (readable with any number of subsystems)
        self.sub_tb.setColumnCount(1 + len(res.subsystems))
        self.sub_tb.setHorizontalHeaderLabels([t("in_col_name")] + [r.name for r in res.subsystems])
        self.sub_tb.setRowCount(len(SUB_COLS))
        hh = self.sub_tb.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for r, (key, f_, e_, u) in enumerate(SUB_COLS):
            put(self.sub_tb, r, 0, (f_ if fa else e_) + "  (" + unit_label(u, t.lang, cur, unit) + ")" if unit_label(u, t.lang, cur, unit)
                else (f_ if fa else e_), bold=True)
            for c, srow in enumerate(res.subsystems, start=1):
                put(self.sub_tb, r, c, format_value(srow.values.get(key), u), True)
        _fit(self.sub_tb)

    def resizeEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(ev)
        for tb in self.tables.values():
            _fit(tb)
