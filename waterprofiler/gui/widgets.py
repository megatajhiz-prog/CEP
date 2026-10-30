"""Reusable widgets: editable data table, numeric spin box, bar chart."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QLocale, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QHeaderView,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..numparse import fmt_float, parse_float

ITEM_FLAG = Qt.ItemFlag
CHECKED, UNCHECKED = Qt.CheckState.Checked, Qt.CheckState.Unchecked


def dspin(maximum: float = 1e12, decimals: int = 3, minimum: float = 0.0, step: float = 1.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setLocale(QLocale(QLocale.Language.English))
    s.setRange(minimum, maximum)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setGroupSeparatorShown(True)
    s.setKeyboardTracking(False)
    s.setMinimumWidth(130)
    return s


class DataTable(QTableWidget):
    """Table whose columns are text / num / bool / combo. rows() <-> set_rows()."""

    changed = Signal()

    def __init__(self, headers: Sequence[str], kinds: Sequence[str], combo_items: Optional[Dict[int, List[str]]] = None):
        super().__init__(0, len(headers))
        self.kinds = list(kinds)
        self.combo_items: Dict[int, List[str]] = dict(combo_items or {})
        self._loading = False
        self.setHorizontalHeaderLabels(list(headers))
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.itemChanged.connect(self._on_item)

    def _on_item(self, _item) -> None:
        if not self._loading:
            self.changed.emit()

    def _combo_changed(self, *_a) -> None:
        if not self._loading:
            self.changed.emit()

    def add_row(self, values: Optional[Sequence] = None, emit: bool = True) -> None:
        was = self._loading
        self._loading = True
        r = self.rowCount()
        self.insertRow(r)
        for c, kind in enumerate(self.kinds):
            v = values[c] if values is not None and c < len(values) else None
            if kind == "combo":
                cb = QComboBox()
                items = list(self.combo_items.get(c, []))
                if v is not None and v not in items:
                    items.append(v)
                cb.addItems(items)
                if v is not None:
                    cb.setCurrentText(v)
                cb.currentTextChanged.connect(self._combo_changed)
                self.setCellWidget(r, c, cb)
            elif kind == "bool":
                it = QTableWidgetItem()
                it.setFlags(ITEM_FLAG.ItemIsUserCheckable | ITEM_FLAG.ItemIsEnabled | ITEM_FLAG.ItemIsSelectable)
                it.setCheckState(CHECKED if v else UNCHECKED)
                self.setItem(r, c, it)
            elif kind == "num":
                it = QTableWidgetItem(fmt_float(parse_float(v)))
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(r, c, it)
            else:
                self.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self._loading = was
        if emit and not was:
            self.changed.emit()

    def remove_selected(self) -> None:
        r = self.currentRow()
        if r >= 0:
            self.removeRow(r)
            self.changed.emit()

    def set_rows(self, rows: Sequence[Sequence]) -> None:
        self._loading = True
        self.setRowCount(0)
        for row in rows:
            self.add_row(row, emit=False)
        self._loading = False

    def rows(self) -> List[list]:
        out = []
        for r in range(self.rowCount()):
            row = []
            for c, kind in enumerate(self.kinds):
                if kind == "combo":
                    w = self.cellWidget(r, c)
                    row.append(w.currentText() if w else "")
                elif kind == "bool":
                    it = self.item(r, c)
                    row.append(bool(it and it.checkState() == CHECKED))
                elif kind == "num":
                    it = self.item(r, c)
                    row.append(parse_float(it.text() if it else None))
                else:
                    it = self.item(r, c)
                    row.append((it.text() if it else "").strip())
            out.append(row)
        return out


def table_box(title: str, table: DataTable, add_text: str, remove_text: str,
              default_row: Optional[Callable[[], list]] = None) -> QGroupBox:
    box = QGroupBox(title)
    lay = QVBoxLayout(box)
    lay.addWidget(table)
    bar = QHBoxLayout()
    add = QPushButton(add_text)
    rem = QPushButton(remove_text)
    add.clicked.connect(lambda: table.add_row(default_row() if default_row else None))
    rem.clicked.connect(table.remove_selected)
    bar.addWidget(add)
    bar.addWidget(rem)
    bar.addStretch(1)
    lay.addLayout(bar)
    return box


PALETTE = ["#2f6fb0", "#e08a2b", "#3a9d8f", "#a65ea8", "#c9524a", "#7a8b3c"]


class BarChart(QWidget):
    """Grouped vertical bar chart painted with QPainter (correct RTL / Persian text)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = ""
        self.categories: List[str] = []
        self.series: List[Tuple[str, List[float]]] = []
        self.percent = False
        self.setMinimumHeight(240)

    def set_data(self, title: str, categories: Sequence[str], series: Sequence[Tuple[str, Sequence[float]]],
                 percent: bool = False) -> None:
        self.title = title
        self.categories = list(categories)
        self.series = [(n, list(v)) for n, v in series]
        self.percent = percent
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg = self.palette().text().color()
        p.fillRect(self.rect(), self.palette().base())
        w, h = self.width(), self.height()
        f = QFont(self.font())
        fm = QFontMetrics(f)

        p.setPen(fg)
        bold = QFont(f)
        bold.setBold(True)
        p.setFont(bold)
        p.drawText(QRectF(0, 4, w, 22), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setFont(f)

        if not self.categories or not self.series:
            return

        # legend
        x = 12.0
        y = 30.0
        for i, (name, _v) in enumerate(self.series):
            p.fillRect(QRectF(x, y + 3, 10, 10), QColor(PALETTE[i % len(PALETTE)]))
            tw = fm.horizontalAdvance(name)
            p.setPen(fg)
            p.drawText(QRectF(x + 14, y, tw + 8, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            x += 14 + tw + 22

        left, right, top, bottom = 50.0, 10.0, 54.0, 46.0
        pw, ph = w - left - right, h - top - bottom
        if pw <= 10 or ph <= 10:
            return
        vmax = max((max(v) if v else 0.0) for _n, v in self.series) or 1.0
        vmax = vmax * 1.12

        # axis + gridlines
        axis_pen = QPen(fg)
        axis_pen.setWidthF(1.0)
        grid = QPen(QColor(128, 128, 128, 70))
        for k in range(5):
            gy = top + ph - ph * k / 4.0
            p.setPen(grid)
            p.drawLine(int(left), int(gy), int(left + pw), int(gy))
            val = vmax * k / 4.0
            lab = f"{val * 100:.0f}%" if self.percent else _short(val)
            p.setPen(fg)
            p.drawText(QRectF(0, gy - 8, left - 4, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lab)
        p.setPen(axis_pen)
        p.drawLine(int(left), int(top + ph), int(left + pw), int(top + ph))

        n = len(self.categories)
        gw = pw / n
        ns = len(self.series)
        bw = gw * 0.72 / ns
        for ci, cat in enumerate(self.categories):
            gx = left + ci * gw + gw * 0.14
            for si, (_name, vals) in enumerate(self.series):
                v = vals[ci] if ci < len(vals) else 0.0
                bh = ph * (v / vmax)
                rect = QRectF(gx + si * bw, top + ph - bh, bw - 2, bh)
                p.fillRect(rect, QColor(PALETTE[si % len(PALETTE)]))
            p.setPen(fg)
            label = fm.elidedText(cat, Qt.TextElideMode.ElideRight, int(gw) - 2)
            p.drawText(QRectF(left + ci * gw, top + ph + 4, gw, 36),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, label)
        p.end()


def _short(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.1f}G"
    if a >= 1e6:
        return f"{v / 1e6:.1f}M"
    if a >= 1e3:
        return f"{v / 1e3:.0f}k"
    return f"{v:.0f}"
