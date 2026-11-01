"""Pages for the water-saving measures database and the saving plan."""

from __future__ import annotations

from html import escape
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QTableWidget, QWidget,
)

from .. import measures as M
from ..i18n import Translator
from ..model import Plant
from .tabs import _Scroll, _fmt, _message_label, make_table, put, stat_row
from .theme import COL
from .widgets import StatCard, button, card, dspin


def _label(rtl: bool) -> QLabel:
    lab = QLabel()
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.TextFormat.RichText)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lab.setAlignment(Qt.AlignmentFlag.AlignTop | (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft))
    return lab


def _fmt_range(lo: float, hi: float) -> str:
    return f"{_fmt(lo)} – {_fmt(hi)}"


class MeasuresTab(_Scroll):
    """Browse, filter and inspect the 80 measures; send one to the plan."""

    plan_requested = Signal(int, str)       # measure id, target subsystem name ("" = plant-wide)

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._rows: List[M.Measure] = []

        # ---- filters
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("ms_search"))
        self.search.setClearButtonEnabled(True)
        self.group = QComboBox()
        self.group.addItem(t("ms_all"), 0)
        for g in range(1, 10):
            self.group.addItem(f"{g}. {M.group_name(g, t.lang)}", g)
        self.relevant = QCheckBox(t("ms_relevant"))
        self.count = QLabel()
        self.count.setObjectName("cardnote")
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)
        bl.addWidget(self.search, 2)
        bl.addWidget(self.group, 2)
        bl.addWidget(self.relevant)
        bl.addWidget(self.count)
        self.lay.addWidget(card("", bar, note=t("ms_disclaimer")))

        # ---- table
        self.table = make_table([t("ms_id"), t("ms_measure"), t("ms_use"), t("ms_fresh"), t("ms_capex"), t("ms_est")])
        hh = self.table.horizontalHeader()
        from PySide6.QtWidgets import QHeaderView
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setMinimumHeight(430)
        self.lay.addWidget(card(t("tab_measures"), self.table))

        # ---- detail
        self.detail = _label(t.rtl)
        self.target = QComboBox()
        self.add = button("+  " + t("ms_add"), "primary", self._add)
        self.add.setEnabled(False)
        self.status = _message_label()
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel(t("ms_target")))
        rl.addWidget(self.target, 1)
        rl.addWidget(self.add)
        self.lay.addWidget(card(t("ms_detail"), self.detail, row, self.status))

        # ---- rules and sources
        rules = _label(t.rtl)
        rules.setText("<br>".join(escape(x) for x in t("ms_rules").split("\n")))
        self.lay.addWidget(card(t("ms_rules_title"), rules))
        from .. import measures_data as D
        src = _label(t.rtl)
        lines = [f"<b>{escape(a)}</b> — {escape(b)}" for a, b, _fa in D.SOURCES]
        sec = [f"{escape(fa if t.lang == 'fa' else en)}: {lo}–{hi}٪" if t.lang == "fa"
               else f"{escape(en)}: {lo}–{hi}%" for fa, en, lo, hi in D.SECTOR_POTENTIAL]
        src.setText("<br>".join(lines) + f"<br><br><i>{escape(t('ms_sector'))}</i><br>" + "<br>".join(sec))
        self.lay.addWidget(card(t("ms_sources"), src))
        self.lay.addStretch(1)

        self.search.textChanged.connect(self._fill)
        self.group.currentIndexChanged.connect(self._fill)
        self.relevant.toggled.connect(self._fill)
        self.table.itemSelectionChanged.connect(self._show)
        self._fill()

    # ------------------------------------------------------------------ data
    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        self._fill()

    def _kinds(self) -> set:
        return {s.kind for s in self.plant.subsystems} if self.plant else set()

    def _fill(self, *_a) -> None:
        t = self.t
        grp = self.group.currentData() or None
        rows = M.search(self.search.text(), group=grp)
        if self.relevant.isChecked() and self.plant is not None:
            kinds = self._kinds()
            rows = [m for m in rows if "plant" in m.targets or kinds.intersection(m.targets)]
        self._rows = rows
        cur = self._selected_id()
        self.table.setRowCount(len(rows))
        for r, m in enumerate(rows):
            put(self.table, r, 0, str(m.id), number=True)
            put(self.table, r, 1, m.name(t.lang))
            put(self.table, r, 2, M.range_text(m.use, m, t.lang), number=True)
            put(self.table, r, 3, M.range_text(m.fresh, m, t.lang, fresh=True), number=True)
            put(self.table, r, 4, M.capex_text(m, t.lang))
            est = M.estimates(self.plant, m) if self.plant else []
            put(self.table, r, 5, " | ".join(_fmt_range(e.low, e.high) for e in est[:2]) if est else "—", number=bool(est))
            if m.id == cur:
                self.table.setCurrentCell(r, 0)
                self.table.selectRow(r)
        self.count.setText(t("ms_count", n=len(rows)))
        if cur is None or all(m.id != cur for m in rows):
            self._show()

    def _selected_id(self) -> Optional[int]:
        rows = self.table.selectionModel().selectedRows()
        r = rows[0].row() if rows else self.table.currentRow() if self.table.selectedItems() else -1
        if 0 <= r < len(self._rows):
            return self._rows[r].id
        return None

    def selected(self) -> Optional[M.Measure]:
        mid = self._selected_id()
        return M.get(mid) if mid is not None else None

    def select(self, measure_id: int) -> None:
        for r, m in enumerate(self._rows):
            if m.id == measure_id:
                self.table.setCurrentCell(r, 0)
                self.table.selectRow(r)
                self._show()
                return

    def _show(self) -> None:
        t = self.t
        m = self.selected()
        self.target.clear()
        self.add.setEnabled(m is not None)
        self.status.setText("")
        if m is None:
            self.detail.setText(escape(t("ms_pick")))
            return
        lang = t.lang
        navy, sub = COL["navy"], COL["sub"]
        h = [f"<span style='font-size:15px;font-weight:700;color:{navy}'>{m.id}. {escape(m.name(lang))}</span>",
             f"<span style='color:{sub}'>{escape(M.group_name(m.group, lang))}</span>"]
        prio = M.group_priority(m.group, lang)
        if prio:
            h.append(f"<span style='color:{sub}'>{escape(prio)}</span>")
        h.append(f"<b>{escape(t('ms_use'))}:</b> {escape(M.range_text(m.use, m, lang))} &nbsp;&nbsp; "
                 f"<b>{escape(t('ms_fresh'))}:</b> {escape(M.range_text(m.fresh, m, lang, fresh=True))}")
        cap = f"<b>{escape(t('ms_capex'))}:</b> {escape(M.capex_text(m, lang))}"
        if m.driver(lang):
            cap += f" &nbsp;&nbsp; <b>{escape(t('ms_cost_driver'))}:</b> {escape(m.driver(lang))}"
        h.append(cap)
        kinds = [t("ms_plant_wide") if x == "plant" else t("kind_" + x) for x in m.targets]
        h.append(f"<b>{escape(t('ms_applies'))}:</b> {escape(' ، '.join(kinds) if lang == 'fa' else ', '.join(kinds))}")
        if m.note(lang):
            h.append(escape(m.note(lang)))
        for c in m.cautions(lang):
            h.append(f"<span style='color:#9C4A00'>⚠ {escape(c)}</span>")
        if m.id in M.EXACT_CALCULATOR:
            h.append(f"<span style='color:{COL['green']}'>✔ {escape(t('ms_exact'))}</span>")
        if not m.estimable:
            h.append(escape(t("ms_no_number")))
        for e in (M.estimates(self.plant, m) if self.plant else []):
            tgt = e.target or t("ms_plant_wide")
            h.append(escape(t("ms_estimate_for", target=tgt, lo=_fmt(e.low), hi=_fmt(e.high))))
        self.detail.setText("<br>".join(h))
        # targets the measure can be applied to
        if self.plant is not None:
            es = M._subs_for(self.plant, m)
            for name, _vol in es:
                self.target.addItem(name or t("ms_plant_wide"), name)
        if self.target.count() == 0:
            self.target.addItem(t("ms_plant_wide"), "")

    def _add(self) -> None:
        m = self.selected()
        if m is None:
            return
        self.plan_requested.emit(m.id, self.target.currentData() or "")
        self.status.setText(self.t("ms_added"))


