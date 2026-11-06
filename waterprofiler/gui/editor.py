"""Subsystem editor panel and plant-definition panel."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..i18n import Translator
from ..model import Outlet, Plant, Pump, Source, Subsystem, Treatment
from ..numparse import fmt_float, parse_float
from .widgets import DataTable, button, card, dspin, table_box

KINDS = ["process", "cooling_tower", "boiler", "sanitary", "irrigation", "other"]


class OptNum(QLineEdit):
    """Optional number: empty means 'not given'. Accepts Persian digits."""

    def get(self) -> Optional[float]:
        return parse_float(self.text())

    def set(self, v: Optional[float]) -> None:
        self.setText(fmt_float(v))


def _sum_dict(rows: List[list]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for name, val in rows:
        if name and val:
            out[name] = out.get(name, 0.0) + float(val)
    return out


class PlantPanel(QScrollArea):
    """Water sources, outlets and treatments (part of the industrial-complex page)."""

    changed = Signal()

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(26, 22, 26, 26)
        outer.setSpacing(16)
        self.sources = DataTable([t("col_name"), t("col_unit_cost"), t("col_metered"), t("col_alternative")],
                                 ["text", "num", "num", "bool"])
        self.outlets = DataTable([t("col_name"), t("col_unit_cost"), t("col_metered")], ["text", "num", "num"])
        self.treatments = DataTable([t("col_name"), t("col_unit_cost"), t("col_wastewater")], ["text", "num", "bool"])
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(table_box(t("sources"), self.sources, t("add"), t("remove"), lambda: ["", 0.0, None, False]))
        row.addWidget(table_box(t("outlets"), self.outlets, t("add"), t("remove"), lambda: ["", 0.0, None]))
        outer.addLayout(row, 1)
        outer.addWidget(table_box(t("treatments"), self.treatments, t("add"), t("remove"), lambda: ["", 0.0, False]), 1)

        for tb in (self.sources, self.outlets, self.treatments):
            tb.changed.connect(self.changed)

    def load(self, p: Plant) -> None:
        self.blockSignals(True)
        self.sources.set_rows([[s.name, s.unit_cost, s.metered_m3, s.alternative] for s in p.sources])
        self.outlets.set_rows([[o.name, o.unit_cost, o.metered_m3] for o in p.outlets])
        self.treatments.set_rows([[x.name, x.unit_cost, x.wastewater] for x in p.treatments])
        self.blockSignals(False)

    def store(self, p: Plant) -> None:
        seen = set()
        p.sources, p.outlets, p.treatments = [], [], []
        for n, c, m, alt in self.sources.rows():
            if n and n not in seen:
                seen.add(n)
                p.sources.append(Source(n, c or 0.0, m, bool(alt)))
        seen = set()
        for n, c, m in self.outlets.rows():
            if n and n not in seen:
                seen.add(n)
                p.outlets.append(Outlet(n, c or 0.0, m))
        seen = set()
        for n, c, ww in self.treatments.rows():
            if n and n not in seen:
                seen.add(n)
                p.treatments.append(Treatment(n, c or 0.0, bool(ww)))


class SubsystemEditor(QScrollArea):
    """Edits one Subsystem. Call set_catalog() then load(); store() writes back."""

    estimate_requested = Signal()

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.setWidgetResizable(True)
        self.catalog = ([], [], [])   # sources, outlets, treatments (names)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(8, 4, 8, 18)
        lay.setSpacing(16)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.name = QLineEdit()
        self.kind = QComboBox()
        for k in KINDS:
            self.kind.addItem(t("kind_" + k), k)
        form.addRow(t("col_name"), self.name)
        form.addRow(t("kind"), self.kind)
        self.est_btn = button(t("estimate"), "primary")
        self.est_btn.clicked.connect(self.estimate_requested)
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(24)
        hl.addLayout(form, 1)
        hl.addWidget(self.est_btn, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addWidget(card(t("sub_basic"), head))

        self.intake = DataTable([t("sources"), t("amount_m3")], ["combo", "num"])
        self.discharge = DataTable([t("outlets"), t("amount_m3")], ["combo", "num"])
        row = QHBoxLayout()
        row.addWidget(table_box(t("intake"), self.intake, t("add"), t("remove"), lambda: ["", None]))
        row.addWidget(table_box(t("discharge"), self.discharge, t("add"), t("remove"), lambda: ["", None]))
        lay.addLayout(row)

        flows = QGroupBox(t("other_flows"))
        ff = QFormLayout(flows)
        self.recirc = dspin(decimals=2)
        self.from_other = dspin(decimals=2)
        self.to_other = dspin(decimals=2)
        self.product = dspin(decimals=2)
        self.evap = dspin(decimals=2)
        for label, w in (("recirculated", self.recirc), ("from_other", self.from_other), ("to_other", self.to_other),
                         ("product", self.product), ("evaporation", self.evap)):
            ff.addRow(t(label), w)
        lay.addWidget(flows)

        self.wtreat = DataTable([t("treatments"), t("fraction")], ["combo", "num"])
        self.wwtreat = DataTable([t("treatments"), t("fraction")], ["combo", "num"])
        row2 = QHBoxLayout()
        row2.addWidget(table_box(t("water_treat"), self.wtreat, t("add"), t("remove"), lambda: ["", 1.0]))
        row2.addWidget(table_box(t("ww_treat"), self.wwtreat, t("add"), t("remove"), lambda: ["", 1.0]))
        lay.addLayout(row2)

        self.pumps = DataTable(
            [t("col_name"), t("pump_hours"), t("pump_kw"), t("pump_eff"), t("pump_load"),
             t("pump_volts"), t("pump_amps"), t("pump_pf"), t("pump_phases")],
            ["text", "num", "num", "num", "num", "num", "num", "num", "num"])
        lay.addWidget(table_box(t("pumps"), self.pumps, t("add"), t("remove"),
                                lambda: ["", 0.0, None, 0.9, 1.0, None, None, 0.85, 3.0]))
        hint = QLabel(t("pump_hint"))
        hint.setObjectName("cardnote")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        temps = QFormLayout()
        self.t_in = OptNum()
        self.t_ww = OptNum()
        temps.addRow(t("t_in"), self.t_in)
        temps.addRow(t("t_ww"), self.t_ww)
        tw = QWidget()
        tw.setLayout(temps)
        lay.addWidget(card(t("temps"), tw))
        lay.addStretch(1)

    # ---------------------------------------------------------------- catalog
    def set_catalog(self, sources: List[str], outlets: List[str], treatments: List[str]) -> None:
        self.catalog = (sources, outlets, treatments)
        self.intake.combo_items = {0: [""] + list(sources)}
        self.discharge.combo_items = {0: [""] + list(outlets)}
        self.wtreat.combo_items = {0: [""] + list(treatments)}
        self.wwtreat.combo_items = {0: [""] + list(treatments)}

    # ------------------------------------------------------------ model <-> UI
    def load(self, s: Subsystem) -> None:
        self.name.setText(s.name)
        i = self.kind.findData(s.kind)
        self.kind.setCurrentIndex(i if i >= 0 else KINDS.index("other"))
        self.intake.set_rows([[k, v] for k, v in s.intake.items()])
        self.discharge.set_rows([[k, v] for k, v in s.discharge.items()])
        self.recirc.setValue(s.recirculated)
        self.from_other.setValue(s.from_other)
        self.to_other.setValue(s.to_other)
        self.product.setValue(s.product)
        self.evap.setValue(s.evaporation)
        self.wtreat.set_rows([[k, v] for k, v in s.water_treatments.items()])
        self.wwtreat.set_rows([[k, v] for k, v in s.wastewater_treatments.items()])
        self.pumps.set_rows([[p.name, p.hours_per_year, p.power_kw if p.power_kw is not None else (
            p.power_hp * 0.746 if p.power_hp is not None else None), p.efficiency, p.load_fraction,
            p.volts, p.amps, p.power_factor, float(p.phases)] for p in s.pumps])
        self.t_in.set(s.t_intake_c)
        self.t_ww.set(s.t_wastewater_c)

    def store(self, s: Subsystem) -> None:
        s.name = self.name.text().strip() or s.name
        s.kind = self.kind.currentData() or "other"
        s.intake = _sum_dict(self.intake.rows())
        s.discharge = _sum_dict(self.discharge.rows())
        s.recirculated = self.recirc.value()
        s.from_other = self.from_other.value()
        s.to_other = self.to_other.value()
        s.product = self.product.value()
        s.evaporation = self.evap.value()
        s.water_treatments = _sum_dict(self.wtreat.rows())
        s.wastewater_treatments = _sum_dict(self.wwtreat.rows())
        pumps = []
        for name, hours, kw, eff, load, volts, amps, pf, phases in self.pumps.rows():
            if not (name or hours or kw or volts):
                continue
            pumps.append(Pump(
                name=name or "pump", hours_per_year=hours or 0.0, power_kw=kw, power_hp=None,
                efficiency=eff if eff else 0.9, load_fraction=load if load is not None else 1.0,
                volts=volts, amps=amps, power_factor=pf if pf else 0.85,
                phases=1 if phases == 1 else 3))
        s.pumps = pumps
        s.t_intake_c = self.t_in.get()
        s.t_wastewater_c = self.t_ww.get()
