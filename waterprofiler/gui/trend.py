"""Trend charts and tables for time series: a bar/line chart, a collapsible peek under data-entry areas and the
indicator trends. Read-only: nothing here changes the plant."""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QHeaderView, QLabel, QToolButton, QVBoxLayout, QWidget

from .. import jcalendar as cal
from .. import timeseries as TS
from ..i18n import Translator
from ..model import Plant
from .tabs import make_table, put
from .theme import COL
from .widgets import _short

MAX_PEEK_SLICES = 48


class TsChart(QWidget):
    """One variable over time as bars or as a line; slices without data are left blank (a line breaks there)."""

    def __init__(self, height: int = 250):
        super().__init__()
        self.setMinimumHeight(height)
        self.title, self.labels, self.values, self.unit, self.mode = "", [], [], "", "bar"

    def set_data(self, title: str, labels: List[str], values: List[Optional[float]], unit: str) -> None:
        self.title, self.labels, self.values, self.unit = title, labels, values, unit
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = "line" if mode == "line" else "bar"
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QColor(COL["navy"]))
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 2, w, 24), Qt.AlignmentFlag.AlignCenter, f"{self.title}  ({self.unit})" if self.unit else self.title)
        f.setBold(False)
        p.setFont(f)
        vals = [v for v in self.values if v is not None]
        if not vals:
            p.setPen(QColor(COL["sub"]))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "—")
            p.end()
            return
        left, right, top, bottom = 64, 14, 34, 34
        pw, ph = w - left - right, h - top - bottom
        lo, hi = min(0.0, min(vals)), max(0.0, max(vals))
        if hi == lo:
            hi = lo + 1.0
        span = hi - lo

        def Y(v: float) -> float:
            return top + ph * (1 - (v - lo) / span)

        for k in range(5):
            v = lo + span * k / 4
            p.setPen(QPen(QColor(COL["line"]), 1))
            p.drawLine(QPointF(left, Y(v)), QPointF(left + pw, Y(v)))
            p.setPen(QColor(COL["sub"]))
            p.drawText(QRectF(0, Y(v) - 9, left - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "‎" + _short(v))
        n = len(self.values)
        gw = pw / n
        step = max(1, -(-n // max(1, int(pw // 78))))
        blue = QColor(COL["blue"])
        if self.mode == "line":
            p.setPen(QPen(blue, 2))
            prev = None
            for i, v in enumerate(self.values):
                if v is None:
                    prev = None
                    continue
                pt = QPointF(left + (i + 0.5) * gw, Y(v))
                if prev is not None:
                    p.drawLine(prev, pt)
                prev = pt
            p.setBrush(blue)
            for i, v in enumerate(self.values):
                if v is not None:
                    p.drawEllipse(QPointF(left + (i + 0.5) * gw, Y(v)), 3.2, 3.2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(blue)
        for i, v in enumerate(self.values):
            cx = left + (i + 0.5) * gw
            if self.mode == "bar" and v is not None:
                y0, y1 = Y(max(v, 0)), Y(min(v, 0))
                p.drawRoundedRect(QRectF(cx - gw * 0.34, y0, gw * 0.68, max(1.0, y1 - y0)), 2, 2)
            if i % step == 0:
                p.setPen(QColor(COL["text"]))
                p.drawText(QRectF(cx - 34, top + ph + 6, 68, 18), Qt.AlignmentFlag.AlignCenter, self.labels[i])
                p.setPen(Qt.PenStyle.NoPen)
        p.end()


def trend_slices(plant: Plant, lang: str) -> List[cal.Slice]:
    """Monthly slices over the span of the plant's data (yearly when that would be more than MAX_PEEK_SLICES)."""
    span = TS.data_span(plant)
    if not span:
        return []
    calendar = plant.site.calendar or "jalali"
    sl = cal.slices(span[0], span[1], "month", calendar, lang)
    if len(sl) > MAX_PEEK_SLICES:
        sl = cal.slices(span[0], span[1], "year", calendar, lang)
    return sl


def slice_labels(plant: Plant, sl: Sequence[cal.Slice]) -> List[str]:
    calendar = plant.site.calendar or "jalali"
    yearly = len(sl) > 1 and (sl[0].end - sl[0].start).days > 300
    out = []
    for s in sl:
        y, m, _d = cal.parts(s.start, calendar)
        out.append(f"{y}" if yearly else f"{y}/{m:02d}")
    return out


def key_values(plant: Plant, key: str, sl: Sequence[cal.Slice]) -> List[Optional[float]]:
    if key == "total:production":
        return TS.total_production_slices(plant, sl)
    return TS.slice_values(plant, key, sl)


def key_unit(plant: Plant, key: str, lang: str) -> str:
    if key == "total:production":
        return plant.production_unit
    sp = TS.spec_of(plant, key)
    return TS.unit_text(sp.unit, lang, plant) if sp else ""


def key_label(plant: Plant, key: str, lang: str) -> str:
    if key == "total:production":
        return "تولید کل (جمع محصولات)" if lang == "fa" else "Total production (sum of products)"
    sp = TS.spec_of(plant, key)
    return sp.label(lang) if sp else key


class ModeBox(QComboBox):
    """Bar / line choice shared by every trend view (user selectable)."""

    def __init__(self, t: Translator):
        super().__init__()
        self.addItem(t("tr_bar"), "bar")
        self.addItem(t("tr_line"), "line")
        self.setMinimumWidth(110)


class TrendPeek(QWidget):
    """Collapsed by default: a button under a data-entry area that opens a chart and a table of the series there.

    ``keys_fn`` returns the series keys offered (e.g. the sources of the table above); a single key shows no chooser."""

    def __init__(self, t: Translator, keys_fn: Callable[[Plant], Sequence[str]]):
        super().__init__()
        self.t, self.keys_fn = t, keys_fn
        self.plant: Optional[Plant] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)
        self.btn = QToolButton()
        self.btn.setCheckable(True)
        self.btn.setText(t("tr_show"))
        self.btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.toggled.connect(self._toggled)
        lay.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        row = QHBoxLayout()
        self.var = QComboBox()
        self.var.setMinimumWidth(220)
        self.mode = ModeBox(t)
        row.addWidget(self.var, 1)
        row.addWidget(self.mode)
        bl.addLayout(row)
        self.chart = TsChart(210)
        bl.addWidget(self.chart)
        self.tb = make_table([t("ts_col_period"), t("tr_value")])
        self.tb.setMaximumHeight(210)
        self.tb.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        bl.addWidget(self.tb)
        self.note = QLabel("")
        self.note.setObjectName("cardnote")
        self.note.setWordWrap(True)
        bl.addWidget(self.note)
        self.body.setVisible(False)
        lay.addWidget(self.body)
        self.var.currentIndexChanged.connect(self._draw)
        self.mode.currentIndexChanged.connect(self._draw)

    def set_plant(self, plant: Plant) -> None:
        self.plant = plant
        cur = self.var.currentData()
        keys = list(self.keys_fn(plant))
        self.var.blockSignals(True)
        self.var.clear()
        for k in keys:
            self.var.addItem(key_label(plant, k, self.t.lang), k)
        i = self.var.findData(cur)
        self.var.setCurrentIndex(i if i >= 0 else 0)
        self.var.blockSignals(False)
        self.var.setVisible(len(keys) > 1)
        self.setVisible(bool(keys))
        if self.body.isVisible():
            self._draw()

    def _toggled(self, on: bool) -> None:
        self.body.setVisible(on)
        self.btn.setText(self.t("tr_hide") if on else self.t("tr_show"))
        if on:
            self._draw()

    def _draw(self, *_a) -> None:
        plant, key = self.plant, self.var.currentData()
        if plant is None or key is None:
            return
        sl = trend_slices(plant, self.t.lang)
        vals = key_values(plant, key, sl) if sl else []
        labels = slice_labels(plant, sl)
        self.chart.set_mode(self.mode.currentData())
        self.chart.set_data(key_label(plant, key, self.t.lang), labels, vals, key_unit(plant, key, self.t.lang))
        self.tb.setRowCount(len(sl))
        for r, (lab, v) in enumerate(zip(labels, vals)):
            put(self.tb, r, 0, lab)
            put(self.tb, r, 1, "—" if v is None else f"{v:,.2f}", True)
        self.note.setText("" if any(v is not None for v in vals) else self.t("tr_none"))


def with_data(plant: Plant, keys: Sequence[str]) -> List[str]:
    """The keys that have a series (or are the total production of products that have one)."""
    out = []
    for k in keys:
        if k == "total:production":
            if any(plant.series.get(f"production:{p.name}") for p in plant.site.products):
                out.append(k)
        elif plant.series.get(k):
            out.append(k)
    return out


def _ratio(a: Sequence[Optional[float]], b: Sequence[Optional[float]], k: float = 1.0) -> List[Optional[float]]:
    return [None if x is None or y is None or y == 0 else k * x / y for x, y in zip(a, b)]


def measures(plant: Plant, sl: Sequence[cal.Slice]) -> List[Tuple[str, str, str, List[Optional[float]]]]:
    """Indicators that can be followed over time: (id, text key, unit, values per slice). Only those with data are listed."""
    intake = TS.total_intake_slices(plant, sl)
    prod = TS.total_production_slices(plant, sl)
    el = TS.slice_values(plant, "energy:el", sl)
    loss = TS.slice_values(plant, "loss:measured", sl)
    out = [("intake", "tr_m_intake", "m³", intake), ("prod", "tr_m_prod", plant.production_unit, prod),
           ("per_unit", "tr_m_per_unit", f"m³/{plant.production_unit}", _ratio(intake, prod)),
           ("energy", "tr_m_energy", "kWh/m³", _ratio(el, intake)), ("loss", "tr_m_loss", "%", _ratio(loss, intake, 100.0))]
    return [m for m in out if any(v is not None for v in m[3])]


class IndicatorTrend(QWidget):
    """Chart and table of the time-based indicators on the Indicators page (bars or line, chosen by the user)."""

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        row = QHBoxLayout()
        self.var = QComboBox()
        self.var.setMinimumWidth(260)
        self.mode = ModeBox(t)
        row.addWidget(self.var, 1)
        row.addWidget(self.mode)
        lay.addLayout(row)
        self.chart = TsChart(250)
        lay.addWidget(self.chart)
        self.tb = make_table([t("ts_col_period"), t("tr_value")])
        self.tb.setMaximumHeight(240)
        lay.addWidget(self.tb)
        self.note = QLabel(t("tr_none"))
        self.note.setObjectName("cardnote")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self._items: List[Tuple[str, str, str, List[Optional[float]]]] = []
        self._labels: List[str] = []
        self.var.currentIndexChanged.connect(self._draw)
        self.mode.currentIndexChanged.connect(self._draw)

    def set_plant(self, plant: Plant) -> None:
        self.plant = plant
        sl = trend_slices(plant, self.t.lang)
        self._items = measures(plant, sl) if sl else []
        self._labels = slice_labels(plant, sl)
        cur = self.var.currentData()
        self.var.blockSignals(True)
        self.var.clear()
        for mid, tk, _u, _v in self._items:
            self.var.addItem(self.t(tk), mid)
        i = self.var.findData(cur)
        self.var.setCurrentIndex(i if i >= 0 else 0)
        self.var.blockSignals(False)
        self._draw()

    def _draw(self, *_a) -> None:
        cur = next((m for m in self._items if m[0] == self.var.currentData()), None)
        self.chart.set_mode(self.mode.currentData())
        if cur is None:
            self.chart.set_data("", [], [], "")
            self.tb.setRowCount(0)
            self.note.setVisible(True)
            return
        self.note.setVisible(False)
        _id, tk, unit, vals = cur
        self.chart.set_data(self.t(tk), self._labels, vals, unit)
        self.tb.setRowCount(len(vals))
        for r, (lab, v) in enumerate(zip(self._labels, vals)):
            put(self.tb, r, 0, lab)
            put(self.tb, r, 1, "—" if v is None else f"{v:,.3f}", True)
