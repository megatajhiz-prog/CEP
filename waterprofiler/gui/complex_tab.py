"""Industrial-complex page: identity and prices, water sources / outlets / treatments, areas and meters.

One page for what used to be two ("Plant" and "Industrial site"); every item is entered once.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QSpinBox, QTabWidget, QWidget

from ..i18n import Translator
from ..model import Plant, Product
from .editor import PlantPanel
from .site_tab import SiteTab
from .tabs import _Scroll
from .widgets import DataTable, card, dspin, table_box


class GeneralPage(_Scroll):
    """Name, location, operating data, production and prices, product list."""

    changed = Signal()

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self._loading = False
        self.plant: Optional[Plant] = None
        self.name, self.owner, self.sector = QLineEdit(), QLineEdit(), QLineEdit()
        self.province, self.city, self.address, self.note = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.lat = dspin(maximum=90.0, minimum=-90.0, decimals=6, step=0.01)
        self.lon = dspin(maximum=180.0, minimum=-180.0, decimals=6, step=0.01)
        self.land = dspin(maximum=1e9, decimals=2)
        self.year = QSpinBox()
        self.year.setRange(0, 2200)
        self.shifts = QSpinBox()
        self.shifts.setRange(0, 6)
        self.days = QSpinBox()
        self.days.setRange(0, 366)
        self.cal = QComboBox()
        self.cal.addItem(t("cal_jalali"), "jalali")
        self.cal.addItem(t("cal_gregorian"), "gregorian")
        self.currency = QLineEdit()
        self.production = dspin(decimals=2)
        self.prod_unit = QLineEdit()
        self.elec = dspin(decimals=6, step=0.01)
        self.fuel = dspin(decimals=6, step=0.01)
        self.heat_eff = dspin(maximum=1.0, decimals=3, step=0.01)

        def two(left_rows, right_rows):
            left, right = QFormLayout(), QFormLayout()
            for form, rows in ((left, left_rows), (right, right_rows)):
                form.setHorizontalSpacing(16)
                form.setVerticalSpacing(10)
                for key, w in rows:
                    form.addRow(t(key), w)
            box = QWidget()
            hl = QHBoxLayout(box)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(40)
            hl.addLayout(left, 1)
            hl.addLayout(right, 1)
            return box

        self.lay.addWidget(card(t("cx_identity"), two(
            [("plant_name", self.name), ("site_owner", self.owner), ("site_sector", self.sector),
             ("site_province", self.province), ("site_city", self.city), ("site_address", self.address),
             ("site_note", self.note)],
            [("site_lat", self.lat), ("site_lon", self.lon), ("site_land", self.land), ("site_year", self.year),
             ("site_shifts", self.shifts), ("site_opdays", self.days), ("site_calendar", self.cal)]),
            note=t("cx_identity_note")))
        self.lay.addWidget(card(t("cx_prod_prices"), two(
            [("currency", self.currency), ("production", self.production), ("production_unit", self.prod_unit)],
            [("elec_cost", self.elec), ("fuel_cost", self.fuel), ("heat_eff", self.heat_eff)]),
            note=t("plant_info_note")))
        self.products = DataTable([t("col_name"), t("site_unit"), t("site_note")], ["text", "text", "text"])
        self.products.setMinimumHeight(170)
        self.lay.addWidget(table_box(t("site_products"), self.products, t("add"), t("remove"),
                                     lambda: ["", self.prod_unit.text().strip() or "t", ""]))
        self.lay.addStretch(1)
        for w in (self.name, self.owner, self.sector, self.province, self.city, self.address, self.note,
                  self.currency, self.prod_unit):
            w.textChanged.connect(self._edited)
        for w in (self.lat, self.lon, self.land, self.production, self.elec, self.fuel, self.heat_eff,
                  self.year, self.shifts, self.days):
            w.valueChanged.connect(self._edited)
        self.cal.currentIndexChanged.connect(self._edited)
        self.products.changed.connect(self._edited)

    def load(self, p: Plant) -> None:
        self._loading = True
        self.plant = p
        s = p.site
        for w, v in ((self.name, p.name), (self.owner, s.owner), (self.sector, s.sector), (self.province, s.province),
                     (self.city, s.city), (self.address, s.address), (self.note, s.note), (self.currency, p.currency),
                     (self.prod_unit, p.production_unit)):
            w.setText(v)
        self.lat.setValue(s.latitude)
        self.lon.setValue(s.longitude)
        self.land.setValue(s.land_area_m2)
        self.year.setValue(s.commissioning_year)
        self.shifts.setValue(s.shifts_per_day)
        self.days.setValue(s.operating_days)
        self.cal.setCurrentIndex(max(0, self.cal.findData(s.calendar)))
        self.production.setValue(p.production_per_year)
        self.elec.setValue(p.costs.electricity_per_kwh)
        self.fuel.setValue(p.costs.fuel_per_kwh_thermal)
        self.heat_eff.setValue(p.costs.heating_efficiency)
        self.products.set_rows([[x.name, x.unit, x.note] for x in s.products])
        self._loading = False

    def store(self, p: Plant) -> None:
        if self.plant is not p:
            return
        s = p.site
        p.name = self.name.text().strip() or p.name
        p.currency = self.currency.text().strip() or p.currency
        p.production_per_year = self.production.value()
        p.production_unit = self.prod_unit.text().strip() or p.production_unit
        p.costs.electricity_per_kwh = self.elec.value()
        p.costs.fuel_per_kwh_thermal = self.fuel.value()
        p.costs.heating_efficiency = self.heat_eff.value() or p.costs.heating_efficiency
        s.owner, s.sector = self.owner.text().strip(), self.sector.text().strip()
        s.province, s.city, s.address = self.province.text().strip(), self.city.text().strip(), self.address.text().strip()
        s.note = self.note.text().strip()
        s.latitude, s.longitude, s.land_area_m2 = self.lat.value(), self.lon.value(), self.land.value()
        s.commissioning_year, s.shifts_per_day, s.operating_days = self.year.value(), self.shifts.value(), self.days.value()
        s.calendar = self.cal.currentData() or "jalali"
        seen = set()
        s.products = []
        for n, u, note in self.products.rows():
            if n and n not in seen:
                seen.add(n)
                s.products.append(Product(n, u or p.production_unit, note))

    def _edited(self, *_a) -> None:
        if self._loading or self.plant is None:
            return
        self.store(self.plant)
        self.changed.emit()


class ComplexTab(QTabWidget):
    """The three parts of the industrial complex, each a tab of this page."""

    changed = Signal()

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.general = GeneralPage(t)
        self.resources = PlantPanel(t)
        self.structure = SiteTab(t)
        self.addTab(self.general, t("cx_general"))
        self.addTab(self.resources, t("cx_resources"))
        self.addTab(self.structure, t("cx_structure"))
        self.general.changed.connect(self.changed)
        self.structure.changed.connect(self.changed)
        self.currentChanged.connect(self._inner_changed)

    def load(self, p: Plant) -> None:
        self.general.load(p)
        self.resources.load(p)
        self.structure.load(p)

    def store(self, p: Plant) -> None:
        self.general.store(p)
        self.resources.store(p)
        self.structure.store(p)

    def refresh(self, p: Plant) -> None:
        """Page shown: pick up renamed subsystems / sources / outlets."""
        self.store(p)
        self.structure.refresh(p)

    def _inner_changed(self, _i: int) -> None:
        if self.general.plant is not None:
            self.refresh(self.general.plant)
