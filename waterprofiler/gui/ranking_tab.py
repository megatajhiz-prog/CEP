"""Ranking of measures: weights and scores are entered here; the page ranks the plan and proposes the best set within a budget."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import QComboBox, QGridLayout, QHeaderView, QLabel, QTabWidget, QVBoxLayout, QWidget

from .. import measures as M
from .. import ranking as RK
from ..i18n import Translator
from ..model import Plant
from .econ_pages import LccTab, RiskTab, SensitivityTab
from .econ_tab import EconTab
from .tabs import _Scroll, _fmt, _message_label, make_table, put, stat_row
from .theme import COL
from .widgets import StatCard, card, dspin


class RankingTab(_Scroll):
    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False
        self.msg = _message_label()
        self.lay.addWidget(self.msg)

        # ---- inputs: criteria weights, method, objective, budget
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.w_spins: Dict[str, object] = {}
        for i, (c, _high) in enumerate(RK.CRITERIA):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(3)
            lab = QLabel(t("rk_c_" + c))
            lab.setObjectName("cardnote")
            lab.setWordWrap(True)
            sp = dspin(maximum=100.0, decimals=0, step=5.0)
            sp.setMinimumWidth(0)
            sp.valueChanged.connect(self._inputs_changed)
            self.w_spins[c] = sp
            bl.addWidget(lab)
            bl.addWidget(sp)
            grid.addWidget(box, i // 4, i % 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        self.lay.addWidget(card(t("rk_weights"), grid_w, note=t("rk_weights_note")))

        self.method = QComboBox()
        self.method.addItem(t("rk_m_wsm"), "wsm")
        self.method.addItem(t("rk_m_topsis"), "topsis")
        self.objective = QComboBox()
        self.objective.addItem(t("rk_o_npv"), "npv")
        self.objective.addItem(t("rk_o_saving"), "saving")
        self.budget = dspin(maximum=1e13, decimals=0, step=1000.0)
        for w in (self.method, self.objective):
            w.currentIndexChanged.connect(self._inputs_changed)
        self.budget.valueChanged.connect(self._inputs_changed)
        opt_w = QWidget()
        og = QGridLayout(opt_w)
        og.setContentsMargins(0, 0, 0, 0)
        og.setHorizontalSpacing(14)
        for k, (lab, w) in enumerate(((t("rk_method"), self.method), (t("rk_objective"), self.objective),
                                      (t("rk_budget"), self.budget))):
            l = QLabel(lab)
            l.setObjectName("cardnote")
            l.setWordWrap(True)
            og.addWidget(l, 0, k)
            og.addWidget(w, 1, k)
            og.setColumnStretch(k, 1)
        self.lay.addWidget(card(t("rk_options"), opt_w, note=t("rk_options_note")))

        # ---- inputs: scores of every measure
        self.scores = make_table([t("rk_measure"), t("rk_target"), t("rk_c_ease"), t("rk_c_reliability")])
        self.scores.setMinimumHeight(190)
        self.lay.addWidget(card(t("rk_scores"), self.scores, note=t("rk_scores_note")))
        self._score_spins: List[tuple] = []

        # ---- results
        self.c_best = StatCard(t("rk_best"), COL["navy"])
        self.c_pf_save = StatCard(t("rk_pf_saving") + " (m³/yr)", COL["green"])
        self.c_pf_capex = StatCard(t("rk_pf_capex"), COL["orange"])
        self.lay.addLayout(stat_row(self.c_best, self.c_pf_save, self.c_pf_capex))
        self.table = make_table([t("rk_rank"), t("rk_measure"), t("rk_target"), t("rk_score"), t("rk_topsis"),
                                 t("rk_c_saving"), t("ec_npv"), t("rk_c_payback"), t("rk_c_capex"), t("rk_pfirst"), t("rk_range")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(240)
        self.lay.addWidget(card(t("rk_result"), self.table, note=t("rk_result_note")))
        self.pf_label = QLabel("")
        self.pf_label.setWordWrap(True)
        self.pf_label.setObjectName("cardnote")
        self.lay.addWidget(card(t("rk_portfolio"), self.pf_label, note=t("rk_portfolio_note")))
        self.warn = _message_label()
        self.lay.addWidget(self.warn)
        self.lay.addStretch(1)

    # ------------------------------------------------------------------------------------------ helpers
    def _name(self, item) -> str:
        try:
            m = M.get(item.measure_id)
            return f"{m.id}. {m.name(self.t.lang)}"
        except Exception:
            return str(item.measure_id)

    def _target(self, item) -> str:
        return item.target or self.t("ms_plant_wide")

    # ------------------------------------------------------------------------------------------ data -> view
    def refresh(self, plant: Plant) -> None:
        t = self.t
        self.plant = plant
        st = RK.Settings.of(plant)
        self._loading = True
        for c, sp in self.w_spins.items():
            sp.setValue(st.weights[c])
        self.method.setCurrentIndex(max(0, self.method.findData(st.method)))
        self.objective.setCurrentIndex(max(0, self.objective.findData(st.objective)))
        self.budget.setValue(st.budget)
        self.scores.setRowCount(len(plant.plan))
        self._score_spins = []
        for r, it in enumerate(plant.plan):
            put(self.scores, r, 0, self._name(it))
            put(self.scores, r, 1, self._target(it))
            pair = []
            for c, attr in ((2, "ease"), (3, "reliability")):
                sp = dspin(maximum=5.0, minimum=1.0, decimals=0, step=1.0)
                sp.setMinimumWidth(0)
                sp.setValue(getattr(it, attr))
                sp.valueChanged.connect(lambda v, i=r, a=attr: self._score_changed(i, a, v))
                self.scores.setCellWidget(r, c, sp)
                pair.append(sp)
            self._score_spins.append(tuple(pair))
        self._loading = False
        self.msg.setText("" if plant.plan else t("rk_empty"))
        self._show()

    def _show(self) -> None:
        t, plant = self.t, self.plant
        if plant is None:
            return
        self.table.setRowCount(0)
        if not plant.plan:
            for c in (self.c_best, self.c_pf_save, self.c_pf_capex):
                c.set("—")
            self.pf_label.setText("")
            self.warn.setText("")
            return
        try:
            res = RK.rank_plan(plant)
        except RK.RankError:
            self.msg.setText(t("rk_zero_weights"))
            return
        if self.msg.text() == t("rk_zero_weights"):
            self.msg.setText("")
        cur = plant.currency
        self.table.setRowCount(len(res.rows))
        for r, x in enumerate(res.rows):
            put(self.table, r, 0, str(x.rank), True, bold=x.rank == 1)
            put(self.table, r, 1, self._name(x.item), bold=x.rank == 1)
            put(self.table, r, 2, self._target(x.item))
            put(self.table, r, 3, f"{x.wsm:.3f}", True)
            put(self.table, r, 4, f"{x.topsis:.3f}", True)
            put(self.table, r, 5, _fmt(x.raw["saving"]), True)
            put(self.table, r, 6, _fmt(x.raw["npv"]), True)
            put(self.table, r, 7, f"{x.raw['payback']:.1f}", True)
            put(self.table, r, 8, _fmt(x.raw["capex"]), True)
            put(self.table, r, 9, f"{100 * x.p_first:.0f}%", True)
            put(self.table, r, 10, f"{x.rank_min}–{x.rank_max}", True)
        if res.rows:
            self.c_best.set(self._name(res.rows[0].item))
            self.c_best.hint.setText(t("rk_best_hint").format(res.rows[0].p_first * 100))
        pf = res.portfolio
        if pf is not None:
            self.c_pf_save.set(_fmt(pf.saving))
            self.c_pf_capex.set(f"{_fmt(pf.capex)} {cur}")
            names = [self._name(plant.plan[i]) + " — " + self._target(plant.plan[i]) for i in pf.chosen]
            self.pf_label.setText(("\n".join("• " + n for n in names) + "\n" + t("rk_pf_line").format(_fmt(pf.npv), cur))
                                  if names else t("rk_pf_none"))
        lines = [t("rk_w_" + w) for w in res.warnings] + [t("rk_w_skipped_item").format(self._name(plant.plan[i]), why)
                                                          for i, why in res.skipped]
        self.warn.setText("\n".join(lines))

    # ------------------------------------------------------------------------------------------ view -> data
    def _inputs_changed(self, *_a) -> None:
        if self._loading or self.plant is None:
            return
        RK.Settings({c: sp.value() for c, sp in self.w_spins.items()}, self.method.currentData(),
                    self.budget.value(), self.objective.currentData()).store(self.plant)
        self._show()

    def _score_changed(self, i: int, attr: str, v: float) -> None:
        if self._loading or self.plant is None or not (0 <= i < len(self.plant.plan)):
            return
        setattr(self.plant.plan[i], attr, float(v))
        self._show()


class EconPage(QTabWidget):
    """«ارزیابی اقتصادی»: the evaluation of one measure and, on a page of its own, the ranking of all of them."""

    def __init__(self, t: Translator):
        super().__init__()
        self.eval_tab = EconTab(t)
        self.lcc_tab = LccTab(t)
        self.sens_tab = SensitivityTab(t)
        self.risk_tab = RiskTab(t)
        self.rank_tab = RankingTab(t)
        self.subtabs = (self.eval_tab, self.lcc_tab, self.sens_tab, self.risk_tab, self.rank_tab)
        for tab, key in zip(self.subtabs, ("ec_sub_eval", "ec_sub_lcc", "ec_sub_sens", "ec_sub_risk", "ec_sub_rank")):
            self.addTab(tab, t(key))
        self.currentChanged.connect(lambda _i: self._refresh_current())
        self._plant: Optional[Plant] = None

    def refresh(self, plant: Plant) -> None:
        self._plant = plant
        self.eval_tab.refresh(plant)
        w = self.currentWidget()                       # the other pages are rebuilt when opened (the risk run is the costly one)
        for tab in self.subtabs[1:]:
            if tab is w:
                tab.refresh(plant)

    def _refresh_current(self) -> None:
        if self._plant is not None:
            self.refresh(self._plant)

    def select_item(self, index: int) -> None:
        self.setCurrentWidget(self.eval_tab)
        self.eval_tab.select_item(index)
