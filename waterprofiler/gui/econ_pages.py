"""Pages of the economic analysis: life-cycle cost, sensitivity, Monte-Carlo risk."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QGridLayout, QHeaderView, QLabel, QSpinBox, QWidget

from .. import economics as EC
from .. import econrisk as ER
from .. import measures as M
from ..i18n import Translator
from ..model import Plant
from .econ_charts import HistogramChart, LccChart, SpiderChart, TornadoChart
from .econ_tab import _two_line_table
from .tabs import _Scroll, _fmt, _message_label, make_table, put, stat_row
from .theme import COL
from .widgets import StatCard, card, dspin

VAR_KEY = {"saving_m3": "ec_s_saving", "price": "ec_s_price", "capex": "ec_s_capex", "opex": "ec_s_opex",
           "rate_pct": "ec_s_rate", "life": "ec_s_life", "price_esc_pct": "ec_s_gprice", "degradation_pct": "ec_s_degr",
           "other_benefit": "ec_s_other", "opex_esc_pct": "ec_s_gopex", "salvage": "ec_s_salvage"}


def _lbl(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("cardnote")
    lab.setWordWrap(True)
    return lab


class _ItemTab(_Scroll):
    """A page that analyses one measure of the plan, chosen in a list on top (the list is rebuilt on every refresh)."""
    WITH_PLAN = False

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False
        self.msg = _message_label()
        self.lay.addWidget(self.msg)
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._picked)
        self.lay.addWidget(card(t("ec_pick"), self.combo, note=t("ec_pick_note")))

    def _label(self, i: int, it) -> str:
        m = M.get(it.measure_id)
        return f"{m.id}. {m.name(self.t.lang)}" + (f" — {it.target}" if it.target else "")

    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        keep = self.combo.currentData()
        self._loading = True
        self.combo.clear()
        if self.WITH_PLAN:
            self.combo.addItem(self.t("rs_plan_all"), "plan")
        for i, it in enumerate(plant.plan):
            self.combo.addItem(self._label(i, it), f"item:{i}")
        want = self._wanted_key() or keep
        k = self.combo.findData(want) if want is not None else -1
        self.combo.setCurrentIndex(k if k >= 0 else 0)
        self._loading = False
        self.msg.setText("" if plant.plan else self.t("rk_empty"))
        self._show()

    def _wanted_key(self) -> Optional[str]:
        return None

    def _picked(self, *_a) -> None:
        if not self._loading:
            self._on_pick()
            self._show()

    def _on_pick(self) -> None:
        pass

    def _index(self) -> Optional[int]:
        d = self.combo.currentData()
        return int(d.split(":")[1]) if isinstance(d, str) and d.startswith("item:") else None

    def _result(self) -> Optional[EC.EconResult]:
        i = self._index()
        if self.plant is None or i is None:
            return None
        ie = EC.evaluate_plan_economics(self.plant)
        return ie[i].result if i < len(ie) else None

    def _show(self) -> None:
        raise NotImplementedError


# ================================================================================================ LCC
class LccTab(_ItemTab):
    def __init__(self, t: Translator):
        super().__init__(t)
        self.c_lcc = StatCard(t("lcc_lcc"), COL["navy"])
        self.c_eac = StatCard(t("lcc_eac"), COL["blue"])
        self.c_unit = StatCard(t("lcc_unit"), COL["green"])
        self.lay.addLayout(stat_row(self.c_lcc, self.c_eac, self.c_unit))
        self.chart = LccChart()
        self.lay.addWidget(card("", self.chart, note=t("lcc_chart_note")))
        self.parts = _two_line_table([t("lcc_component"), t("lcc_pv"), t("lcc_share")])
        self.parts.setMinimumHeight(230)
        self.lay.addWidget(card(t("lcc_parts"), self.parts, note=t("lcc_parts_note")))
        self.cmp = _two_line_table([t("ms_measure"), t("lcc_lcc"), t("lcc_eac"), t("lcc_unit"), t("ec_npv"), t("lcc_capex_share")])
        self.cmp.setMinimumHeight(220)
        self.lay.addWidget(card(t("lcc_compare"), self.cmp, note=t("lcc_compare_note")))
        lab = _lbl(t("lcc_method"))
        self.lay.addWidget(card(t("ec_method"), lab))
        self.lay.addStretch(1)

    def _show(self) -> None:
        t, plant = self.t, self.plant
        cur = plant.currency if plant else ""
        r = self._result()
        names = (t("lcc_n_capex"), t("lcc_n_opex"), t("lcc_n_repl"))
        if r is None:
            for c in (self.c_lcc, self.c_eac, self.c_unit):
                c.set("—")
            self.chart.set_data(t("lcc_chart"), [], names)
            self.parts.setRowCount(0)
        else:
            self.c_lcc.set(f"{r.lcc:,.0f}", cur)
            self.c_eac.set(f"{r.eac:,.0f}", f"{cur} / {t('ec_year_unit')}")
            self.c_unit.set("—" if r.lcow is None else f"{r.lcow:,.3f}", f"{cur} / m³")
            self.chart.set_data(t("lcc_chart"), r.lcc_years, names)
            rows = [(t("lcc_n_capex"), r.lcc_parts["capex"]), (t("lcc_n_opex"), r.lcc_parts["opex"]),
                    (t("lcc_n_repl"), r.lcc_parts["repl"]), (t("lcc_n_salvage"), r.lcc_parts["salvage"]), (t("lcc_total"), r.lcc)]
            self.parts.setRowCount(len(rows))
            for i, (n, v) in enumerate(rows):
                last = i == len(rows) - 1
                put(self.parts, i, 0, n, bold=last)
                put(self.parts, i, 1, _fmt(v), True, bold=last)
                put(self.parts, i, 2, f"{100 * v / r.lcc:.1f}%" if r.lcc else "—", True, bold=last)
        items = EC.evaluate_plan_economics(plant) if plant is not None and plant.plan else []
        self.cmp.setRowCount(len(items))
        for i, ie in enumerate(items):
            put(self.cmp, i, 0, self._label(i, ie.item))
            x = ie.result
            if x is None:
                for c in range(1, 6):
                    put(self.cmp, i, c, "—")
                continue
            put(self.cmp, i, 1, _fmt(x.lcc), True, bold=True)
            put(self.cmp, i, 2, _fmt(x.eac), True)
            put(self.cmp, i, 3, "—" if x.lcow is None else f"{x.lcow:,.3f}", True)
            put(self.cmp, i, 4, _fmt(x.npv), True)
            put(self.cmp, i, 5, f"{100 * x.lcc_parts['capex'] / x.lcc:.0f}%" if x.lcc else "—", True)


# ================================================================================================ sensitivity
class SensitivityTab(_ItemTab):
    DELTAS = (0.1, 0.2, 0.3)

    def __init__(self, t: Translator):
        super().__init__(t)
        self.delta = QComboBox()
        for d in self.DELTAS:
            self.delta.addItem(f"±{d * 100:.0f}%", d)
        self.delta.setCurrentIndex(1)
        self.delta.currentIndexChanged.connect(self._picked)
        self.lay.addWidget(card(t("sn_delta"), self.delta, note=t("sn_delta_note")))
        self.tornado = TornadoChart()
        self.lay.addWidget(card("", self.tornado))
        self.table = _two_line_table([t("ec_var"), t("sn_low_value"), t("sn_high_value"), t("sn_npv_low"), t("sn_npv_high"),
                                      t("ec_swing"), t("sn_lcow_low"), t("sn_lcow_high")])
        self.table.setMinimumHeight(290)
        self.lay.addWidget(card(t("sn_table"), self.table, note=t("sn_table_note")))
        self.spider = SpiderChart()
        self.lay.addWidget(card("", self.spider, note=t("sn_spider_note")))
        self.be = _two_line_table([t("ec_var"), t("sn_be_base"), t("sn_be_change"), t("sn_be_value")])
        self.be.setMinimumHeight(210)
        self.lay.addWidget(card(t("sn_be"), self.be, note=t("sn_be_note")))
        self.grid = make_table([""])
        self.grid.setMinimumHeight(260)
        self.lay.addWidget(card(t("sn_grid"), self.grid, note=t("sn_grid_note")))
        self.lay.addStretch(1)

    def _show(self) -> None:
        t, plant = self.t, self.plant
        r = self._result()
        for tb in (self.table, self.be):
            tb.setRowCount(0)
        self.grid.setRowCount(0)
        if r is None:
            self.tornado.set_data(t("sn_tornado"), [], 0.0)
            self.spider.set_data(t("sn_spider"), [], [])
            return
        inp, d = r.inputs, self.delta.currentData() or 0.2
        pc = f"{d * 100:.0f}%"
        rows = ER.sensitivity_table(inp, d)
        self.tornado.set_data(t("sn_tornado").format(pc), [(t(VAR_KEY[x.var]), x.low.npv, x.high.npv) for x in rows], r.npv,
                              (t("sn_leg_low"), t("sn_leg_high")), f"NPV = {_fmt(r.npv)}")
        self.table.setRowCount(len(rows))
        for i, x in enumerate(rows):
            put(self.table, i, 0, t(VAR_KEY[x.var]))
            put(self.table, i, 1, f"{x.low_value:,.2f}", True)
            put(self.table, i, 2, f"{x.high_value:,.2f}", True)
            put(self.table, i, 3, _fmt(x.low.npv), True)
            put(self.table, i, 4, _fmt(x.high.npv), True)
            put(self.table, i, 5, _fmt(x.swing), True, bold=True)
            put(self.table, i, 6, "—" if x.low.lcow is None else f"{x.low.lcow:,.3f}", True)
            put(self.table, i, 7, "—" if x.high.lcow is None else f"{x.high.lcow:,.3f}", True)
        xs, ys = ER.spider(inp)
        self.spider.set_data(t("sn_spider"), xs, [(t(VAR_KEY[v]), vals) for v, vals in ys.items()])
        be = ER.break_even(inp)
        self.be.setRowCount(len(be))
        for i, (v, x) in enumerate(be.items()):
            base = getattr(inp, v)
            put(self.be, i, 0, t(VAR_KEY[v]))
            put(self.be, i, 1, f"{base:,.2f}", True)
            put(self.be, i, 2, t("sn_be_none") if x is None else f"{x * 100:+.1f}%", True, bold=x is not None)
            put(self.be, i, 3, "—" if x is None else f"{base * (1 + x):,.2f}", True)
        a, b, g = ER.two_way(inp)
        self.grid.setColumnCount(len(b) + 1)
        self.grid.setHorizontalHeaderLabels([t("sn_grid_corner")] + [f"{t('ec_s_price')} {x * 100:+.0f}%" for x in b])
        self.grid.setRowCount(len(a))
        lo, hi = min(min(row) for row in g), max(max(row) for row in g)
        for i, x in enumerate(a):
            put(self.grid, i, 0, f"{t('ec_s_saving')} {x * 100:+.0f}%", bold=abs(x) < 1e-9)
            for j, v in enumerate(g[i]):
                put(self.grid, i, j + 1, _fmt(v), True, bold=(abs(x) < 1e-9 and abs(b[j]) < 1e-9))
                it = self.grid.item(i, j + 1)
                if it is not None:
                    it.setBackground(QColor("#FDEBEB") if v < 0 else QColor("#E7F5EB"))
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)


# ================================================================================================ Monte Carlo risk
class RiskTab(_ItemTab):
    WITH_PLAN = True

    def __init__(self, t: Translator):
        super().__init__(t)
        # settings
        self.runs = QSpinBox()
        self.runs.setRange(100, ER.MAX_RUNS)
        self.runs.setSingleStep(500)
        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.runs.valueChanged.connect(self._settings_changed)
        self.seed.valueChanged.connect(self._settings_changed)
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(14)
        for k, (lab, w) in enumerate(((t("rs_runs"), self.runs), (t("rs_seed"), self.seed))):
            g.addWidget(_lbl(lab), 0, k)
            g.addWidget(w, 1, k)
            g.setColumnStretch(k, 1)
        self.lay.addWidget(card(t("rs_settings"), box, note=t("rs_settings_note")))
        self.ranges = make_table([t("ec_var"), t("rs_scale"), t("rs_low"), t("rs_high")])
        self.ranges.setMinimumHeight(330)
        self._range_spins: Dict[str, Tuple[object, object]] = {}
        for r, var in enumerate(ER.MC_VARS):
            self.ranges.insertRow(r)
            put(self.ranges, r, 0, t(VAR_KEY[var]))
            put(self.ranges, r, 1, t("rs_rel") if var in ER.REL_VARS else t("rs_pp"))
            pair = []
            for c in (2, 3):
                sp = dspin(maximum=1000.0, minimum=-100.0, decimals=1, step=5.0)
                sp.setMinimumWidth(0)
                sp.valueChanged.connect(self._settings_changed)
                self.ranges.setCellWidget(r, c, sp)
                pair.append(sp)
            self._range_spins[var] = (pair[0], pair[1])
        self.lay.addWidget(card(t("rs_ranges"), self.ranges, note=t("rs_ranges_note")))
        # results
        self.c_mean = StatCard(t("rs_mean"), COL["navy"])
        self.c_ploss = StatCard(t("rs_ploss"), COL["red"])
        self.c_var = StatCard(t("rs_var5"), COL["orange"])
        self.lay.addLayout(stat_row(self.c_mean, self.c_ploss, self.c_var))
        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        self.verdict.setVisible(False)
        self.lay.addWidget(self.verdict)
        self.hist = HistogramChart()
        self.lay.addWidget(card("", self.hist, note=t("rs_hist_note")))
        self.stats = _two_line_table([t("rs_metric"), t("rs_mean"), t("rs_sd"), "P5", "P50", "P95"])
        self.stats.setMinimumHeight(190)
        self.lay.addWidget(card(t("rs_stats"), self.stats, note=t("rs_stats_note")))
        self.drivers = TornadoChart()
        self.lay.addWidget(card("", self.drivers, note=t("rs_drivers_note")))
        self.dtable = _two_line_table([t("ec_var"), t("rs_rho")])
        self.dtable.setMinimumHeight(220)
        self.lay.addWidget(card(t("rs_dtable"), self.dtable))
        self.lay.addWidget(card(t("ec_method"), _lbl(t("rs_method"))))
        self.lay.addStretch(1)

    # the settings live in the plant file
    def _wanted_key(self) -> Optional[str]:
        return ER.RiskSettings.of(self.plant).scope if self.plant is not None else None

    def refresh(self, plant: Plant) -> None:
        super().refresh(plant)
        st = ER.RiskSettings.of(plant)
        self._loading = True
        self.runs.setValue(st.runs)
        self.seed.setValue(st.seed)
        for var, (a, b) in self._range_spins.items():
            a.setValue(st.ranges[var][0])
            b.setValue(st.ranges[var][1])
        self._loading = False

    def _settings(self) -> ER.RiskSettings:
        return ER.RiskSettings(self.runs.value(), self.seed.value(),
                               {v: (a.value(), b.value()) for v, (a, b) in self._range_spins.items()},
                               str(self.combo.currentData() or "plan"))

    def _on_pick(self) -> None:
        if self.plant is not None:
            self._settings().store(self.plant)

    def _settings_changed(self, *_a) -> None:
        if self._loading or self.plant is None:
            return
        self._settings().store(self.plant)
        self._show()

    def _name_of(self, key: str) -> str:
        if key.startswith("item:") and self.plant is not None:
            try:
                return self._label(0, self.plant.plan[int(key.split(":")[1])])
            except (ValueError, IndexError):
                return key
        return self.t(VAR_KEY.get(key, key))

    def _show(self) -> None:
        t, plant = self.t, self.plant
        if plant is None:
            return
        for tb in (self.stats, self.dtable):
            tb.setRowCount(0)
        if not plant.plan:
            for c in (self.c_mean, self.c_ploss, self.c_var):
                c.set("—")
            self.verdict.setVisible(False)
            self.hist.set_data(t("rs_hist"), [], [], [], [])
            self.drivers.set_data(t("rs_drivers"), [], 0.0)
            return
        res = ER.simulate(plant, self._settings())
        if res is None:
            self.msg.setText(t("rs_none"))
            return
        self.msg.setText("")
        cur = plant.currency
        s = res.npv_stats
        self.c_mean.set(f"{s.mean:,.0f}", f"{cur} · " + t("rs_base").format(_fmt(res.base_npv)),
                        COL["green"] if s.mean >= 0 else COL["red"])
        self.c_ploss.set(f"{res.p_loss * 100:.1f}%", t("rs_ploss_hint"), COL["green"] if res.p_loss < 0.1 else COL["red"])
        self.c_var.set(f"{res.var5:,.0f}", f"{cur} · " + t("rs_var5_hint").format(_fmt(res.shortfall)))
        bg, fg, bd = (("#E7F5EB", "#14572A", "#BFE3CB") if res.p_loss < 0.1 else
                      ("#FFF3E0", "#8A4B08", "#F6D9AE") if res.p_loss < 0.3 else ("#FDEBEB", "#8E1F1F", "#F3C2C2"))
        self.verdict.setStyleSheet(f"background:{bg}; color:{fg}; border:1px solid {bd}; border-radius:10px; padding:10px 14px;")
        self.verdict.setText(t("rs_v_low" if res.p_loss < 0.1 else "rs_v_mid" if res.p_loss < 0.3 else "rs_v_high")
                             .format(res.p_loss * 100, res.runs))
        self.verdict.setVisible(True)
        marks = [("P5", s.p5, COL["red"]), ("P50", s.p50, COL["navy"]), ("P95", s.p95, COL["green"])]
        self.hist.set_data(t("rs_hist"), res.hist_counts, res.hist_edges, res.cdf_x, marks, (t("rs_leg_freq"), t("rs_leg_cdf")))
        rows = [(t("ec_npv"), res.npv_stats, 0)]
        if res.lcc_stats:
            rows.append((t("lcc_lcc"), res.lcc_stats, 0))
        if res.lcow_stats:
            rows.append((t("ec_lcow") + f" ({cur}/m³)", res.lcow_stats, 3))
        if res.irr_stats:
            rows.append((t("ec_irr") + " (%)", res.irr_stats, 1))
        self.stats.setRowCount(len(rows))
        for i, (n, x, dec) in enumerate(rows):
            put(self.stats, i, 0, n, bold=i == 0)
            for j, v in enumerate((x.mean, x.sd, x.p5, x.p50, x.p95), start=1):
                put(self.stats, i, j, f"{v:,.{dec}f}", True)
        self.drivers.set_data(t("rs_drivers"), [(self._name_of(k), min(0.0, v), max(0.0, v)) for k, v in res.drivers], 0.0,
                              (t("rs_leg_neg"), t("rs_leg_pos")))
        self.dtable.setRowCount(len(res.drivers))
        for i, (k, v) in enumerate(res.drivers):
            put(self.dtable, i, 0, self._name_of(k))
            put(self.dtable, i, 1, f"{v:+.2f}", True, bold=i == 0)
