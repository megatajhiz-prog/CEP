"""Site page: the structure of the industrial site (areas, products, meters) and its descriptive data."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QWidget

from .. import complex as CX
from .. import timeseries as TS
from ..indicator_text import STRUCT_GROUPS
from ..i18n import Translator
from ..model import Area, Meter, Plant, Product, Site
from .profile_inputs import ProfileInputs
from .tabs import _Scroll, make_table, put
from .widgets import DataTable, card, dspin, table_box

AREA_KINDS = ("production", "utility", "services", "landscape", "other")
METER_KINDS = ("flow", "energy", "quality", "level", "other")


class _Kinds:
    """Localised labels for a fixed list of identifiers, both directions."""

    def __init__(self, t: Translator, prefix: str, ids):
        self.ids = list(ids)
        self.labels = [t(prefix + i) for i in ids]
        self._to_id = dict(zip(self.labels, self.ids))
        self._to_label = dict(zip(self.ids, self.labels))

    def id(self, label: str) -> str:
        return self._to_id.get(label, self.ids[-1])

    def label(self, ident: str) -> str:
        return self._to_label.get(ident, self.labels[-1])


class SiteTab(_Scroll):
    changed = Signal()

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self._loading = False
        self.plant: Optional[Plant] = None
        self.area_kinds = _Kinds(t, "site_ak_", AREA_KINDS)
        self.meter_kinds = _Kinds(t, "site_mk_", METER_KINDS)

        # ---- descriptive data
        self.f_owner, self.f_sector = QLineEdit(), QLineEdit()
        self.f_province, self.f_city, self.f_address = QLineEdit(), QLineEdit(), QLineEdit()
        self.f_note = QLineEdit()
        self.f_lat = dspin(maximum=90.0, minimum=-90.0, decimals=6, step=0.01)
        self.f_lon = dspin(maximum=180.0, minimum=-180.0, decimals=6, step=0.01)
        self.f_land = dspin(maximum=1e9, decimals=2)
        self.f_year = QSpinBox()
        self.f_year.setRange(0, 2200)
        self.f_shifts = QSpinBox()
        self.f_shifts.setRange(0, 6)
        self.f_cal = QComboBox()
        self.f_cal.addItem(t("cal_jalali"), "jalali")
        self.f_cal.addItem(t("cal_gregorian"), "gregorian")
        left, right = QFormLayout(), QFormLayout()
        for form in (left, right):
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(10)
        for key, w in (("site_owner", self.f_owner), ("site_sector", self.f_sector),
                       ("site_province", self.f_province), ("site_city", self.f_city), ("site_address", self.f_address),
                       ("site_note", self.f_note)):
            left.addRow(t(key), w)
        for key, w in (("site_lat", self.f_lat), ("site_lon", self.f_lon), ("site_land", self.f_land),
                       ("site_year", self.f_year), ("site_shifts", self.f_shifts),
                       ("site_calendar", self.f_cal)):
            right.addRow(t(key), w)
        info = QWidget()
        il = QHBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(40)
        il.addLayout(left, 1)
        il.addLayout(right, 1)
        self.lay.addWidget(card(t("site_info"), info, note=t("site_info_note")))
        self.struct = ProfileInputs(t, STRUCT_GROUPS)
        self.lay.addWidget(card(t("site_struct"), self.struct, note=t("site_struct_note")))

        # ---- areas, products
        self.areas = DataTable([t("col_name"), t("site_kind"), t("site_note")], ["text", "combo", "text"],
                               {1: self.area_kinds.labels})
        self.products = DataTable([t("col_name"), t("site_note")], ["text", "text"])
        self.areas.setMinimumHeight(170)
        self.products.setMinimumHeight(170)
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(table_box(t("site_areas"), self.areas, t("add"), t("remove"),
                                lambda: ["", self.area_kinds.labels[0], ""]))
        row.addWidget(table_box(t("site_products"), self.products, t("add"), t("remove"), lambda: ["", ""]))
        self.lay.addLayout(row)

        # ---- subsystems -> areas
        self.assign = make_table([t("subsystem"), t("site_area"), t("site_intake"), t("site_share")])
        self.assign.setMinimumHeight(200)
        self.assign_rows: List[str] = []
        self.lay.addWidget(card(t("site_assign"), self.assign, note=t("site_assign_note")))
        self.summary = make_table([t("site_area"), t("site_nsubs"), t("site_intake"), t("site_discharge"), t("site_evap"), t("site_product"), t("site_share")])
        self.summary.setMinimumHeight(170)
        self.lay.addWidget(card(t("site_summary"), self.summary))

        # ---- meters
        self.meters = DataTable([t("col_name"), t("site_tag"), t("site_kind"), t("site_munit"), t("site_acc"),
                                 t("site_installed"), t("site_calibrated"), t("site_note")],
                                ["text", "combo", "combo", "text", "num", "text", "text", "text"],
                                {2: self.meter_kinds.labels})
        self.meters.setMinimumHeight(220)
        self.meter_status = QLabel("")
        self.meter_status.setObjectName("cardnote")
        self.meter_status.setWordWrap(True)
        mb = table_box(t("site_meters"), self.meters, t("add"), t("remove"),
                       lambda: ["", "", self.meter_kinds.labels[0], "m3", None, "", "", ""])
        mb.layout().addWidget(self.meter_status)
        self.lay.addWidget(mb)
        self.lay.addStretch(1)

        for w in (self.f_owner, self.f_sector, self.f_province, self.f_city, self.f_address, self.f_note):
            w.textChanged.connect(self._edited)
        for w in (self.f_lat, self.f_lon, self.f_land):
            w.valueChanged.connect(self._edited)
        for w in (self.f_year, self.f_shifts):
            w.valueChanged.connect(self._edited)
        self.f_cal.currentIndexChanged.connect(self._edited)
        for tb in (self.areas, self.products, self.meters):
            tb.changed.connect(self._edited)

    # ------------------------------------------------------------------ load / store
    def load(self, plant: Plant) -> None:
        self._loading = True
        self.plant = plant
        s = plant.site
        for w, v in ((self.f_owner, s.owner), (self.f_sector, s.sector), (self.f_province, s.province),
                     (self.f_city, s.city), (self.f_address, s.address), (self.f_note, s.note)):
            w.setText(v)
        self.f_lat.setValue(s.latitude)
        self.f_lon.setValue(s.longitude)
        self.f_land.setValue(s.land_area_m2)
        self.f_year.setValue(s.commissioning_year)
        self.f_shifts.setValue(s.shifts_per_day)
        self.f_cal.setCurrentIndex(max(0, self.f_cal.findData(s.calendar)))
        self.struct.load(plant)
        self.areas.set_rows([[a.name, self.area_kinds.label(a.kind), a.note] for a in s.areas])
        self.products.set_rows([[p.name, p.note] for p in s.products])
        self._load_meters(plant)
        self._load_assign(plant)
        self._loading = False
        self._update_summary()

    def _load_meters(self, plant: Plant) -> None:
        keys = [""] + [v.key for v in TS.catalog(plant)]
        self.meters.combo_items[1] = keys
        self.meters.set_rows([[m.name, m.tag, self.meter_kinds.label(m.kind), m.unit, m.accuracy_pct or None, m.installed,
                               m.calibrated, m.note] for m in plant.site.meters])

    def _area_names(self) -> List[str]:
        return [r[0] for r in self.areas.rows() if r[0]]

    def _load_assign(self, plant: Plant) -> None:
        names = [""] + self._area_names()
        self.assign_rows = [s.name for s in plant.subsystems]
        self.assign.clearContents()
        self.assign.setRowCount(len(plant.subsystems))
        total = sum(s.total_intake for s in plant.subsystems)
        for r, s in enumerate(plant.subsystems):
            put(self.assign, r, 0, s.name, bold=True)
            cb = QComboBox()
            items = list(names)
            if s.area and s.area not in items:
                items.append(s.area)
            cb.addItems(items)
            cb.setCurrentText(s.area)
            cb.currentTextChanged.connect(self._edited)
            self.assign.setCellWidget(r, 1, cb)
            put(self.assign, r, 2, f"{s.total_intake:,.0f}", True)
            put(self.assign, r, 3, f"{100 * s.total_intake / total:.1f}%" if total > 0 else "—", True)

    def store(self, plant: Plant) -> None:
        """Write the page into the plant. Does nothing until the page has been loaded for this plant."""
        if self.plant is not plant:
            return
        s = plant.site
        s.owner, s.sector = self.f_owner.text().strip(), self.f_sector.text().strip()
        s.name = plant.name                      # one name for the complex: the plant name
        s.province, s.city, s.address = self.f_province.text().strip(), self.f_city.text().strip(), self.f_address.text().strip()
        s.note = self.f_note.text().strip()
        s.latitude, s.longitude, s.land_area_m2 = self.f_lat.value(), self.f_lon.value(), self.f_land.value()
        s.commissioning_year, s.shifts_per_day = self.f_year.value(), self.f_shifts.value()
        s.calendar = self.f_cal.currentData() or "jalali"
        seen = set()
        s.areas = []
        for n, k, note in self.areas.rows():
            if n and n not in seen:
                seen.add(n)
                s.areas.append(Area(n, self.area_kinds.id(k), note))
        seen = set()
        s.products = []
        for n, note in self.products.rows():
            if n and n not in seen:
                seen.add(n)
                s.products.append(Product(n, plant.production_unit, note))      # products share the plant's unit
        s.meters = []
        for n, tag, k, u, acc, ins, cal_, note in self.meters.rows():
            if n:
                s.meters.append(Meter(n, tag, self.meter_kinds.id(k), u, float(acc or 0.0), ins, cal_, note))
        by_name = {x.name: x for x in plant.subsystems}
        for r, name in enumerate(self.assign_rows):
            cb = self.assign.cellWidget(r, 1)
            if cb is not None and name in by_name:
                by_name[name].area = cb.currentText()

    # -------------------------------------------------------------------- reactions
    def _edited(self, *_a) -> None:
        if self._loading or self.plant is None:
            return
        self.store(self.plant)
        self._update_summary()
        self.changed.emit()

    def refresh(self, plant: Plant) -> None:
        """Called when the page is opened: pick up renamed subsystems, sources and outlets."""
        if self.plant is plant:
            self.store(plant)
        self._loading = True
        self.plant = plant
        self._load_meters(plant)
        self._load_assign(plant)
        self._loading = False
        self._update_summary()

    def _update_summary(self) -> None:
        plant = self.plant
        if plant is None:
            return
        rows = CX.area_rows(plant)
        self.summary.clearContents()
        self.summary.setRowCount(len(rows))
        for r, x in enumerate(rows):
            put(self.summary, r, 0, x.name or self.t("site_unassigned"), bold=True)
            put(self.summary, r, 1, str(len(x.subsystems)), True)
            for c, v in enumerate((x.intake, x.discharge, x.evaporation, x.product), 2):
                put(self.summary, r, c, f"{v:,.0f}", True)
            put(self.summary, r, 6, "—" if x.share is None else f"{x.share:.1f}%", True)
        meters = CX.meter_rows(plant)
        due = sum(1 for m in meters if m.due)
        self.meter_status.setText(self.t("site_meter_status", n=len(meters), due=due) if meters else "")
