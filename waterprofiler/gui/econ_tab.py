"""Economic evaluation page: inputs, indicators, cash-flow chart, yearly table, sensitivity, plan comparison."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QVBoxLayout, QWidget

from .. import economics as EC
from .. import measures as M
from ..i18n import Translator
from ..model import PlanItem, Plant
from .tabs import _Scroll, _fmt, _message_label, make_table, put, stat_row
from .theme import COL
from .widgets import StatCard, button, card, dspin

LRM = "‎"
VERDICT_STYLE = {
    "good": ("#E7F5EB", "#14572A", "#BFE3CB"), "marginal": ("#FFF3E0", "#8A4B08", "#F6D9AE"),
    "poor": ("#FDEBEB", "#8E1F1F", "#F3C2C2"), "invalid": ("#EEF2F7", "#475569", "#D5DEE9"),
}


class CashFlowChart(QWidget):
    """Net cash flow per year (bars) and cumulative discounted cash flow (line)."""

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.res: Optional[EC.EconResult] = None
        self.setMinimumHeight(300)

    def set_result(self, r: Optional[EC.EconResult]) -> None:
        self.res = r
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        f = QFont(self.font())
        fm = QFontMetrics(f)
        p.setPen(QColor(COL["navy"]))
        bold = QFont(f)
        bold.setBold(True)
        p.setFont(bold)
        p.drawText(QRectF(0, 2, w, 24), Qt.AlignmentFlag.AlignCenter, self.t("ec_chart"))
        p.setFont(f)
        r = self.res
        if r is None:
            p.end()
            return
        # legend
        items = [(COL["blue"], self.t("ec_leg_net"), "bar"), ("#E9892B", self.t("ec_leg_cum"), "line")]
        total = sum(22 + fm.horizontalAdvance(n) + 24 for _c, n, _k in items)
        x = max(8.0, (w - total) / 2.0)
        for col, name, kind in items:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            if kind == "bar":
                p.drawRoundedRect(QRectF(x, 36, 12, 10), 2, 2)
            else:
                p.setPen(QPen(QColor(col), 3))
                p.drawLine(QPointF(x, 41), QPointF(x + 14, 41))
            p.setPen(QColor(COL["text"]))
            tw = fm.horizontalAdvance(name)
            p.drawText(QRectF(x + 20, 30, tw + 8, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            x += 22 + tw + 24
        left, right, top, bottom = 64.0, 14.0, 62.0, 30.0
        pw, ph = w - left - right, h - top - bottom
        vals = list(r.net) + list(r.dcum)
        vmax, vmin = max(max(vals), 0.0), min(min(vals), 0.0)
        span = (vmax - vmin) or 1.0
        vmax += span * 0.08
        vmin -= span * 0.08 if vmin < 0 else 0.0
        span = vmax - vmin

        def Y(v: float) -> float:
            return top + ph * (vmax - v) / span

        grid = QPen(QColor(COL["line"]))
        for k in range(5):
            v = vmin + span * k / 4
            p.setPen(grid)
            p.drawLine(QPointF(left, Y(v)), QPointF(left + pw, Y(v)))
            p.setPen(QColor(COL["sub"]))
            from .widgets import _short
            p.drawText(QRectF(0, Y(v) - 9, left - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _short(v))
        p.setPen(QPen(QColor(COL["sub"]), 1.4))
        p.drawLine(QPointF(left, Y(0)), QPointF(left + pw, Y(0)))
        n = len(r.years)
        gw = pw / n
        p.setPen(Qt.PenStyle.NoPen)
        pts = []
        step = max(1, n // 12)
        for i, yr in enumerate(r.years):
            cx = left + (i + 0.5) * gw
            v = r.net[i]
            p.setBrush(QColor(COL["blue"] if v >= 0 else COL["red"]))
            y0, y1 = Y(max(v, 0)), Y(min(v, 0))
            p.drawRoundedRect(QRectF(cx - gw * 0.3, y0, gw * 0.6, max(1.0, y1 - y0)), 2, 2)
            pts.append(QPointF(cx, Y(r.dcum[i])))
            if i % step == 0:
                p.setPen(QColor(COL["text"]))
                p.drawText(QRectF(cx - 20, top + ph + 6, 40, 18), Qt.AlignmentFlag.AlignCenter, str(yr))
                p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        p.setPen(QPen(QColor("#E9892B"), 2.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setBrush(QColor("#E9892B"))
        p.setPen(QPen(QColor("#FFFFFF"), 1.2))
        for q in pts:
            p.drawEllipse(q, 3.4, 3.4)
        p.end()


class EconTab(_Scroll):
    FIELDS = [   # (i18n key, PlanItem attribute, maximum, decimals)
        ("ec_pct", "saving_pct", 100.0, 2), ("ec_capex", "capex", 1e13, 0), ("ec_opex", "opex", 1e13, 0),
        ("ec_life", "life_years", 100.0, 0),
        ("ec_rate", "rate_pct", 500.0, 2), ("ec_price", "water_price", 1e9, 4), ("ec_other", "other_benefit", 1e13, 0),
        ("ec_salvage", "salvage", 1e13, 0),
        ("ec_gprice", "price_esc_pct", 200.0, 2), ("ec_gopex", "opex_esc_pct", 200.0, 2),
        ("ec_degr", "degradation_pct", 99.0, 2), ("ec_repl_year", "repl_year", 100.0, 0),
        ("ec_repl_cost", "repl_cost", 1e13, 0),
    ]

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False
        self.msg = _message_label()
        self.lay.addWidget(self.msg)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._select)
        self.lay.addWidget(card(t("ec_pick"), self.combo, note=t("ec_pick_note")))

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.spins: Dict[str, object] = {}
        for i, (key, attr, mx, dec) in enumerate(self.FIELDS):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(3)
            lab = QLabel(t(key))
            lab.setObjectName("cardnote")
            lab.setWordWrap(True)
            sp = dspin(maximum=mx, decimals=dec, step=1.0)
            sp.setMinimumWidth(0)
            sp.valueChanged.connect(lambda v, a=attr: self._set(a, v))
            self.spins[attr] = sp
            bl.addWidget(lab)
            bl.addWidget(sp)
            grid.addWidget(box, i // 4, i % 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        self.auto_price = QLabel("")
        self.auto_price.setObjectName("cardnote")
        self.auto_price.setWordWrap(True)
        self.saving_info = QLabel("")
        self.saving_info.setObjectName("cardnote")
        self.saving_info.setWordWrap(True)
        self.lay.addWidget(card(t("ec_inputs"), self.saving_info, grid_w, self.auto_price, note=t("ec_inputs_note")))

        self.c_npv = StatCard(t("ec_npv"), COL["navy"])
        self.c_irr = StatCard(t("ec_irr"), COL["blue"])
        self.c_bcr = StatCard(t("ec_bcr"), COL["green"])
        self.c_spb = StatCard(t("ec_spb"), COL["orange"])
        self.c_dpb = StatCard(t("ec_dpb"), COL["orange"])
        self.c_lcow = StatCard(t("ec_lcow"), COL["navy"])
        self.lay.addLayout(stat_row(self.c_npv, self.c_irr, self.c_bcr))
        self.lay.addLayout(stat_row(self.c_spb, self.c_dpb, self.c_lcow))
        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        self.verdict.setVisible(False)
        self.lay.addWidget(self.verdict)

        self.chart = CashFlowChart(t)
        self.lay.addWidget(card("", self.chart))
        self.flows = make_table([t("ec_year"), t("ec_vol"), t("ec_benefit"), t("ec_cost"), t("ec_net"), t("ec_cum"), t("ec_dcum")])
        self.flows.setMinimumHeight(300)
        self.lay.addWidget(card(t("ec_flows"), self.flows))
        self.sens = make_table([t("ec_var"), t("ec_npv_low"), t("ec_npv_high"), t("ec_swing")])
        self.sens.setMinimumHeight(250)
        self.lay.addWidget(card(t("ec_sens"), self.sens, note=t("ec_sens_note")))
        self.cmp = make_table([t("ms_measure"), t("ec_saving_col"), t("ec_capex"), t("ec_npv"), t("ec_irr"), t("ec_spb"),
                               t("ec_bcr"), t("ec_lcow"), t("ec_verdict")])
        self.cmp.setMinimumHeight(240)
        self.cmp.cellClicked.connect(lambda r, _c: self.combo.setCurrentIndex(r) if r < self.combo.count() else None)
        self.lay.addWidget(card(t("ec_compare"), self.cmp, note=t("ec_compare_note")))
        self.lay.addWidget(card(t("ec_method"), self._method_label()))
        self.lay.addStretch(1)

    def _method_label(self) -> QLabel:
        lab = QLabel(self.t("ec_method_text"))
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setObjectName("cardnote")
        lab.setAlignment(Qt.AlignmentFlag.AlignTop | (Qt.AlignmentFlag.AlignRight if self.t.rtl else Qt.AlignmentFlag.AlignLeft))
        return lab

    # ------------------------------------------------------------------ data
    def _item(self) -> Optional[PlanItem]:
        i = self.combo.currentIndex()
        if self.plant is None or not (0 <= i < len(self.plant.plan)):
            return None
        return self.plant.plan[i]

    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        keep = self.combo.currentIndex()
        self._loading = True
        self.combo.clear()
        for it in plant.plan:
            if it.measure_id in {m.id for m in M.all_measures()}:
                m = M.get(it.measure_id)
                self.combo.addItem(f"{m.id}. {m.name(self.t.lang)} — {it.target or self.t('ms_plant_wide')}")
        if self.combo.count():
            self.combo.setCurrentIndex(max(0, min(keep, self.combo.count() - 1)))
        self._loading = False
        self._select()

    def select_item(self, index: int) -> None:
        if 0 <= index < self.combo.count():
            self.combo.setCurrentIndex(index)

    def _select(self, *_a) -> None:
        if self._loading:
            return
        it = self._item()
        has = it is not None
        for sp in self.spins.values():
            sp.setEnabled(has)
        if not has:
            self.msg.setText(self.t("ec_empty"))
            self._clear()
            self._compare()
            return
        self.msg.setText("")
        self._loading = True
        for _k, attr, _mx, _d in self.FIELDS:
            self.spins[attr].setValue(float(getattr(it, attr)))
        self._loading = False
        self._recalc()

    def _set(self, attr: str, value: float) -> None:
        if self._loading:
            return
        it = self._item()
        if it is None:
            return
        setattr(it, attr, value)
        self._recalc()

    def _clear(self) -> None:
        for c in (self.c_npv, self.c_irr, self.c_bcr, self.c_spb, self.c_dpb, self.c_lcow):
            c.set("—", "")
        self.verdict.setVisible(False)
        self.chart.set_result(None)
        self.flows.setRowCount(0)
        self.sens.setRowCount(0)
        self.saving_info.setText("")
        self.auto_price.setText("")

    # ------------------------------------------------------------------ results
    def _recalc(self) -> None:
        t = self.t
        it = self._item()
        if it is None or self.plant is None:
            return
        cur = self.plant.currency
        try:
            inp = EC.inputs_from_item(self.plant, it)
            res = EC.evaluate(inp)
        except EC.EconError as e:
            self._clear()
            self.msg.setText(t("ec_err_" + str(e)) if ("ec_err_" + str(e)) in _keys() else t("ec_err_generic"))
            self._compare()
            return
        self.msg.setText("")
        auto = EC.default_price(self.plant, it.target)
        self.saving_info.setText(t("ec_saving_info", vol=f"{inp.saving_m3:,.0f}", day=f"{inp.saving_m3 / 365:,.1f}"))
        self.auto_price.setText(t("ec_auto_price", v=f"{auto:,.3f}", cur=cur) + (
            "  ·  " + t("ec_auto_used") if it.water_price <= 0 else ""))
        good = res.npv >= 0
        self.c_npv.set(f"{res.npv:,.0f}", cur, COL["green"] if good else COL["red"])
        self.c_irr.set("—" if res.irr is None else f"{res.irr:.1f}%",
                       t("ec_irr_vs", r=f"{inp.rate_pct:g}"), COL["green"] if res.irr is not None and res.irr >= inp.rate_pct else COL["red"])
        self.c_bcr.set("—" if res.bcr is None else f"{res.bcr:.2f}", t("ec_bcr_hint"),
                       COL["green"] if res.bcr is not None and res.bcr >= 1 else COL["red"])
        self.c_spb.set("—" if res.payback is None else f"{res.payback:.2f}", t("ec_year_unit") if res.payback is not None else t("ec_never"))
        self.c_dpb.set("—" if res.dpayback is None else f"{res.dpayback:.2f}", t("ec_year_unit") if res.dpayback is not None else t("ec_never"))
        self.c_lcow.set("—" if res.lcow is None else f"{res.lcow:,.3f}", f"{cur} / m³" + (
            "  ·  " + t("ec_lcow_vs", p=f"{inp.price:,.3f}") if res.lcow is not None else ""),
            COL["green"] if res.lcow is not None and res.lcow <= inp.price else COL["red"])
        bg, fg, bd = VERDICT_STYLE[res.verdict]
        self.verdict.setStyleSheet(f"background:{bg}; color:{fg}; border:1px solid {bd}; border-radius:10px; padding:10px 14px;")
        self.verdict.setText(t("ec_v_" + res.verdict))
        self.verdict.setVisible(True)
        self.chart.set_result(res)
        self._fill_flows(res)
        self._fill_sens(inp)
        self._compare()

    def _fill_flows(self, r: EC.EconResult) -> None:
        tb = self.flows
        tb.setRowCount(len(r.years))
        for i, yr in enumerate(r.years):
            put(tb, i, 0, str(yr), True)
            put(tb, i, 1, _fmt(r.volume[i]), True)
            put(tb, i, 2, _fmt(r.benefit[i]), True)
            put(tb, i, 3, _fmt(r.cost[i]), True)
            put(tb, i, 4, _fmt(r.net[i]), True, bold=True)
            put(tb, i, 5, _fmt(r.cum[i]), True)
            put(tb, i, 6, _fmt(r.dcum[i]), True)

    def _fill_sens(self, inp: EC.EconInputs) -> None:
        names = {"saving_m3": self.t("ec_s_saving"), "price": self.t("ec_s_price"), "capex": self.t("ec_s_capex"),
                 "opex": self.t("ec_s_opex"), "rate_pct": self.t("ec_s_rate"), "life": self.t("ec_s_life")}
        rows = EC.sensitivity(inp)
        self.sens.setRowCount(len(rows))
        for i, (n, lo, hi, sw) in enumerate(rows):
            put(self.sens, i, 0, names[n])
            put(self.sens, i, 1, _fmt(lo), True)
            put(self.sens, i, 2, _fmt(hi), True)
            put(self.sens, i, 3, _fmt(sw), True, bold=True)

    def _compare(self) -> None:
        t = self.t
        tb = self.cmp
        items = EC.evaluate_plan_economics(self.plant) if self.plant is not None and self.plant.plan else []
        tb.setRowCount(len(items))
        for i, ie in enumerate(items):
            m = M.get(ie.item.measure_id)
            put(tb, i, 0, f"{m.id}. {m.name(t.lang)}")
            r = ie.result
            if r is None:
                for c in range(1, 9):
                    put(tb, i, c, "—")
                continue
            put(tb, i, 1, _fmt(r.inputs.saving_m3), True)
            put(tb, i, 2, _fmt(r.inputs.capex), True)
            put(tb, i, 3, _fmt(r.npv), True, bold=True)
            put(tb, i, 4, "—" if r.irr is None else f"{r.irr:.1f}%", True)
            put(tb, i, 5, "—" if r.payback is None else f"{r.payback:.2f}", True)
            put(tb, i, 6, "—" if r.bcr is None else f"{r.bcr:.2f}", True)
            put(tb, i, 7, "—" if r.lcow is None else f"{r.lcow:,.3f}", True)
            put(tb, i, 8, t("ec_v_short_" + r.verdict))


def _keys():
    from ..i18n import all_keys
    return set(all_keys())