class PlanTab(_Scroll):
    """Selected measures with editable inputs, combined without double counting."""

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False

        self.msg = _message_label()
        self.lay.addWidget(self.msg)
        self.c_save = StatCard(t("pl_saving"), COL["blue"])
        self.c_value = StatCard(t("pl_value"), COL["green"])
        self.c_capex = StatCard(t("pl_capex"), COL["navy"])
        self.c_pay = StatCard(t("pl_payback"), COL["orange"])
        self.lay.addLayout(stat_row(self.c_save, self.c_value, self.c_capex, self.c_pay))

        heads = [t("ms_measure"), t("pl_target"), t("pl_pct"), t("pl_capex"), t("pl_opex"), t("pl_life"), t("pl_rate")]
        self.inputs = QTableWidget(0, len(heads))
        self.inputs.setHorizontalHeaderLabels(heads)
        from PySide6.QtWidgets import QHeaderView
        hh = self.inputs.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.inputs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inputs.setAlternatingRowColors(True)
        self.inputs.setShowGrid(False)
        self.inputs.verticalHeader().setVisible(False)
        self.inputs.verticalHeader().setDefaultSectionSize(44)
        self.inputs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.inputs.setMinimumHeight(260)
        for c, w in ((1, 150), (2, 100), (3, 130), (4, 130), (5, 90), (6, 100)):
            self.inputs.setColumnWidth(c, w)
        rm = button(t("pl_remove"), "danger", self._remove)
        clr = button(t("pl_clear"), "", self._clear)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(rm)
        rl.addWidget(clr)
        rl.addStretch(1)
        self.lay.addWidget(card(t("pl_items"), self.inputs, row, note=t("pl_note")))

        self.warn = QLabel()
        self.warn.setObjectName("warnbox")
        self.warn.setWordWrap(True)
        self.warn.setVisible(False)
        self.lay.addWidget(self.warn)

        rh = [t("ms_measure"), t("pl_saved"), t("pl_val_col"), t("pl_i1"), t("pl_i2"), t("pl_lcc"), t("pl_pay"), t("pl_flags")]
        self.results = make_table(rh)
        self.results.setMinimumHeight(260)
        self.lay.addWidget(card(t("pl_results"), self.results))
        self.lay.addStretch(1)

    # ------------------------------------------------------------------ data
    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        self._build_inputs()
        self._recalc()

    def _targets(self) -> List[str]:
        return [""] + [s.name for s in (self.plant.subsystems if self.plant else [])]

    def _build_inputs(self) -> None:
        t = self.t
        self._loading = True
        plan = self.plant.plan if self.plant else []
        self.inputs.setRowCount(len(plan))
        targets = self._targets()
        for r, it in enumerate(plan):
            m = M.get(it.measure_id)
            put(self.inputs, r, 0, f"{m.id}. {m.name(t.lang)}")
            combo = QComboBox()
            for name in targets:
                combo.addItem(name or t("ms_plant_wide"), name)
            if it.target not in targets:
                combo.addItem(it.target, it.target)
            combo.setCurrentIndex(max(0, combo.findData(it.target)))
            combo.currentIndexChanged.connect(lambda _i, it=it, cb=combo: self._set(it, "target", cb.currentData()))
            self.inputs.setCellWidget(r, 1, combo)
            for col, attr, mx, dec in ((2, "saving_pct", 100, 2), (3, "capex", 1e13, 0), (4, "opex", 1e13, 0),
                                       (5, "life_years", 100, 0), (6, "rate_pct", 100, 1)):
                sp = dspin(maximum=mx, decimals=dec, step=1 if col != 3 else 1000)
                sp.setValue(getattr(it, attr))
                sp.valueChanged.connect(lambda v, it=it, a=attr: self._set(it, a, v))
                self.inputs.setCellWidget(r, col, sp)
        self._loading = False

    def _set(self, it, attr: str, value) -> None:
        if self._loading:
            return
        setattr(it, attr, value)
        self._recalc()

    def add(self, measure_id: int, target: str) -> None:
        if self.plant is None:
            return
        m = M.get(measure_id)
        if any(i.measure_id == measure_id and i.target == target for i in self.plant.plan):
            return
        self.plant.plan.append(M.new_plan_item(self.plant, m, target))
        self.refresh(self.plant)

    def _remove(self) -> None:
        r = self.inputs.currentRow()
        if self.plant is not None and 0 <= r < len(self.plant.plan):
            del self.plant.plan[r]
            self.refresh(self.plant)

    def _clear(self) -> None:
        if self.plant is not None:
            self.plant.plan.clear()
            self.refresh(self.plant)

    def _recalc(self) -> None:
        t = self.t
        plant = self.plant
        self.results.setRowCount(0)
        if plant is None or not plant.plan:
            self.msg.setText(t("pl_empty"))
            for c in (self.c_save, self.c_value, self.c_capex, self.c_pay):
                c.set("—")
            self.warn.setVisible(False)
            return
        self.msg.setText("")
        res = M.evaluate_plan(plant)
        cur = plant.currency
        self.c_save.set(f"{_fmt(res.saving)} m³", f"{res.saving_pct:.1f}%")
        self.c_value.set(_fmt(res.annual_value), cur + (" / سال" if t.lang == "fa" else " / year"))
        self.c_capex.set(_fmt(res.capex), f"{t('pl_opex')}: {_fmt(res.opex)}")
        self.c_pay.set("—" if res.payback is None else f"{res.payback:.1f}",
                       t("pl_years") + ("" if res.lcc is None else f" · LCC {res.lcc:.3g} {cur}/m³"))
        warns = []
        for code in res.warnings:
            if code.startswith("overlap:"):
                tgt = code.split(":", 1)[1] or t("ms_plant_wide")
                warns.append("⚠ " + t("pl_w_overlap", target=tgt))
        self.warn.setText("\n".join(warns))
        self.warn.setVisible(bool(warns))
        self.results.setRowCount(len(res.lines))

        def num(v, d=2):
            return "—" if v is None else _fmt(v, d)
        for r, ln in enumerate(res.lines):
            put(self.results, r, 0, f"{ln.measure.id}. {ln.measure.name(t.lang)}")
            put(self.results, r, 1, _fmt(ln.saving), number=True)
            put(self.results, r, 2, _fmt(ln.annual_value), number=True)
            put(self.results, r, 3, num(ln.i1, 0), number=True)
            put(self.results, r, 4, num(ln.i2, 3), number=True)
            put(self.results, r, 5, num(ln.lcc, 3), number=True)
            put(self.results, r, 6, "—" if ln.payback is None else f"{ln.payback:.1f}", number=True)
            put(self.results, r, 7, " ، ".join(t("pl_f_" + f) for f in ln.flags) if t.lang == "fa"
                else ", ".join(t("pl_f_" + f) for f in ln.flags))
