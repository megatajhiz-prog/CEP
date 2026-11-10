"""Water by product: which share of each unit's / equipment's water serves which product (page «آب محصولات»)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem

from .. import allocation as AL
from ..cost import plant_cost
from ..i18n import Translator
from ..model import Plant
from .tabs import StatCard, _Scroll, _fmt, _message_label, _warn_label, make_table, put, stat_row
from .theme import COL
from .widgets import card


def _pct_text(v: float) -> str:
    return f"{100.0 * v:g}" if v else ""


class ProductWaterTab(_Scroll):
    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Plant | None = None
        self._loading = False
        self._nodes: list = []
        self._products: list = []
        self.msg = _message_label()
        self.lay.addWidget(self.msg)
        self.c_alloc = StatCard(t("pw_allocated"), COL["green"])
        self.c_general = StatCard(t("pw_general") + " (m³)", COL["orange"])
        self.c_total = StatCard(t("sum_intake") + " (m³)", COL["blue"])
        self.lay.addLayout(stat_row(self.c_alloc, self.c_general, self.c_total))
        self.matrix = make_table([t("subsystem")])
        self.matrix.setMinimumHeight(260)
        self.matrix.itemChanged.connect(self._edited)
        self.lay.addWidget(card(t("pw_matrix"), self.matrix, note=t("pw_matrix_note")))
        self.result = make_table([t("pw_product"), t("site_munit"), t("pw_production"), t("sum_intake") + " (m³)",
                                  t("series_consumptive") + " (m³)", t("sum_discharge") + " (m³)", t("pw_share"),
                                  t("pw_cost"), t("pw_m3_unit"), t("pw_cost_unit")])
        self.result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.result.setMinimumHeight(220)
        self.lay.addWidget(card(t("pw_result"), self.result, note=t("pw_result_note")))
        self.warn = _warn_label()
        self.lay.addWidget(self.warn)
        self.lay.addStretch(1)

    # ------------------------------------------------------------------------------------------ data -> view
    def refresh(self, plant: Plant) -> None:
        t = self.t
        self.plant = plant
        plant.rollup()
        self._nodes = plant.ordered()
        self._products = [p.name for p in plant.site.products]
        self.msg.setText("" if self._products and plant.subsystems else t("pw_none"))
        self._loading = True
        heads = [t("subsystem")] + [f"{p} (%)" for p in self._products] + [t("pw_general") + " (%)"]
        self.matrix.setColumnCount(len(heads))
        self.matrix.setHorizontalHeaderLabels(heads)
        self.matrix.setRowCount(len(self._nodes))
        for r, s in enumerate(self._nodes):
            name = ("    ↳ " if s.parent else "") + s.name
            leaf = not plant.has_children(s.name)
            it = QTableWidgetItem(name)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.matrix.setItem(r, 0, it)
            fr = AL.clean_fractions(plant.allocation.get(s.name, {}))
            for c, p in enumerate(self._products, start=1):
                cell = QTableWidgetItem(_pct_text(fr.get(p, 0.0)) if leaf else "")
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if not leaf:                                  # a unit with equipment: its equipment carry the allocation
                    cell.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.matrix.setItem(r, c, cell)
            g = QTableWidgetItem("" if not leaf else f"{100.0 * max(0.0, 1.0 - sum(fr.values())):g}")
            g.setFlags(Qt.ItemFlag.ItemIsEnabled)
            g.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.matrix.setItem(r, len(heads) - 1, g)
        self._loading = False
        self._show_result()

    def _show_result(self) -> None:
        t, plant = self.t, self.plant
        if plant is None:
            return
        res = AL.allocate(plant, plant_cost(plant))
        self.c_alloc.set(f"{res.allocated_pct:.0f}%")
        self.c_general.set(_fmt(res.general.intake))
        self.c_total.set(_fmt(res.total_intake))
        rows = res.products + ([res.general] if res.general.intake or res.general.cost else [])
        self.result.setRowCount(len(rows))
        cur = plant.currency
        for r, x in enumerate(rows):
            put(self.result, r, 0, x.name or t("pw_general"), bold=not x.name)
            put(self.result, r, 1, x.unit)
            put(self.result, r, 2, _fmt(x.production, 1) if x.name else "—", True)
            put(self.result, r, 3, _fmt(x.intake), True)
            put(self.result, r, 4, _fmt(x.consumption), True)
            put(self.result, r, 5, _fmt(x.discharge), True)
            put(self.result, r, 6, f"{x.intake_share_pct:.1f}%", True)
            put(self.result, r, 7, f"{_fmt(x.cost)} {cur}", True)
            put(self.result, r, 8, _fmt(x.per_unit_intake, 3), True)
            put(self.result, r, 9, _fmt(x.per_unit_cost, 1), True)
        self.warn.setText("\n".join(self._warning(w) for w in res.warnings))
        self.warn.setVisible(bool(res.warnings))

    def _warning(self, code: str) -> str:
        t = self.t
        key, *args = code.split(":")
        return t("pw_w_" + key[len("alloc_"):]).format(*args)

    # ------------------------------------------------------------------------------------------ view -> data
    def _edited(self, item) -> None:
        if self._loading or self.plant is None or item.column() == 0:
            return
        r, c = item.row(), item.column()
        if not (0 <= r < len(self._nodes)) or c > len(self._products):
            return
        node = self._nodes[r].name
        fr = {}
        for k, p in enumerate(self._products, start=1):
            txt = (self.matrix.item(r, k).text() if self.matrix.item(r, k) else "").replace(",", ".").strip()
            try:
                v = float(txt) / 100.0 if txt else 0.0
            except ValueError:
                v = 0.0
            fr[p] = max(0.0, v)
        try:
            AL.set_fractions(self.plant, node, fr)
            self.msg.setText("")
        except ValueError:
            self.msg.setText(self.t("pw_over").format(node))       # over 100 %: keep the previous values
        self._loading = True                                        # no rebuild here: only this row is redrawn
        stored = AL.clean_fractions(self.plant.allocation.get(node, {}))
        for k, p in enumerate(self._products, start=1):
            self.matrix.item(r, k).setText(_pct_text(stored.get(p, 0.0)))
        self.matrix.item(r, len(self._products) + 1).setText(f"{100.0 * max(0.0, 1.0 - sum(stored.values())):g}")
        self._loading = False
        self._show_result()
