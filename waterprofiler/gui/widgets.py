"""Reusable widgets: editable data table, numeric spin box, bar chart."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QEvent, QLocale, QObject, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QComboBox, QDoubleSpinBox, QFrame, QGroupBox, QHBoxLayout,
    QAbstractScrollArea, QApplication, QHeaderView, QLabel, QLayout, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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


class Sections(QTabWidget):
    """Parallel sub-pages for a long page: each section is a column of cards, only the open one takes room.

    ``page(title)`` returns the QVBoxLayout of a new section; call ``finish()`` once all cards have been added.
    """

    def __init__(self):
        super().__init__()
        self.setDocumentMode(True)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def page(self, title: str) -> QVBoxLayout:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 14, 0, 0)
        lay.setSpacing(16)
        self.addTab(w, title)
        return lay

    def finish(self) -> None:
        for i in range(self.count()):
            self.widget(i).layout().addStretch(1)

    def _fit(self, hint, minimum: bool = False):
        """Size of the open section (QTabWidget would otherwise ask for the widest of all of them)."""
        cur = self.currentWidget()
        if cur is not None:
            base = cur.minimumSizeHint() if minimum else cur.sizeHint()
            hint.setHeight(cur.sizeHint().height() + self.tabBar().sizeHint().height() + 8)
            hint.setWidth(base.width() + 4)
        return hint

    def sizeHint(self):
        return self._fit(super().sizeHint())

    def minimumSizeHint(self):
        return self._fit(super().minimumSizeHint(), True)


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
        self.setMinimumHeight(108)
        for w in (self.title, self.value, self.hint):
            lay.addWidget(w)
        lay.addStretch(1)

    def set(self, value: str, hint: str = "", accent: Optional[str] = None) -> None:
        # a leading LRM keeps digits, signs and % together in right-to-left layouts
        self.value.setText("\u200e" + value + "\u200e")
        self.hint.setText(hint)
        if accent:
            self.value.setStyleSheet(f"color:{accent};")


class NavButton(QPushButton):
    """Sidebar entry: vector icon + text, laid out by Qt so it mirrors correctly in RTL."""

    def __init__(self, icon_name: str, text: str):
        super().__init__()
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(42)
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
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(r, c, it)
            else:
                self.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self._loading = was
        if emit and not was:
            self.changed.emit()

    def lock_cells(self, cells, tip: str = "", reset_cols=()) -> int:
        """Make the number cells ``(row, col)`` read-only (values that come from elsewhere); returns how many were locked.

        Cells of ``reset_cols`` are made editable again first, so a lock that no longer applies is lifted."""
        for r in range(self.rowCount()):
            for c in reset_cols:
                it = self.item(r, c)
                if it is not None and not (it.flags() & ITEM_FLAG.ItemIsEditable):
                    it.setFlags(it.flags() | ITEM_FLAG.ItemIsEditable)
                    it.setBackground(QBrush())
                    it.setToolTip("")
        n = 0
        for r, c in cells:
            it = self.item(r, c)
            if it is not None:
                it.setFlags(it.flags() & ~ITEM_FLAG.ItemIsEditable)
                it.setBackground(QColor("#EEF1F5"))
                it.setToolTip(tip)
                n += 1
        return n

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


class StatGrid(QLayout):
    """Row of big-number cards that wraps onto several lines when the window is narrow (a plain row would force a wide page)."""

    MIN_W = 190

    def __init__(self, spacing: int = 14):
        super().__init__()
        self._items: list = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 (Qt API)
        self._items.append(item)
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation.Horizontal

    def _min_w(self) -> int:
        return max([self.MIN_W] + [it.minimumSize().width() for it in self._items])

    def _cols(self, width: int) -> int:
        n = len(self._items)
        if n == 0:
            return 1
        return max(1, min(n, (width + self._sp) // (self._min_w() + self._sp)))

    def _heights(self, width: int):
        cols = self._cols(width)
        cw = (width - (cols - 1) * self._sp) // cols
        rows = []
        for r in range(0, len(self._items), cols):
            h = 0
            for it in self._items[r:r + cols]:
                ih = it.heightForWidth(cw) if it.hasHeightForWidth() else it.sizeHint().height()
                h = max(h, ih, it.minimumSize().height())
            rows.append(h)
        return cols, cw, rows

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        if not self._items:
            return 0
        _c, _w, rows = self._heights(width)
        return sum(rows) + self._sp * (len(rows) - 1)

    def setGeometry(self, rect) -> None:  # noqa: N802
        super().setGeometry(rect)
        if not self._items:
            return
        cols, cw, rows = self._heights(rect.width())
        rtl = QApplication.layoutDirection() == Qt.LayoutDirection.RightToLeft
        y = rect.y()
        for ri, rh in enumerate(rows):
            for ci, it in enumerate(self._items[ri * cols:(ri + 1) * cols]):
                x = rect.right() + 1 - (ci + 1) * cw - ci * self._sp if rtl else rect.x() + ci * (cw + self._sp)
                it.setGeometry(QRect(x, y, cw, rh))
            y += rh + self._sp

    def sizeHint(self) -> QSize:  # noqa: N802
        if not self._items:
            return QSize(0, 0)
        w = sum(max(it.sizeHint().width(), self._min_w()) for it in self._items) + self._sp * (len(self._items) - 1)
        return QSize(w, max(it.sizeHint().height() for it in self._items))

    def minimumSize(self) -> QSize:  # noqa: N802
        if not self._items:
            return QSize(0, 0)
        return QSize(self._min_w(), max(it.minimumSize().height() for it in self._items))


_NO_WRAP = {"appname", "nav", "pagetitle", "accent"}


class _UiGuard(QObject):
    """Application-wide rules that keep pages inside the window:

    * the mouse wheel over a number box or drop-down that does not have the keyboard focus scrolls the page, not the value;
    * long texts wrap and drop-downs are not as wide as their longest item, so a page never needs more width than the window has.
    """

    @staticmethod
    def _area(obj):
        p = obj.parentWidget()
        while p is not None:
            if isinstance(p, QAbstractScrollArea) and p is not obj:
                return p
            p = p.parentWidget()
        return None

    def eventFilter(self, obj, ev):  # noqa: N802 (Qt API)
        t = ev.type()
        if t == QEvent.Type.Wheel:
            if isinstance(obj, (QAbstractSpinBox, QComboBox)) and not obj.hasFocus():
                area = self._area(obj)
                if area is not None:
                    vp = area.viewport()
                    pos = vp.mapFromGlobal(ev.globalPosition().toPoint())
                    fwd = QWheelEvent(QPointF(pos), ev.globalPosition(), ev.pixelDelta(), ev.angleDelta(), ev.buttons(),
                                      ev.modifiers(), ev.phase(), ev.inverted(), ev.source())
                    QApplication.sendEvent(vp, fwd)
                ev.accept()
                return True
        elif t == QEvent.Type.Polish:
            if isinstance(obj, QComboBox):
                if obj.sizeAdjustPolicy() != QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon:
                    obj.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                    obj.setMinimumContentsLength(max(8, obj.minimumContentsLength()))
            elif isinstance(obj, QLabel):
                par = obj.parentWidget()
                if (not obj.wordWrap() and len(obj.text()) > 22 and obj.objectName() not in _NO_WRAP
                        and not (par is not None and par.objectName() in _NO_WRAP)):
                    obj.setWordWrap(True)
        return False


def install_wheel_guard(app) -> None:
    if getattr(app, "_wheel_guard", None) is None:
        app._wheel_guard = _UiGuard(app)
        app.installEventFilter(app._wheel_guard)
