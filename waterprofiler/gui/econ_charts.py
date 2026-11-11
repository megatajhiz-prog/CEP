"""Painted charts of the economic analysis pages: tornado, spider, histogram with cumulative curve, stacked life-cycle cost."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .theme import COL
from .widgets import PALETTE, _short


class _Chart(QWidget):
    def __init__(self, title: str = "", height: int = 300):
        super().__init__()
        self.title = title
        self.setMinimumHeight(height)

    def _frame(self, p: QPainter) -> QFont:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(self.font())
        bold = QFont(f)
        bold.setBold(True)
        p.setPen(QColor(COL["navy"]))
        p.setFont(bold)
        p.drawText(QRectF(0, 2, self.width(), 24), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setFont(f)
        return f

    @staticmethod
    def _num(v: float) -> str:
        return "‎" + _short(v)

    def _legend(self, p: QPainter, items: Sequence[Tuple[str, str]], y: float = 28.0) -> None:
        fm = QFontMetrics(p.font())
        total = sum(22 + fm.horizontalAdvance(n) + 20 for _c, n in items)
        x = max(8.0, (self.width() - total) / 2.0)
        for col, name in items:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(x, y + 5, 12, 10), 2, 2)
            p.setPen(QColor(COL["text"]))
            tw = fm.horizontalAdvance(name)
            p.drawText(QRectF(x + 18, y, tw + 8, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            x += 22 + tw + 20


class TornadoChart(_Chart):
    """Horizontal bars around a base value: for every variable the value at its low and at its high setting."""

    def __init__(self, title: str = "", height: int = 300):
        super().__init__(title, height)
        self.rows: List[Tuple[str, float, float]] = []
        self.base = 0.0
        self.legend: Tuple[str, str] = ("", "")
        self.base_label = ""

    def set_data(self, title: str, rows: Sequence[Tuple[str, float, float]], base: float,
                 legend: Tuple[str, str] = ("", ""), base_label: str = "") -> None:
        self.title, self.rows, self.base, self.legend, self.base_label = title, list(rows), base, legend, base_label
        self.setMinimumHeight(max(220, 84 + 34 * len(self.rows)))
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        f = self._frame(p)
        if not self.rows:
            p.end()
            return
        if self.legend[0]:
            self._legend(p, [(COL["red"], self.legend[0]), (COL["blue"], self.legend[1])])
        fm = QFontMetrics(f)
        w, h = self.width(), self.height()
        lab_w = min(190.0, max(fm.horizontalAdvance(n) for n, _a, _b in self.rows) + 14)
        left, right, top, bottom = lab_w + 8, 20.0, 58.0, 26.0
        pw, ph = w - left - right, h - top - bottom
        vals = [v for _n, a, b in self.rows for v in (a, b)] + [self.base]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.06 or 1.0
        lo, hi = lo - pad, hi + pad

        def X(v: float) -> float:
            return left + pw * (v - lo) / (hi - lo)

        n = len(self.rows)
        rh = ph / n
        grid = QPen(QColor(COL["line"]))
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            p.setPen(grid)
            p.drawLine(QPointF(X(v), top), QPointF(X(v), top + ph))
            p.setPen(QColor(COL["sub"]))
            p.drawText(QRectF(X(v) - 36, top + ph + 4, 72, 18), Qt.AlignmentFlag.AlignCenter, self._num(v))
        bx = X(self.base)
        for i, (name, a, b) in enumerate(self.rows):
            y = top + i * rh
            p.setPen(QColor(COL["text"]))
            p.drawText(QRectF(0, y, lab_w, rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(name, Qt.TextElideMode.ElideRight, int(lab_w)))
            p.setPen(Qt.PenStyle.NoPen)
            for val, col in ((a, COL["red"]), (b, COL["blue"])):
                x0, x1 = sorted((bx, X(val)))
                p.setBrush(QColor(col))
                half = (rh - 10) / 2
                # each side gets its own half-height strip so overlapping low/high bars stay readable
                yy = y + 5 + (0 if col == COL["red"] else half)
                p.drawRoundedRect(QRectF(x0, yy, max(1.5, x1 - x0), half), 2, 2)
        p.setPen(QPen(QColor(COL["navy"]), 1.6, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(bx, top - 4), QPointF(bx, top + ph))
        if self.base_label:
            p.setPen(QColor(COL["navy"]))
            p.drawText(QRectF(bx - 80, top - 20, 160, 16), Qt.AlignmentFlag.AlignCenter, self.base_label)
        p.end()


class SpiderChart(_Chart):
    """Lines of one result against the relative change of several inputs."""

    def __init__(self, title: str = "", height: int = 300):
        super().__init__(title, height)
        self.xs: List[float] = []
        self.series: List[Tuple[str, List[float]]] = []

    def set_data(self, title: str, xs: Sequence[float], series: Sequence[Tuple[str, Sequence[float]]]) -> None:
        self.title, self.xs, self.series = title, list(xs), [(n, list(v)) for n, v in series]
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        self._frame(p)
        if not self.xs or not self.series:
            p.end()
            return
        self._legend(p, [(PALETTE[i % len(PALETTE)], n) for i, (n, _v) in enumerate(self.series)])
        w, h = self.width(), self.height()
        left, right, top, bottom = 64.0, 18.0, 58.0, 34.0
        pw, ph = w - left - right, h - top - bottom
        vals = [v for _n, ys in self.series for v in ys]
        lo, hi = min(vals + [0.0]), max(vals + [0.0])
        pad = (hi - lo) * 0.06 or 1.0
        lo, hi = lo - pad, hi + pad
        x0, x1 = self.xs[0], self.xs[-1]

        def X(v: float) -> float:
            return left + pw * (v - x0) / ((x1 - x0) or 1.0)

        def Y(v: float) -> float:
            return top + ph * (hi - v) / (hi - lo)

        for k in range(5):
            v = lo + (hi - lo) * k / 4
            p.setPen(QColor(COL["line"]))
            p.drawLine(QPointF(left, Y(v)), QPointF(left + pw, Y(v)))
            p.setPen(QColor(COL["sub"]))
            p.drawText(QRectF(0, Y(v) - 9, left - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._num(v))
        p.setPen(QPen(QColor(COL["sub"]), 1.4))
        p.drawLine(QPointF(left, Y(0)), QPointF(left + pw, Y(0)))
        for x in self.xs:
            p.setPen(QColor(COL["text"]))
            p.drawText(QRectF(X(x) - 24, top + ph + 6, 48, 18), Qt.AlignmentFlag.AlignCenter, f"‎{x * 100:+.0f}%")
        for i, (_n, ys) in enumerate(self.series):
            col = QColor(PALETTE[i % len(PALETTE)])
            path = QPainterPath(QPointF(X(self.xs[0]), Y(ys[0])))
            for x, y in zip(self.xs[1:], ys[1:]):
                path.lineTo(QPointF(X(x), Y(y)))
            p.setPen(QPen(col, 2.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setBrush(col)
            p.setPen(QPen(QColor("#FFFFFF"), 1.0))
            for x, y in zip(self.xs, ys):
                p.drawEllipse(QPointF(X(x), Y(y)), 3.0, 3.0)
        p.end()


class HistogramChart(_Chart):
    """Histogram of a simulated result with its cumulative curve, percentile marks and the zero line."""

    def __init__(self, title: str = "", height: int = 330):
        super().__init__(title, height)
        self.counts: List[int] = []
        self.edges: List[float] = []
        self.cdf: List[float] = []
        self.marks: List[Tuple[str, float, str]] = []     # (label, value, colour)
        self.legend: Tuple[str, str] = ("", "")

    def set_data(self, title: str, counts: Sequence[int], edges: Sequence[float], cdf_x: Sequence[float],
                 marks: Sequence[Tuple[str, float, str]], legend: Tuple[str, str] = ("", "")) -> None:
        self.title, self.counts, self.edges, self.cdf, self.marks, self.legend = (
            title, list(counts), list(edges), list(cdf_x), list(marks), legend)
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        f = self._frame(p)
        if not self.counts:
            p.end()
            return
        if self.legend[0]:
            self._legend(p, [(COL["blue"], self.legend[0]), (COL["orange"], self.legend[1])])
        w, h = self.width(), self.height()
        left, right, top, bottom = 64.0, 52.0, 58.0, 40.0
        pw, ph = w - left - right, h - top - bottom
        lo, hi = self.edges[0], self.edges[-1]
        span = (hi - lo) or 1.0
        cmax = max(self.counts) or 1

        def X(v: float) -> float:
            return left + pw * (v - lo) / span

        for k in range(5):
            gy = top + ph - ph * k / 4
            p.setPen(QColor(COL["line"]))
            p.drawLine(QPointF(left, gy), QPointF(left + pw, gy))
            p.setPen(QColor(COL["sub"]))
            p.drawText(QRectF(0, gy - 9, left - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "‎" + f"{cmax * k / 4:.0f}")
            p.drawText(QRectF(left + pw + 6, gy - 9, right - 6, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"‎{25 * k}%")
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(self.counts):
            x0, x1 = X(self.edges[i]), X(self.edges[i + 1])
            bh = ph * c / cmax
            neg = self.edges[i + 1] <= 0
            p.setBrush(QColor(COL["red"] if neg else COL["blue"]))
            p.drawRect(QRectF(x0 + 0.5, top + ph - bh, max(1.0, x1 - x0 - 1.0), bh))
        # cumulative curve (right axis, 0..100 %)
        n = len(self.cdf)
        path = QPainterPath()
        for i, v in enumerate(self.cdf):
            q = QPointF(X(v), top + ph - ph * i / (n - 1))
            path.moveTo(q) if i == 0 else path.lineTo(q)
        p.setPen(QPen(QColor(COL["orange"]), 2.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        if lo < 0 < hi:
            p.setPen(QPen(QColor(COL["sub"]), 1.4))
            p.drawLine(QPointF(X(0), top), QPointF(X(0), top + ph))
        fm = QFontMetrics(f)
        for j, (label, v, col) in enumerate(self.marks):
            if not (lo <= v <= hi):
                continue
            p.setPen(QPen(QColor(col), 1.6, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(X(v), top), QPointF(X(v), top + ph))
            p.setPen(QColor(col))
            tw = fm.horizontalAdvance(label) + 8
            p.drawText(QRectF(X(v) - tw / 2, top - 16 - (j % 2) * 0, tw, 16), Qt.AlignmentFlag.AlignCenter, label)
        p.setPen(QColor(COL["sub"]))
        for k in range(5):
            v = lo + span * k / 4
            p.drawText(QRectF(X(v) - 36, top + ph + 4, 72, 18), Qt.AlignmentFlag.AlignCenter, self._num(v))
        p.end()


class LccChart(_Chart):
    """Present value of the cost of every year, stacked by component (investment, operation, replacement)."""

    def __init__(self, title: str = "", height: int = 300):
        super().__init__(title, height)
        self.years: List[Tuple[float, float, float]] = []
        self.names: Tuple[str, str, str] = ("", "", "")

    def set_data(self, title: str, years: Sequence[Tuple[float, float, float]], names: Tuple[str, str, str]) -> None:
        self.title, self.years, self.names = title, list(years), names
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        self._frame(p)
        if not self.years:
            p.end()
            return
        cols = (COL["navy"], COL["blue"], COL["orange"])
        self._legend(p, list(zip(cols, self.names)))
        w, h = self.width(), self.height()
        left, right, top, bottom = 64.0, 14.0, 58.0, 30.0
        pw, ph = w - left - right, h - top - bottom
        vmax = max(sum(y) for y in self.years) * 1.08 or 1.0
        for k in range(5):
            gy = top + ph - ph * k / 4
            p.setPen(QColor(COL["line"]))
            p.drawLine(QPointF(left, gy), QPointF(left + pw, gy))
            p.setPen(QColor(COL["sub"]))
            p.drawText(QRectF(0, gy - 9, left - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._num(vmax * k / 4))
        n = len(self.years)
        gw = pw / n
        step = max(1, n // 12)
        p.setPen(Qt.PenStyle.NoPen)
        for i, parts in enumerate(self.years):
            cx = left + (i + 0.5) * gw
            base = 0.0
            for col, v in zip(cols, parts):
                if v <= 0:
                    continue
                bh = ph * v / vmax
                p.setBrush(QColor(col))
                p.drawRect(QRectF(cx - gw * 0.34, top + ph - (base + bh), gw * 0.68, bh))
                base += bh
            if i % step == 0:
                p.setPen(QColor(COL["text"]))
                p.drawText(QRectF(cx - 20, top + ph + 6, 40, 18), Qt.AlignmentFlag.AlignCenter, str(i))
                p.setPen(Qt.PenStyle.NoPen)
        p.end()
