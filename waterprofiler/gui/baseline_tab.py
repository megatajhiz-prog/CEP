"""Consumption baseline (regression of monthly water intake) and savings measured against it (page «خط مبنا»)."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QSpinBox

from .. import baseline as BL
from ..i18n import Translator
from ..model import Plant
from .tabs import StatCard, _Scroll, _fmt, _message_label, _warn_label, make_table, put, stat_row
from .theme import COL
from .trend import TsChart
from .widgets import card


class BaselineTab(_Scroll):
    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Plant | None = None
        self.msg = _message_label()
        self.lay.addWidget(self.msg)
        self.n_report = QSpinBox()
        self.n_report.setRange(0, 60)
        self.n_report.valueChanged.connect(self._redraw)
        row = QHBoxLayout()
        lab = QLabel(t("bl_report_months"))
        lab.setObjectName("cardnote")
        row.addWidget(lab)
        row.addWidget(self.n_report)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.c_r2 = StatCard("R²", COL["blue"])
        self.c_cv = StatCard("CV(RMSE)", COL["orange"])
        self.c_sav = StatCard(t("bl_saving") + " (m³)", COL["green"])
        self.c_pct = StatCard(t("bl_saving_pct"), COL["green"])
        self.lay.addLayout(stat_row(self.c_r2, self.c_cv, self.c_sav, self.c_pct))
        self.eq = QLabel()
        self.eq.setWordWrap(True)
        self.eq.setObjectName("cardnote")
        self.coef = make_table([t("bl_term"), t("bl_coef"), t("bl_se"), "t", "p"])
        self.coef.setMaximumHeight(190)
        box = card(t("bl_model"), self.coef, note=t("bl_model_note"))
        box.layout().addWidget(self.eq)
        self.lay.addWidget(box)
        self.chart = TsChart(230)
        self.lay.addWidget(card(t("bl_cusum"), self.chart, note=t("bl_cusum_note")))
        self.table = make_table([t("ts_month"), t("bl_actual"), t("bl_expected"), t("bl_saving"), t("bl_cusum_col"), t("bl_phase")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(300)
        self.lay.addWidget(card(t("bl_months"), self.table))
        self.warn = _warn_label()
        self.lay.addWidget(self.warn)
        self.lay.addStretch(1)

    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        self._redraw()

    def _redraw(self, *_a) -> None:
        t, plant = self.t, self.plant
        if plant is None:
            return
        res = BL.evaluate(plant, self.n_report.value())
        m = res.model
        warns = [t(w) for w in res.warnings]
        if m is None:
            self.msg.setText(t("bl_none"))
            for c in (self.c_r2, self.c_cv, self.c_sav, self.c_pct):
                c.set("—")
            self.coef.setRowCount(0)
            self.table.setRowCount(0)
            self.chart.set_data("", [], [], "m³")
            self.eq.setText("")
        else:
            self.msg.setText("")
            lang = t.lang
            self.c_r2.set(f"{m.r2:.3f}" if not m.intercept_only else "—")
            self.c_cv.set(f"{m.cv_rmse:.1f}%")
            reporting = res.n_report > 0
            self.c_sav.set((("+" if res.saving_total >= 0 else "") + _fmt(res.saving_total) +
                            (f" ± {_fmt(res.saving_sigma)}" if reporting else "")) if reporting else "—")
            self.c_pct.set(f"{res.saving_pct:+.1f}%" if reporting else "—")
            names = [t("bl_intercept")] + [d.label(lang) for d in m.drivers]
            self.coef.setRowCount(len(names))
            for r, nme in enumerate(names):
                put(self.coef, r, 0, nme)
                put(self.coef, r, 1, f"{m.coef[r]:,.4g}", True)
                put(self.coef, r, 2, f"{m.se[r]:,.3g}", True)
                put(self.coef, r, 3, f"{m.t[r]:.2f}", True)
                put(self.coef, r, 4, f"{m.p[r]:.4f}", True)
            terms = " + ".join(f"{c:,.4g}×[{d.label(lang)}]" for c, d in zip(m.coef[1:], m.drivers))
            self.eq.setText(f"W = {m.coef[0]:,.4g}" + (f" + {terms}" if terms else "") +
                            f"   ({t('bl_n')}: {m.n},  adj. R² = {m.adj_r2:.3f})")
            self.table.setRowCount(len(res.months))
            for r, x in enumerate(res.months):
                put(self.table, r, 0, x.label)
                put(self.table, r, 1, _fmt(x.actual), True)
                put(self.table, r, 2, _fmt(x.expected), True)
                put(self.table, r, 3, _fmt(x.saving), True)
                put(self.table, r, 4, _fmt(x.cusum), True)
                put(self.table, r, 5, t("bl_report") if x.in_report else t("bl_train"))
            self.chart.set_data(t("bl_cusum"), [x.label for x in res.months], [x.cusum for x in res.months], "m³")
            if reporting:
                warns.append(t("bl_sig_yes" if res.significant else "bl_sig_no"))
        self.warn.setText("\n".join(warns))
        self.warn.setVisible(bool(warns))
