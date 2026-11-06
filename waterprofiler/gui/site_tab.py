"""Structure part of the industrial-complex page: areas, subsystem assignment and the meter list."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLabel

from .. import timeseries as TS
from ..i18n import Translator
from ..model import Area, Meter, Plant
from .tabs import _Scroll, make_table, put
from .widgets import DataTable, card, table_box

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

        # ---- areas
        self.areas = DataTable([t("col_name"), t("site_kind"), t("site_note")], ["text", "combo", "text"],
                               {1: self.area_kinds.labels})
        self.areas.setMinimumHeight(170)
        self.lay.addWidget(table_box(t("site_areas"), self.areas, t("add"), t("remove"),
                                     lambda: ["", self.area_kinds.labels[0], ""]))

        # ---- subsystems -> areas
        self.assign = make_table([t("subsystem"), t("site_area"), t("site_intake"), t("site_share")])
        self.assign.setMinimumHeight(200)
        self.assign_rows: List[str] = []
        self.lay.addWidget(card(t("site_assign"), self.assign, note=t("site_assign_note")))
        self.summary = make_table([t("site_area"), t("site_nsubs"), t("site_intake"), t("site_share")])
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

        for tb in (self.areas, self.meters):
            tb.changed.connect(self._edited)

    # ------------------------------------------------------------------ load / store
    def load(self, plant: Plant) -> None:
        self._loading = True
        self.plant = plant
        s = plant.site
        self.areas.set_rows([[a.name, self.area_kinds.label(a.kind), a.note] for a in s.areas])
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
        seen = set()
        s.areas = []
        for n, k, note in self.areas.rows():
            if n and n not in seen:
                seen.add(n)
                s.areas.append(Area(n, self.area_kinds.id(k), note))
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
        total = sum(s.total_intake for s in plant.subsystems)
        names = self._area_names()
        for s in plant.subsystems:
            if s.area and s.area not in names:
                names.append(s.area)
        rows = [(n, [s for s in plant.subsystems if s.area == n]) for n in names]
        free = [s for s in plant.subsystems if not s.area or s.area not in names]
        if free:
            rows.append((self.t("site_unassigned"), free))
        self.summary.setRowCount(len(rows))
        for r, (n, subs) in enumerate(rows):
            v = sum(s.total_intake for s in subs)
            put(self.summary, r, 0, n, bold=True)
            put(self.summary, r, 1, str(len(subs)), True)
            put(self.summary, r, 2, f"{v:,.0f}", True)
            put(self.summary, r, 3, f"{100 * v / total:.1f}%" if total > 0 else "—", True)
        today = date.today()
        due = 0
        for m in plant.site.meters:
            try:
                last = date.fromisoformat(m.calibrated)
                if (today - last).days > 365:
                    due += 1
            except ValueError:
                due += 1
        n = len(plant.site.meters)
        self.meter_status.setText(self.t("site_meter_status", n=n, due=due) if n else "")
