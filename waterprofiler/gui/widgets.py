"""Reusable widgets: editable data table, numeric spin box, bar chart."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QLocale, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QComboBox, QDoubleSpinBox, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..numparse import fmt_float, parse_float
from .theme import CHART, COL, nav_pixmap

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
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)   # clean modern look; type or scroll
    s.setMinimumWidth(130)
    return s


def button(text: str, kind: str = "", on_click=None) -> QPushButton:
    """Push button with a theme variant: '' (outline), 'primary', 'danger' or 'ghost'."""
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click is not None:
        b.clicked.connect(lambda _=False: on_click())
    return b


def card(title: str = "", *widgets: QWidget, note: str = "") -> QFrame:
    """White rounded panel with an optional title and note."""
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    if title:
        lab = QLabel(title)
        lab.setObjectName("cardtitle")
        lay.addWidget(lab)
    if note:
        n = QLabel(note)
        n.setObjectName("cardnote")
        n.setWordWrap(True)
        lay.addWidget(n)
    for w in widgets:
        lay.addWidget(w)
    return f


class StatCard(QFrame):
    """Big-number tile: title, value, optional hint, coloured value."""

    def __init__(self, title: str, accent: str = COL["blue"]):
        super().__init__()
        self.setObjectName("stat")
        self.accent = accent
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("stattitle")
        self.value = QLabel("—")
        self.value.setObjectName("statvalue")
        self.value.setStyleSheet(f"color:{accent};")
        self.hint = QLabel("")
        self.hint.setObjectName("stathint")
        self.hint.setWordWrap(True)
        for w in (self.title, self.value, self.hint):
            lay.addWidget(w)

    def set(self, value: str, hint: str = "", accent: Optional[str] = None) -> None:
        # a leading LRM keeps digits, signs and % together in right-to-left layouts
        self.value.setText("\u200e" + value + "\u200e")
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        if accent:
            self.value.setStyleSheet(f"color:{accent};")


class NavButton(QPushButton):
    """Sidebar entry: vector icon + text, laid out by Qt so it mirrors correctly in RTL."""

    def __init__(self, icon_name: str, text: str):
        super().__init__()
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(46)
        self.icon_name = icon_name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)
        self.ic = QLabel()
        self.ic.setFixedSize(22, 22)
        self.tx = QLabel(text)
        for w in (self.ic, self.tx):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.ic)
        lay.addWidget(self.tx, 1)
        self.toggled.connect(self._paint)
        self._paint(False)

    def _paint(self, on: bool) -> None:
        col = "#FFFFFF" if on else COL["sub"]
        self.ic.setPixmap(nav_pixmap(self.icon_name, col))
        self.tx.setStyleSheet(f"color:{'#FFFFFF' if on else COL['text']}; font-size:14px; "
                              f"font-weight:{700 if on else 500}; background:transparent;")


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
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(38)
        self.setMinimumHeight(150)
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
    add = button("+  " + add_text, "primary")
    rem = button(remove_text, "danger")
    add.clicked.connect(lambda: table.add_row(default_row() if default_row else None))
    rem.clicked.connect(table.remove_selected)
    bar.addWidget(add)
    bar.addWidget(rem)
    bar.addStretch(1)
    lay.addLayout(bar)
    return box


PALETTE = CHART


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
        fg = QColor(COL["sub"])
        ink = QColor(COL["text"])
        w, h = self.width(), self.height()
        f = QFont(self.font())
        fm = QFontMetrics(f)

        p.setPen(QColor(COL["navy"]))
        bold = QFont(f)
        bold.setBold(True)
        bold.setPointSizeF(f.pointSizeF() + 1)
        p.setFont(bold)
        p.drawText(QRectF(0, 2, w, 24), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setFont(f)

        if not self.categories or not self.series:
            p.end()
            return

        # legend (round swatches)
        total = sum(14 + fm.horizontalAdvance(n) + 26 for n, _v in self.series)
        x = max(8.0, (w - total) / 2.0)
        y = 30.0
        for i, (name, _v) in enumerate(self.series):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PALETTE[i % len(PALETTE)]))
            p.drawEllipse(QRectF(x, y + 4, 9, 9))
            tw = fm.horizontalAdvance(name)
            p.setPen(ink)
            p.drawText(QRectF(x + 14, y, tw + 8, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            x += 14 + tw + 26

        left, right, top, bottom = 54.0, 12.0, 60.0, 46.0
        pw, ph = w - left - right, h - top - bottom
        if pw <= 10 or ph <= 10:
            p.end()
            return
        vmax = max((max(v) if v else 0.0) for _n, v in self.series) or 1.0
        vmax = vmax * 1.12

        grid = QPen(QColor(COL["line"]))
        grid.setWidthF(1.0)
        for k in range(5):
            gy = top + ph - ph * k / 4.0
            p.setPen(grid)
            p.drawLine(int(left), int(gy), int(left + pw), int(gy))
            val = vmax * k / 4.0
            lab = f"{val * 100:.0f}%" if self.percent else _short(val)
            p.setPen(fg)
            p.drawText(QRectF(0, gy - 9, left - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lab)

        n = len(self.categories)
        gw = pw / n
        ns = len(self.series)
        bw = gw * 0.72 / ns
        p.setPen(Qt.PenStyle.NoPen)
        for ci, cat in enumerate(self.categories):
            gx = left + ci * gw + gw * 0.14
            for si, (_name, vals) in enumerate(self.series):
                v = vals[ci] if ci < len(vals) else 0.0
                bh = ph * (v / vmax)
                if bh <= 0:
                    continue
                rect = QRectF(gx + si * bw + 1, top + ph - bh, bw - 3, bh)
                p.setBrush(QColor(PALETTE[si % len(PALETTE)]))
                p.drawRoundedRect(rect, min(5.0, rect.width() / 2), min(5.0, rect.width() / 2))
            p.setPen(ink)
            label = fm.elidedText(cat, Qt.TextElideMode.ElideRight, int(gw) - 2)
            p.drawText(QRectF(left + ci * gw, top + ph + 6, gw, 36),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, label)
            p.setPen(Qt.PenStyle.NoPen)
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
