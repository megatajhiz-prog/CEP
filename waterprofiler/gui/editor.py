"""Subsystem editor panel and plant-definition panel."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from .. import timeseries as TS
from ..i18n import Translator
from ..model import Outlet, Plant, Pump, Source, Subsystem, Treatment
from ..numparse import fmt_float, parse_float
from .series_view import SeriesPanel, TimeContext
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

    def __init__(self, t: Translator, ctx: Optional[TimeContext] = None):
        super().__init__()
        self.t = t
        self.ctx = ctx or TimeContext(t.lang)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(26, 22, 26, 26)
        outer.setSpacing(16)
        self.name = QLineEdit()
        self.currency = QLineEdit()
        self.prod_unit = QLineEdit()
        self.heat_eff = dspin(maximum=1.0, decimals=3, step=0.01)
        left, right = QFormLayout(), QFormLayout()
        for form in (left, right):
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(10)
        for label, w in (("plant_name", self.name), ("currency", self.currency), ("production_unit", self.prod_unit)):
            left.addRow(t(label), w)
        right.addRow(t("heat_eff"), self.heat_eff)
        info = QWidget()
        il = QHBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(40)
        il.addLayout(left, 1)
        il.addLayout(right, 1)
        # prices of electricity and fuel vary with time: they are series, entered right here
        self.panel_info = SeriesPanel(t, self.ctx, lambda: ["price:electricity", "price:fuel"], opened=True)
        outer.addWidget(card(t("plant_info"), info, self.panel_info, note=t("plant_info_note")))

        self.sources = DataTable([t("col_name"), t("col_alternative")], ["text", "bool"])
        self.outlets = DataTable([t("col_name")], ["text"])
        self.treatments = DataTable([t("col_name"), t("col_wastewater")], ["text", "bool"])
        # water prices and meters (sources, outlets) and treatment unit costs are series: a table + chart under each list
        self.panel_sources = SeriesPanel(t, self.ctx, lambda: [k for s in self._plant().sources
                                                              for k in (f"source:{s.name}", f"price:source:{s.name}")],
                                         opened=True)
        self.panel_outlets = SeriesPanel(t, self.ctx, lambda: [k for o in self._plant().outlets
                                                              for k in (f"outlet:{o.name}", f"price:outlet:{o.name}")],
                                         opened=True)
        self.panel_treat = SeriesPanel(t, self.ctx, lambda: [f"price:treat:{x.name}" for x in self._plant().treatments],
                                       opened=True)
        row = QVBoxLayout()
        row.setSpacing(16)
        for tb, panel, title, dflt in ((self.sources, self.panel_sources, "sources", lambda: ["", False]),
                                       (self.outlets, self.panel_outlets, "outlets", lambda: [""]),
                                       (self.treatments, self.panel_treat, "treatments", lambda: ["", False])):
            col = QVBoxLayout()
            col.addWidget(table_box(t(title), tb, t("add"), t("remove"), dflt))
            col.addWidget(panel)
            row.addLayout(col)
        outer.addLayout(row, 1)

        for w in (self.name, self.currency, self.prod_unit):
            w.textChanged.connect(self.changed)
        self.heat_eff.valueChanged.connect(self.changed)
        for tb in (self.sources, self.outlets, self.treatments):
            tb.changed.connect(self.changed)

    def load(self, p: Plant) -> None:
        self.blockSignals(True)
        self.name.setText(p.name)
        self.currency.setText(p.currency)
        self.prod_unit.setText(p.production_unit)
        self.heat_eff.setValue(p.costs.heating_efficiency)
        self.sources.set_rows([[s.name, s.alternative] for s in p.sources])
        self.outlets.set_rows([[o.name] for o in p.outlets])
        self.treatments.set_rows([[x.name, x.wastewater] for x in p.treatments])
        self.blockSignals(False)
        for panel in (self.panel_info, self.panel_sources, self.panel_outlets, self.panel_treat):
            panel.refresh()

    def _plant(self) -> Plant:
        return self.ctx.plant if self.ctx.plant is not None else Plant(name="")

    def store(self, p: Plant) -> None:
        p.name = self.name.text().strip() or p.name
        p.currency = self.currency.text().strip() or p.currency
        p.production_unit = self.prod_unit.text().strip() or p.production_unit
        p.costs.heating_efficiency = self.heat_eff.value() or p.costs.heating_efficiency
        # prices, meters and unit costs come from the series: existing objects keep the values the sync gave them
        old_s, old_o, old_t = ({x.name: x for x in lst} for lst in (p.sources, p.outlets, p.treatments))
        seen = set()
        p.sources, p.outlets, p.treatments = [], [], []
        for n, alt in self.sources.rows():
            if n and n not in seen:
                seen.add(n)
                o = old_s.get(n)
                p.sources.append(Source(n, o.unit_cost if o else 0.0, o.metered_m3 if o else None, bool(alt)))
        seen = set()
        for (n,) in self.outlets.rows():
            if n and n not in seen:
                seen.add(n)
                o = old_o.get(n)
                p.outlets.append(Outlet(n, o.unit_cost if o else 0.0, o.metered_m3 if o else None))
        seen = set()
        for n, ww in self.treatments.rows():
            if n and n not in seen:
                seen.add(n)
                o = old_t.get(n)
                p.treatments.append(Treatment(n, o.unit_cost if o else 0.0, bool(ww)))


class SubsystemEditor(QScrollArea):
    """Edits one Subsystem. Call set_catalog() then load(); store() writes back."""

    estimate_requested = Signal()

    def __init__(self, t: Translator, ctx: Optional[TimeContext] = None):
        super().__init__()
        self.t = t
        self.ctx = ctx or TimeContext(t.lang)
        self._sub_name = ""
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

        # transfers between subsystems are entered only as links (flow page) + their series; an old fixed value that no
        # link explains is reported here with a button to remove it
        self.legacy_box = QGroupBox(t("other_flows"))
        ll = QVBoxLayout(self.legacy_box)
        self.legacy_note = QLabel("")
        self.legacy_note.setWordWrap(True)
        self.legacy_note.setObjectName("cardnote")
        self.legacy_clear = QPushButton(t("legacy_clear"))
        self.legacy_clear.clicked.connect(self._clear_legacy)
        ll.addWidget(self.legacy_note)
        ll.addWidget(self.legacy_clear, 0, Qt.AlignmentFlag.AlignLeft)
        self.legacy_box.setVisible(False)
        lay.addWidget(self.legacy_box)

        self.wtreat = DataTable([t("treatments"), t("fraction")], ["combo", "num"])
        self.wwtreat = DataTable([t("treatments"), t("fraction")], ["combo", "num"])
        row2 = QHBoxLayout()
        row2.addWidget(table_box(t("water_treat"), self.wtreat, t("add"), t("remove"), lambda: ["", 1.0]))
        row2.addWidget(table_box(t("ww_treat"), self.wwtreat, t("add"), t("remove"), lambda: ["", 1.0]))
        lay.addLayout(row2)

        self.pumps = DataTable(
            [t("col_name"), t("pump_kw"), t("pump_eff"), t("pump_volts"), t("pump_amps"), t("pump_pf"), t("pump_phases")],
            ["text", "num", "num", "num", "num", "num", "num"])          # running hours and load factor are series
        lay.addWidget(table_box(t("pumps"), self.pumps, t("add"), t("remove"),
                                lambda: ["", None, 0.9, None, None, 0.85, 3.0]))
        hint = QLabel(t("pump_hint"))
        hint.setObjectName("cardnote")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.panel = SeriesPanel(t, self.ctx, self._series_keys, opened=True)
        lay.addWidget(card(t("sub_series"), self.panel, note=t("sub_series_note")))
        lay.addStretch(1)

    def _in_links(self, name: str) -> bool:
        p = self.ctx.plant
        return bool(p) and any(x.src == name or x.dst == name for x in p.links)

    def _show_legacy(self, s: Subsystem) -> None:
        on = (s.from_other > 0 or s.to_other > 0) and not self._in_links(s.name)
        self.legacy_box.setVisible(on)
        if on:
            self.legacy_note.setText(self.t("legacy_note", a=f"{s.from_other:,.0f}", b=f"{s.to_other:,.0f}"))

    def _clear_legacy(self) -> None:
        p = self.ctx.plant
        s = next((x for x in p.subsystems if x.name == self._sub_name), None) if p else None
        if s is not None:
            s.from_other = s.to_other = 0.0
            self.legacy_box.setVisible(False)

    def _series_keys(self) -> List[str]:
        p, n = self.ctx.plant, self._sub_name
        sub = next((x for x in p.subsystems if x.name == n), None) if p else None
        if sub is None:
            return []
        keys = [f"sub:{n}:{f}" for f, _a, _b in TS.SUB_FIELDS] + [f"sub:{n}:production", f"sub:{n}:t_in", f"sub:{n}:t_ww"]
        for pm in sub.pumps:
            keys += [f"pump:{n}:{pm.name}:hours", f"pump:{n}:{pm.name}:load"]
        keys += [f"link:{x.src}>{x.dst}" for x in p.links if x.src == n or x.dst == n]
        return keys

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
        self._show_legacy(s)
        self.wtreat.set_rows([[k, v] for k, v in s.water_treatments.items()])
        self.wwtreat.set_rows([[k, v] for k, v in s.wastewater_treatments.items()])
        self.pumps.set_rows([[p.name, p.power_kw if p.power_kw is not None else (
            p.power_hp * 0.746 if p.power_hp is not None else None), p.efficiency,
            p.volts, p.amps, p.power_factor, float(p.phases)] for p in s.pumps])
        self._lock_driven(s)

    def _lock_driven(self, s: Subsystem) -> None:
        """Flows, temperatures and pump hours are time series: shown here, entered in the panel at the bottom.

        The intake / discharge tables stay editable but only their proportions count: the total comes from the series."""
        self._locked = {f for f in ("intake", "discharge") if f"sub:{s.name}:{f}" in self.driven}
        share = self.t("sp_share_tip")
        for tb, f in ((self.intake, "intake"), (self.discharge, "discharge")):
            for r in range(tb.rowCount()):
                it = tb.item(r, 1)
                if it is not None:
                    it.setToolTip(share if f in self._locked else "")
        self.driven_note.setVisible(bool(self._locked))
        self.panel.refresh()

    def store(self, s: Subsystem) -> None:
        s.name = self.name.text().strip() or s.name
        s.kind = self.kind.currentData() or "other"
        s.intake = _sum_dict(self.intake.rows())            # when a series drives the total, only the proportions matter
        s.discharge = _sum_dict(self.discharge.rows())
        # evaporation, product, recirculation, temperatures, pump hours and loads are series-only: written by the sync
        s.water_treatments = _sum_dict(self.wtreat.rows())
        s.wastewater_treatments = _sum_dict(self.wwtreat.rows())
        pumps = []
        old = {x.name: x for x in s.pumps}                    # hours and load factor are series: kept as the sync set them
        for name, kw, eff, volts, amps, pf, phases in self.pumps.rows():
            if not (name or kw or volts):
                continue
            o = old.get(name or "pump")
            pumps.append(Pump(
                name=name or "pump", hours_per_year=o.hours_per_year if o else 0.0, power_kw=kw, power_hp=None,
                efficiency=eff if eff else 0.9, load_fraction=o.load_fraction if o else 1.0,
                volts=volts, amps=amps, power_factor=pf if pf else 0.85,
                phases=1 if phases == 1 else 3))
        s.pumps = pumps
        # (temperatures are series-only as well)
