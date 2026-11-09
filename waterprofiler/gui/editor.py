"""Subsystem editor panel and plant-definition panel."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QVBoxLayout, QWidget,
)

from .. import timeseries as TS
from ..i18n import Translator
from ..model import Outlet, Plant, Pump, Source, Subsystem, Treatment
from ..numparse import fmt_float, parse_float
from .trend import TrendPeek, with_data
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
    """Plant name, unit prices, sources, outlets, treatments."""

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
        self.name = QLineEdit()
        self.currency = QLineEdit()
        self.production = dspin(decimals=2)
        self.prod_unit = QLineEdit()
        self.elec = dspin(decimals=6, step=0.01)
        self.fuel = dspin(decimals=6, step=0.01)
        self.heat_eff = dspin(maximum=1.0, decimals=3, step=0.01)
        left, right = QFormLayout(), QFormLayout()
        for form in (left, right):
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(10)
        for label, w in (("plant_name", self.name), ("currency", self.currency), ("production", self.production),
                         ("production_unit", self.prod_unit)):
            left.addRow(t(label), w)
        for label, w in (("elec_cost", self.elec), ("fuel_cost", self.fuel), ("heat_eff", self.heat_eff)):
            right.addRow(t(label), w)
        info = QWidget()
        il = QHBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(40)
        il.addLayout(left, 1)
        il.addLayout(right, 1)
        self.peek_prod = TrendPeek(t, lambda p: with_data(p, ["total:production"] + [f"production:{x.name}" for x in p.site.products]))
        self.peek_energy = TrendPeek(t, lambda p: with_data(p, ["price:electricity", "price:fuel", "energy:el"]))
        outer.addWidget(card(t("plant_info"), info, self.peek_prod, self.peek_energy, note=t("plant_info_note")))

        self.sources = DataTable([t("col_name"), t("col_unit_cost"), t("col_metered"), t("col_alternative")],
                                 ["text", "num", "num", "bool"])
        self.outlets = DataTable([t("col_name"), t("col_unit_cost"), t("col_metered")], ["text", "num", "num"])
        self.treatments = DataTable([t("col_name"), t("col_unit_cost"), t("col_wastewater")], ["text", "num", "bool"])
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(table_box(t("sources"), self.sources, t("add"), t("remove"), lambda: ["", 0.0, None, False]))
        row.addWidget(table_box(t("outlets"), self.outlets, t("add"), t("remove"), lambda: ["", 0.0, None]))
        outer.addLayout(row, 1)
        self.peek_src = TrendPeek(t, lambda p: with_data(p, [k for s in p.sources for k in (f"source:{s.name}", f"price:source:{s.name}")]))
        self.peek_out = TrendPeek(t, lambda p: with_data(p, [k for o in p.outlets for k in (f"outlet:{o.name}", f"price:outlet:{o.name}")]))
        prow = QHBoxLayout()
        prow.addWidget(self.peek_src, 1)
        prow.addWidget(self.peek_out, 1)
        outer.addLayout(prow)
        outer.addWidget(table_box(t("treatments"), self.treatments, t("add"), t("remove"), lambda: ["", 0.0, False]), 1)

        for w in (self.name, self.currency, self.prod_unit):
            w.textChanged.connect(self.changed)
        for w in (self.production, self.elec, self.fuel, self.heat_eff):
            w.valueChanged.connect(self.changed)
        for tb in (self.sources, self.outlets, self.treatments):
            tb.changed.connect(self.changed)

    def load(self, p: Plant) -> None:
        self.blockSignals(True)
        self.name.setText(p.name)
        self.currency.setText(p.currency)
        self.production.setValue(p.production_per_year)
        self.prod_unit.setText(p.production_unit)
        self.elec.setValue(p.costs.electricity_per_kwh)
        self.fuel.setValue(p.costs.fuel_per_kwh_thermal)
        self.heat_eff.setValue(p.costs.heating_efficiency)
        self.sources.set_rows([[s.name, s.unit_cost, s.metered_m3, s.alternative] for s in p.sources])
        self.outlets.set_rows([[o.name, o.unit_cost, o.metered_m3] for o in p.outlets])
        self.treatments.set_rows([[x.name, x.unit_cost, x.wastewater] for x in p.treatments])
        self.blockSignals(False)
        self._lock_driven(p)
        for pk in (self.peek_prod, self.peek_energy, self.peek_src, self.peek_out):
            pk.set_plant(p)

    def _lock_driven(self, p: Plant) -> None:
        """Values that come from the time series are shown but cannot be typed here (one entry point per datum)."""
        drv = TS.driven(p)
        tip = self.t("ft_driven")
        self.production.setEnabled(False)               # total production = sum of the products (Site page): display only
        self.production.setToolTip(self.t("production_sum_tip"))
        for w, key in ((self.elec, "costs:electricity_per_kwh"),
                       (self.fuel, "costs:fuel_per_kwh_thermal")):
            w.setEnabled(key not in drv)
            w.setToolTip(tip if key in drv else "")
        self.sources.lock_cells([(r, c) for r, s in enumerate(p.sources) for c, k in ((1, "unit_cost"), (2, "metered"))
                                 if f"source:{s.name}:{k}" in drv], tip, (1, 2))
        self.outlets.lock_cells([(r, c) for r, o in enumerate(p.outlets) for c, k in ((1, "unit_cost"), (2, "metered"))
                                 if f"outlet:{o.name}:{k}" in drv], tip, (1, 2))

    def store(self, p: Plant) -> None:
        p.name = self.name.text().strip() or p.name
        p.currency = self.currency.text().strip() or p.currency
        p.production_unit = self.prod_unit.text().strip() or p.production_unit
        if self.elec.isEnabled():
            p.costs.electricity_per_kwh = self.elec.value()
        if self.fuel.isEnabled():
            p.costs.fuel_per_kwh_thermal = self.fuel.value()
        p.costs.heating_efficiency = self.heat_eff.value() or p.costs.heating_efficiency
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
        self._sub_name = ""
        self.peek = TrendPeek(t, lambda p: with_data(p, [f"sub:{self._sub_name}:{f}" for f in
                                                         ("production", "intake", "discharge", "evaporation", "product", "recirc")]))
        lay.addWidget(card(t("sub_basic"), head, self.peek))
        self.driven: Dict[str, str] = {}          # model fields currently taken from the time series (set by the window)
        self._locked: set = set()
        self.driven_note = QLabel(t("ft_driven_note"))
        self.driven_note.setObjectName("cardnote")
        self.driven_note.setWordWrap(True)
        self.driven_note.setVisible(False)
        lay.addWidget(self.driven_note)

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
        self._sub_name = s.name
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
        self._lock_driven(s)

    def _lock_driven(self, s: Subsystem) -> None:
        drv = self.driven
        tip = self.t("ft_driven")
        self._locked = {f for f in ("intake", "discharge", "evaporation", "product", "recirc") if f"sub:{s.name}:{f}" in drv}
        for f, w in (("evaporation", self.evap), ("product", self.product), ("recirc", self.recirc)):
            w.setEnabled(f not in self._locked)
            w.setToolTip(tip if f in self._locked else "")
        for f, tb in (("intake", self.intake), ("discharge", self.discharge)):
            tb.lock_cells([(r, 1) for r in range(tb.rowCount())] if f in self._locked else [], tip, (1,))
        self.driven_note.setVisible(bool(self._locked))

    def store(self, s: Subsystem) -> None:
        s.name = self.name.text().strip() or s.name
        s.kind = self.kind.currentData() or "other"
        lk = self._locked                                   # fields driven by the time series are not written back
        if "intake" not in lk:
            s.intake = _sum_dict(self.intake.rows())
        if "discharge" not in lk:
            s.discharge = _sum_dict(self.discharge.rows())
        if "recirc" not in lk:
            s.recirculated = self.recirc.value()
        s.from_other = self.from_other.value()
        s.to_other = self.to_other.value()
        if "product" not in lk:
            s.product = self.product.value()
        if "evaporation" not in lk:
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
