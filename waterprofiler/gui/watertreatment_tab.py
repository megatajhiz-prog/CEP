"""Water treatment page: pre-treatment, demineralised-water units and the cost of the treated water along the chain."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from .. import watertreatment as WT
from ..i18n import Translator
from ..model import Plant
from .tabs import _Scroll, _fmt, _message_label, _pct, make_table, put, stat_row
from .theme import COL
from .widgets import Sections, StatCard, card, dspin

FIELDS = [
    ("capacity", "wt_p_capacity", 0, 1e9), ("tds_in", "wt_p_tds_in", 0, 1e6), ("tds_out", "wt_p_tds_out", 0, 1e6),
    ("opex_m3", "wt_p_opex", 3, 1e6), ("kwh_m3", "wt_p_kwh", 3, 1e4), ("capex", "wt_p_capex", 0, 1e12),
    ("life", "wt_p_life", 0, 100), ("min_yield", "wt_p_minyield", 0, 100),
]


def _money(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:,.2f}"


class WaterTreatmentTab(_Scroll):
    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False
        self._names: List[str] = []
        self.lay.addWidget(_message_label())

        self.c_raw = StatCard(t("wt_raw"), COL["blue"])
        self.c_del = StatCard(t("wt_delivered"), COL["green"])
        self.c_yield = StatCard(t("wt_yield"), COL["orange"])
        self.lay.addLayout(stat_row(self.c_raw, self.c_del, self.c_yield))
        self.c_waste = StatCard(t("wt_waste"), COL["red"])
        self.c_share = StatCard(t("wt_waste_share"), COL["orange"])
        self.c_cost = StatCard(t("wt_cost"), COL["navy"])
        self.lay.addLayout(stat_row(self.c_waste, self.c_share, self.c_cost))

        self.warn = QLabel()
        self.warn.setObjectName("warnbox")
        self.warn.setWordWrap(True)
        self.warn.setVisible(False)
        self.lay.addWidget(self.warn)

        self.empty = QLabel(t("wt_empty"))
        self.empty.setObjectName("cardnote")
        self.empty.setWordWrap(True)
        self.lay.addWidget(card(t("wt_howto"), self.empty))

        self.sections = Sections()
        p_unit = self.sections.page(t("wt_sec_units"))
        p_cost = self.sections.page(t("wt_sec_cost"))
        p_cons = self.sections.page(t("wt_sec_consumers"))
        self.lay.addWidget(self.sections)

        self.units = make_table([t("subsystem"), t("wt_raw_in"), t("wt_inflow"), t("wt_to_users"), t("wt_to_next"),
                                 t("wt_waste_m3"), t("wt_sludge"), t("wt_loss"), t("wt_closure"), t("wt_yield_col"),
                                 t("wt_util")])
        p_unit.addWidget(card(t("wt_units"), self.units, note=t("wt_units_note")))

        self.pick = QComboBox()
        self.pick.currentIndexChanged.connect(self._load_form)
        self.spins: Dict[str, object] = {}
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.addRow(t("subsystem"), self.pick)
        for key, lab, dec, mx in FIELDS:
            sp = dspin(mx, dec)
            sp.valueChanged.connect(lambda _v=0.0, k=key: self._edited(k))
            self.spins[key] = sp
            form.addRow(t(lab), sp)
        fw = QWidget()
        fw.setLayout(form)
        p_unit.addWidget(card(t("wt_data"), fw, note=t("wt_data_note")))

        self.cost = make_table([t("subsystem"), t("wt_tds_rem"), t("wt_own_cost"), t("wt_waste_fee"), t("wt_energy"),
                                t("wt_cost_m3")])
        self.cost_note = QLabel()
        self.cost_note.setObjectName("cardnote")
        self.cost_note.setWordWrap(True)
        p_cost.addWidget(card(t("wt_costs"), self.cost, self.cost_note, note=t("wt_costs_note")))

        self.cons = make_table([t("subsystem"), t("wt_received"), t("wt_tds"), t("wt_need"), t("wt_ok"), t("wt_cost_m3"),
                                t("wt_vs_fresh")])
        p_cons.addWidget(card(t("wt_consumers"), self.cons, note=t("wt_consumers_note")))
        self.sections.finish()
        self.lay.addStretch(1)

    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        t = self.t
        r = WT.analyse_water_treatment(plant)
        self.empty.parent().setVisible(not r.has_system)
        names = [x.name for x in plant.units() if WT.is_unit(x)]
        if names != self._names:
            self._loading = True
            cur = self.pick.currentText()
            self.pick.clear()
            self.pick.addItems(names)
            if cur in names:
                self.pick.setCurrentText(cur)
            self._names = names
            self._loading = False
        self._load_form()
        self.pick.parent().setEnabled(bool(names))

        self.c_raw.set(_fmt(r.raw_in) + " m³", t("wt_raw_hint"))
        self.c_del.set(_fmt(r.delivered) + " m³", t("wt_delivered_hint"))
        self.c_yield.set(_pct(r.overall_yield), t("wt_yield_hint"))
        self.c_waste.set(_fmt(r.waste) + " m³", t("wt_waste_hint"))
        self.c_share.set(_pct(r.waste_share_of_intake), t("wt_share_hint"))
        self.c_cost.set(_fmt(r.total_cost) + f" {plant.currency}/{t('ww_year')}", t("wt_cost_hint"))
        self.warn.setText("\n".join("• " + WT.message(w, t.lang) for w in r.warnings))
        self.warn.setVisible(bool(r.warnings))

        tb = self.units
        tb.setRowCount(len(r.units))
        for i, u in enumerate(r.units):
            put(tb, i, 0, u.name)
            for j, v in enumerate((u.raw_in, u.inflow, u.to_users, u.to_next, u.waste, u.sludge, u.losses), 1):
                put(tb, i, j, _fmt(v), True)
            put(tb, i, 8, f"{_fmt(u.closure)} ({u.closure_pct:.1f}%)", True)
            put(tb, i, 9, _pct(u.yield_), True)
            put(tb, i, 10, _pct(u.utilisation), True)

        tb = self.cost
        tb.setRowCount(len(r.units))
        for i, u in enumerate(r.units):
            put(tb, i, 0, u.name)
            put(tb, i, 1, _pct(u.tds_removal), True)
            put(tb, i, 2, _fmt(u.treatment_cost), True)
            put(tb, i, 3, _fmt(u.waste_fee), True)
            put(tb, i, 4, _fmt(u.energy_kwh), True)
            put(tb, i, 5, _money(u.cost_per_m3), True)
        self.cost_note.setText(t("wt_cost_text"))

        tb = self.cons
        tb.setRowCount(len(r.consumers))
        for i, c in enumerate(r.consumers):
            put(tb, i, 0, c.name)
            put(tb, i, 1, _fmt(c.volume), True)
            put(tb, i, 2, "—" if c.tds is None else f"{c.tds:,.0f}", True)
            put(tb, i, 3, "—" if c.need is None else f"≤ {c.need:,.0f}", True)
            put(tb, i, 4, "—" if c.suitable is None else t("yes") if c.suitable else t("no"))
            put(tb, i, 5, _money(c.cost_per_m3), True)
            put(tb, i, 6, "—" if c.cost_per_m3 is None or not c.fresh_price else f"{c.cost_per_m3 / c.fresh_price:.1f}×", True)
        for tbl in (self.units, self.cost, self.cons):
            tbl.resizeRowsToContents()
            h = tbl.horizontalHeader().height() + 2 * tbl.frameWidth() + 6
            h += sum(tbl.rowHeight(k) for k in range(tbl.rowCount()))
            tbl.setFixedHeight(max(h, 60))

    def _unit(self):
        name = self.pick.currentText()
        return self.plant.node(name) if (self.plant and name) else None

    def _load_form(self, *_a) -> None:
        if self._loading:
            return
        u = self._unit()
        self._loading = True
        p = (u.params if u is not None else {}) or {}
        for key, sp in self.spins.items():
            sp.setValue(float(p.get(key, 0.0) or 0.0))
        self._loading = False

    def _edited(self, key: str) -> None:
        if self._loading:
            return
        u = self._unit()
        if u is None:
            return
        val = float(self.spins[key].value())
        if val:
            u.params[key] = val
        else:
            u.params.pop(key, None)
        self.refresh(self.plant)
