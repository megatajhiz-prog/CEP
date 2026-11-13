"""Wastewater page: collection, treatment, quality, reuse and the extra reuse potential of the plant."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from .. import wastewater as WW
from ..i18n import Translator
from ..model import Plant
from .tabs import _Scroll, _fmt, _message_label, _pct, make_table, put, stat_row
from .theme import COL
from .widgets import StatCard, card, dspin

# parameter -> (label key, decimals, maximum)
FIELDS = [
    ("capacity", "ww_p_capacity", 0, 1e9), ("opex_m3", "ww_p_opex", 3, 1e6), ("capex", "ww_p_capex", 0, 1e12),
    ("life", "ww_p_life", 0, 100),
    ("cod_in", "ww_p_cod_in", 1, 1e6), ("cod_out", "ww_p_cod_out", 1, 1e6),
    ("tds_in", "ww_p_tds_in", 0, 1e6), ("tds_out", "ww_p_tds_out", 0, 1e6),
    ("cod_limit", "ww_p_cod_limit", 1, 1e6), ("tds_limit", "ww_p_tds_limit", 0, 1e6),
]


def _money(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:,.2f}"


class WastewaterTab(_Scroll):
    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False
        self.msg = _message_label()
        self.lay.addWidget(self.msg)

        self.c_gen = StatCard(t("ww_generated"), COL["blue"])
        self.c_col = StatCard(t("ww_collection"), COL["orange"])
        self.c_reuse = StatCard(t("ww_reuse_vol"), COL["green"])
        self.lay.addLayout(stat_row(self.c_gen, self.c_col, self.c_reuse))
        self.c_rate = StatCard(t("ww_reuse_rate"), COL["green"])
        self.c_fresh = StatCard(t("ww_fresh_saving"), COL["blue"])
        self.c_net = StatCard(t("ww_net"), COL["navy"])
        self.lay.addLayout(stat_row(self.c_rate, self.c_fresh, self.c_net))

        self.warn = QLabel()
        self.warn.setObjectName("warnbox")
        self.warn.setWordWrap(True)
        self.warn.setVisible(False)
        self.lay.addWidget(self.warn)

        self.empty = QLabel(t("ww_empty"))
        self.empty.setObjectName("cardnote")
        self.empty.setWordWrap(True)
        self.lay.addWidget(card(t("ww_howto"), self.empty))

        self.streams = make_table([t("subsystem"), t("ww_class"), t("ww_gen"), t("ww_to_tr"), t("ww_cascade"),
                                   t("ww_untreated"), t("ww_coll_rate")])
        self.lay.addWidget(card(t("ww_streams"), self.streams, note=t("ww_streams_note")))

        self.units = make_table([t("subsystem"), t("ww_inflow"), t("ww_to_users"), t("ww_to_next"), t("ww_effluent"),
                                 t("ww_sludge"), t("ww_loss"), t("ww_closure"), t("ww_recovery"), t("ww_util")])
        self.lay.addWidget(card(t("ww_units"), self.units, note=t("ww_units_note")))

        # data of one treatment unit
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
        self.required = QCheckBox(t("ww_p_required"))
        self.required.toggled.connect(lambda _c=False: self._edited("required"))
        form.addRow("", self.required)
        fw = QWidget()
        fw.setLayout(form)
        self.lay.addWidget(card(t("ww_data"), fw, note=t("ww_data_note")))

        self.quality = make_table([t("subsystem"), t("ww_cod_rem"), t("ww_tds_rem"), t("ww_cod_kg"), t("ww_cod_out_kg"),
                                   t("ww_comply")])
        self.lay.addWidget(card(t("ww_quality"), self.quality, note=t("ww_quality_note")))

        self.econ = make_table([t("subsystem"), t("ww_benefit"), t("ww_opex"), t("ww_net"), t("ww_rec_cost"), t("ww_payback")])
        self.econ_note = QLabel()
        self.econ_note.setObjectName("cardnote")
        self.econ_note.setWordWrap(True)
        self.lay.addWidget(card(t("ww_econ"), self.econ, self.econ_note, note=t("ww_econ_note")))

        self.users = make_table([t("subsystem"), t("ww_received"), t("ww_fresh_demand"), t("ww_suitable"),
                                 t("ww_potential"), t("ww_remark")])
        self.pot = QLabel()
        self.pot.setObjectName("cardnote")
        self.pot.setWordWrap(True)
        self.lay.addWidget(card(t("ww_users"), self.users, self.pot, note=t("ww_users_note")))
        self.lay.addStretch(1)
        self._names: List[str] = []

    # ------------------------------------------------------------------ data
    def refresh(self, plant: Plant) -> None:
        self.plant = plant
        t = self.t
        r = WW.analyse_wastewater(plant)
        self._report = r
        self.empty.parent().setVisible(not r.has_system)
        names = [x.name for x in plant.units() if WW.is_treatment(x)]
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

        self.c_gen.set(_fmt(r.generated) + " m³", t("ww_generated_hint"))
        self.c_col.set(_pct(r.collection_rate), f"{_fmt(r.collected)} m³")
        self.c_reuse.set(_fmt(r.reuse_treated + r.direct_reuse) + " m³", t("ww_reuse_hint"))
        self.c_rate.set(_pct(r.reuse_rate), t("ww_reuse_rate_hint"))
        self.c_fresh.set(_pct(r.fresh_saving_pct), t("ww_fresh_hint"))
        self.c_net.set(_fmt(r.net_benefit) + f" {plant.currency}/{t('ww_year')}", t("ww_net_hint"))

        self.warn.setText("\n".join("• " + WW.message(w, t.lang) for w in r.warnings))
        self.warn.setVisible(bool(r.warnings))

        cls = {c: t("ww_cls_" + c) for c in ("domestic", "industrial", "blowdown", "other")}
        tb = self.streams
        tb.setRowCount(len(r.streams))
        for i, s in enumerate(r.streams):
            put(tb, i, 0, s.name)
            put(tb, i, 1, cls.get(s.cls, s.cls))
            for j, v in enumerate((s.generated, s.to_treatment, s.direct_reuse, s.to_outlet), 2):
                put(tb, i, j, _fmt(v), True)
            put(tb, i, 6, _pct(s.collection_rate), True)

        tb = self.units
        tb.setRowCount(len(r.treatments))
        for i, u in enumerate(r.treatments):
            put(tb, i, 0, u.name)
            for j, v in enumerate((u.inflow, u.reuse_to_users, u.to_next_stage, u.effluent, u.sludge, u.evaporation), 1):
                put(tb, i, j, _fmt(v), True)
            put(tb, i, 7, f"{_fmt(u.closure)} ({u.closure_pct:.1f}%)", True)
            put(tb, i, 8, _pct(u.recovery), True)
            put(tb, i, 9, _pct(u.utilisation), True)

        tb = self.quality
        tb.setRowCount(len(r.treatments))
        for i, u in enumerate(r.treatments):
            put(tb, i, 0, u.name)
            put(tb, i, 1, _pct(u.cod_removal), True)
            put(tb, i, 2, _pct(u.tds_removal), True)
            put(tb, i, 3, _fmt(u.cod_load_removed), True)
            put(tb, i, 4, _fmt(u.cod_load_discharged), True)
            put(tb, i, 5, "—" if u.compliant is None else t("yes") if u.compliant else t("no"))

        tb = self.econ
        tb.setRowCount(len(r.treatments))
        for i, u in enumerate(r.treatments):
            put(tb, i, 0, u.name + (f" ({t('ww_required_tag')})" if u.required else ""))
            put(tb, i, 1, _fmt(u.benefit), True)
            put(tb, i, 2, _fmt(0.0 if u.required else u.opex), True)
            put(tb, i, 3, _fmt(u.net_benefit), True)
            put(tb, i, 4, _money(u.reclaimed_cost), True)
            put(tb, i, 5, "—" if u.payback_years is None else f"{u.payback_years:.1f}", True)
        self.econ_note.setText(t("ww_prices", fresh=_money(r.fresh_price), disch=_money(r.discharge_price),
                                 cur=plant.currency))

        tb = self.users
        tb.setRowCount(len(r.users))
        remark = {"no_limit": t("ww_rm_nolimit"), "no_quality": t("ww_rm_noq"), "polish": t("ww_rm_polish"), "": ""}
        for i, u in enumerate(r.users):
            put(tb, i, 0, u.name)
            put(tb, i, 1, _fmt(u.reclaimed), True)
            put(tb, i, 2, _fmt(u.fresh_demand), True)
            put(tb, i, 3, "—" if u.allowed is None else t("yes") if u.allowed else t("no"))
            put(tb, i, 4, _fmt(u.potential), True)
            put(tb, i, 5, remark.get(u.note, u.note))
        self.pot.setText(t("ww_potential_text", vol=_fmt(r.potential_volume), val=_fmt(r.potential_benefit),
                           cur=plant.currency, surplus=_fmt(r.surplus_effluent)) if r.has_system else "")
        for tbl in (self.streams, self.units, self.quality, self.econ, self.users):
            tbl.resizeRowsToContents()
            h = tbl.horizontalHeader().height() + 2 * tbl.frameWidth() + 6
            h += sum(tbl.rowHeight(k) for k in range(tbl.rowCount()))
            tbl.setFixedHeight(max(h, 60))

    # ------------------------------------------------------------------ one treatment unit's data
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
        self.required.setChecked(bool(p.get("required")))
        self._loading = False

    def _edited(self, key: str) -> None:
        if self._loading:
            return
        u = self._unit()
        if u is None:
            return
        if key == "required":
            val = 1.0 if self.required.isChecked() else 0.0
        else:
            val = float(self.spins[key].value())
        if val:
            u.params[key] = val
        else:
            u.params.pop(key, None)
        self.refresh(self.plant)
