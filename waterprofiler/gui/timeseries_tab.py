"""Time-series page: enter and review data for any period, cut into monthly or yearly slices."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QListView, QListWidget, QListWidgetItem, QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import jcalendar as cal
from .. import timeseries as TS
from .. import ts_excel as XL
from ..i18n import Translator
from ..model import Plant
from ..numparse import parse_float
from .tabs import WARN_BG, _Scroll, make_table, put
from .theme import COL
from .widgets import button, card

MAX_SLICES = 600
DEFAULT_ON = ("production", "source:", "outlet:")


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.6g}"


class CalDate(QWidget):
    """Year / month / day pickers for the Jalali or the Gregorian calendar."""

    changed = Signal()

    def __init__(self, calendar: str, lang: str):
        super().__init__()
        self.cal, self.lang = calendar, lang
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.year = QSpinBox()
        self.year.setRange(1200, 2600)
        self.year.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.year.setMinimumWidth(70)
        self.month = QComboBox()
        self.day = QSpinBox()
        self.day.setRange(1, 31)
        self.day.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.day.setMinimumWidth(48)
        for w in (self.year, self.month, self.day):
            lay.addWidget(w)
        self._fill_months()
        self.year.valueChanged.connect(self._edited)
        self.month.currentIndexChanged.connect(self._edited)
        self.day.valueChanged.connect(self._edited)

    def _fill_months(self) -> None:
        self.month.blockSignals(True)
        cur = self.month.currentIndex()
        self.month.clear()
        for m in range(1, 13):
            self.month.addItem(cal.month_name(self.cal, m, self.lang))
        self.month.setCurrentIndex(max(0, cur))
        self.month.blockSignals(False)

    def _edited(self, *_a) -> None:
        self.day.blockSignals(True)
        self.day.setMaximum(cal.month_days(self.cal, self.year.value(), self.month.currentIndex() + 1))
        self.day.blockSignals(False)
        self.changed.emit()

    def date(self) -> date:
        return cal.make_date(self.cal, self.year.value(), self.month.currentIndex() + 1, self.day.value())

    def set_date(self, d: date) -> None:
        y, m, dd = cal.parts(d, self.cal)
        for w in (self.year, self.month, self.day):
            w.blockSignals(True)
        self.year.setValue(y)
        self.month.setCurrentIndex(m - 1)
        self.day.setMaximum(cal.month_days(self.cal, y, m))
        self.day.setValue(dd)
        for w in (self.year, self.month, self.day):
            w.blockSignals(False)

    def set_calendar(self, calendar: str) -> None:
        d = self.date()
        self.cal = calendar
        self._fill_months()
        self.set_date(d)


class PasteTable(QTableWidget):
    """Table that accepts Ctrl+V of spreadsheet cells and Delete to clear."""

    pasted = Signal(int, int, list)       # first row, first column, rows of strings
    cleared = Signal(list)                # [(row, col), ...]

    def keyPressEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        if ev.matches(QKeySequence.StandardKey.Paste):
            text = QGuiApplication.clipboard().text()
            rows = [line.split("\t") for line in text.replace("\r", "").split("\n") if line != ""]
            cur = self.currentIndex()
            if rows and cur.isValid():
                self.pasted.emit(cur.row(), cur.column(), rows)
            return
        if ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.state() != QAbstractItemView.State.EditingState:
            self.cleared.emit([(i.row(), i.column()) for i in self.selectedIndexes()])
            return
        super().keyPressEvent(ev)


class TsChart(QWidget):
    """Bars per slice for the chosen variable; empty slices are left blank."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(250)
        self.title, self.labels, self.values, self.unit = "", [], [], ""

    def set_data(self, title: str, labels: List[str], values: List[Optional[float]], unit: str) -> None:
        self.title, self.labels, self.values, self.unit = title, labels, values, unit
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
            from .widgets import _short
            p.drawText(QRectF(0, Y(v) - 9, left - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "‎" + _short(v))
        n = len(self.values)
        gw = pw / n
        step = max(1, -(-n // max(1, int(pw // 78))))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(COL["blue"]))
        for i, v in enumerate(self.values):
            cx = left + (i + 0.5) * gw
            if v is not None:
                y0, y1 = Y(max(v, 0)), Y(min(v, 0))
                p.drawRoundedRect(QRectF(cx - gw * 0.34, y0, gw * 0.68, max(1.0, y1 - y0)), 2, 2)
            if i % step == 0:
                p.setPen(QColor(COL["text"]))
                p.drawText(QRectF(cx - 34, top + ph + 6, 68, 18), Qt.AlignmentFlag.AlignCenter, self.labels[i])
                p.setPen(Qt.PenStyle.NoPen)
        p.end()


class ApplyDialog(QDialog):
    def __init__(self, t: Translator, plant: Plant, changes: List[TS.Change], parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("ts_apply_title"))
        self.resize(900, 520)
        lay = QVBoxLayout(self)
        intro = QLabel(t("ts_apply_intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        tb = make_table([t("ts_col_var"), t("ts_col_target"), t("ts_col_old"), t("ts_col_new"), t("ts_col_cov"), t("ts_col_note")])
        specs = {s.key: s for s in TS.catalog(plant)}
        tb.setRowCount(len(changes))
        for r, ch in enumerate(changes):
            sp = specs.get(ch.key)
            put(tb, r, 0, sp.label(t.lang) if sp else ch.key)
            put(tb, r, 1, where_text(t, ch.where))
            put(tb, r, 2, "—" if ch.old is None else _fmt(ch.old), True)
            put(tb, r, 3, "—" if ch.new is None else _fmt(ch.new), True, bold=ch.new is not None)
            put(tb, r, 4, f"{100 * ch.coverage:.0f}%", True)
            put(tb, r, 5, t("ts_note_" + ch.note) if ch.note else "", bg=WARN_BG if ch.note else None)
        lay.addWidget(tb, 1)
        self.n_apply = sum(1 for c in changes if c.new is not None)
        bb = QDialogButtonBox()
        ok = bb.addButton(t("ts_apply_btn", n=self.n_apply), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setEnabled(self.n_apply > 0)
        bb.addButton(t("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


def where_text(t: Translator, where: str) -> str:
    parts = where.split(":")
    if where == "production_per_year":
        return t("ts_tg_production")
    if parts[0] in ("source", "outlet"):
        what = t("ts_tg_metered") if parts[-1] == "metered" else t("ts_tg_price")
        return f"{t('ts_tg_' + parts[0])} «{parts[1]}» — {what}"
    if parts[0] == "sub":
        return f"{parts[1]} — {t('ts_tg_sub_' + parts[2])}"
    if parts[0] == "costs":
        return t("ts_tg_cost_" + parts[1])
    if parts[0] == "profile":
        return t("ts_tg_profile") + ": " + parts[1]
    return where


class TimeTab(_Scroll):
    model_changed = Signal()               # a period was applied to the annual model
    # shown by default: the data that really changes month by month
    DEFAULT_GROUPS = ("production", "source", "outlet", "loss", "price")

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._loading = False
        self.slices: List[cal.Slice] = []
        self.cols: List[TS.VarSpec] = []
        lang = t.lang

        # ---- period
        self.cal_combo = QComboBox()
        self.cal_combo.addItem(t("cal_jalali"), "jalali")
        self.cal_combo.addItem(t("cal_gregorian"), "gregorian")
        self.step_combo = QComboBox()
        self.step_combo.addItem(t("ts_monthly"), "month")
        self.step_combo.addItem(t("ts_yearly"), "year")
        self.start = CalDate("jalali", lang)
        self.end = CalDate("jalali", lang)
        row = QHBoxLayout()
        row.setSpacing(14)
        for text, w in ((t("ts_calendar"), self.cal_combo), (t("ts_slice"), self.step_combo),
                        (t("ts_start"), self.start), (t("ts_end"), self.end)):
            box = QVBoxLayout()
            lab = QLabel(text)
            lab.setObjectName("cardnote")
            box.addWidget(lab)
            box.addWidget(w)
            row.addLayout(box)
        row.addStretch(1)
        presets = QHBoxLayout()
        for key, fn in (("ts_p_year", self._preset_year), ("ts_p_last12", self._preset_last12), ("ts_p_data", self._preset_data)):
            presets.addWidget(button(t(key), "", fn))
        presets.addStretch(1)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addLayout(row)
        hl.addLayout(presets)
        self.lay.addWidget(card(t("ts_period"), holder, note=t("ts_period_note")))

        # ---- variables
        pre = QHBoxLayout()
        for key, kind in (("ts_pre_water", "water"), ("ts_pre_loss", "loss"), ("ts_pre_prod", "prod"),
                          ("ts_pre_price", "price"), ("ts_pre_other", "other")):
            pre.addWidget(button(t(key), "", lambda _=False, k=kind: self._add_preset(k)))
        pre.addWidget(button(t("ts_pre_none"), "ghost", lambda _=False: self.set_checked([])))
        pre.addStretch(1)
        pre_w = QWidget()
        pre_w.setLayout(pre)
        pre.setContentsMargins(0, 0, 0, 0)
        self.var_list = QListWidget()
        # items run top-to-bottom and wrap into columns, so every group is visible without scrolling
        self.var_list.setFlow(QListView.Flow.TopToBottom)
        self.var_list.setWrapping(True)
        self.var_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.var_list.setGridSize(QSize(330, 32))
        self.var_list.setStyleSheet(
            "QListWidget::indicator{width:16px;height:16px;border:1.5px solid #8A94A6;border-radius:4px;background:#FFFFFF;}"
            f"QListWidget::indicator:checked{{background:{COL['blue']};border-color:{COL['blue']};}}")
        self.var_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.var_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.var_list.itemChanged.connect(self._vars_changed)
        self.lay.addWidget(card(t("ts_vars"), pre_w, self.var_list, note=t("ts_vars_note")))

        # ---- table
        self.msg = QLabel("")
        self.msg.setObjectName("cardnote")
        self.msg.setWordWrap(True)
        self.tb = PasteTable(0, 2)
        self.tb.setAlternatingRowColors(True)
        self.tb.setShowGrid(False)
        self.tb.verticalHeader().setVisible(False)
        self.tb.verticalHeader().setDefaultSectionSize(34)
        self.tb.setMinimumHeight(420)
        self.tb.itemChanged.connect(self._cell_edited)
        self.tb.pasted.connect(self._paste)
        self.tb.cleared.connect(self._clear_cells)
        io = QHBoxLayout()
        io.addWidget(button(t("ts_x_export"), "primary", self.export_xlsx_dialog))
        io.addWidget(button(t("ts_x_import"), "", self.import_xlsx_dialog))
        io.addWidget(button(t("ts_import"), "", self.import_csv_dialog))
        io.addWidget(button(t("ts_export"), "", self.export_csv_dialog))
        io.addStretch(1)
        iw = QWidget()
        il = QVBoxLayout(iw)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(self.msg)
        il.addWidget(self.tb)
        il.addLayout(io)
        self.lay.addWidget(card(t("ts_data"), iw, note=t("ts_data_note")))

        # ---- chart
        self.chart_var = QComboBox()
        self.chart_var.currentIndexChanged.connect(self._draw_chart)
        self.chart = TsChart()
        self.lay.addWidget(card(t("ts_chart"), self.chart_var, self.chart))

        # ---- window / apply
        self.w_start = CalDate("jalali", lang)
        self.w_end = CalDate("jalali", lang)
        wrow = QHBoxLayout()
        wrow.setSpacing(14)
        for text, w in ((t("ts_start"), self.w_start), (t("ts_end"), self.w_end)):
            box = QVBoxLayout()
            lab = QLabel(text)
            lab.setObjectName("cardnote")
            box.addWidget(lab)
            box.addWidget(w)
            wrow.addLayout(box)
        wrow.addWidget(button(t("ts_w_from_table"), "", self._window_from_table))
        wrow.addWidget(button(t("ts_w_apply"), "primary", lambda: self.apply_window(True)))
        wrow.addStretch(1)
        self.w_info = QLabel("")
        self.w_info.setObjectName("cardnote")
        self.w_info.setWordWrap(True)
        ww = QWidget()
        wl = QVBoxLayout(ww)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addLayout(wrow)
        wl.addWidget(self.w_info)
        self.lay.addWidget(card(t("ts_window"), ww, note=t("ts_window_note")))
        self.lay.addStretch(1)

        self.cal_combo.currentIndexChanged.connect(self._calendar_changed)
        self.step_combo.currentIndexChanged.connect(self._rebuild)
        self.start.changed.connect(self._rebuild)
        self.end.changed.connect(self._rebuild)
        self.w_start.changed.connect(self._window_edited)
        self.w_end.changed.connect(self._window_edited)

    # ------------------------------------------------------------------ plant in / out
    def refresh(self, plant: Plant) -> None:
        new_plant = plant is not self.plant
        self.plant = plant
        self._loading = True
        calendar = plant.site.calendar if plant.site.calendar in cal.CALENDARS else "jalali"
        self.cal_combo.setCurrentIndex(self.cal_combo.findData(calendar))
        if new_plant or self.start.cal != calendar:
            for w in (self.start, self.end, self.w_start, self.w_end):
                w.cal = calendar
                w._fill_months()
            span = TS.data_span(plant)
            if span:
                self.start.set_date(span[0])
                self.end.set_date(span[1])
            else:
                self._set_year_defaults(self.start, self.end)
            win = TS.window_of(plant)
            if win:
                self.w_start.set_date(win[0])
                self.w_end.set_date(win[1])
            else:
                self._set_year_defaults(self.w_start, self.w_end)
        self._fill_vars(plant)
        self._loading = False
        self._rebuild()

    def _set_year_defaults(self, a: CalDate, b: CalDate) -> None:
        y = cal.parts(date.today(), a.cal)[0]
        a.set_date(cal.make_date(a.cal, y, 1, 1))
        b.set_date(cal.make_date(a.cal, y, 12, 31))

    def _fill_vars(self, plant: Plant) -> None:
        old = {k for k in self.checked_keys()} if self.var_list.count() else None
        self.var_list.blockSignals(True)
        self.var_list.clear()
        lang = self.t.lang
        group = None
        for sp in TS.catalog(plant):
            if sp.group != group:
                group = sp.group
                h = QListWidgetItem(TS.GROUP_TITLE[group][0 if lang == "fa" else 1])
                h.setFlags(Qt.ItemFlag.ItemIsEnabled)
                f = h.font()
                f.setBold(True)
                h.setFont(f)
                self.var_list.addItem(h)
            it = QListWidgetItem(f"{sp.label(lang)}   [{TS.unit_text(sp.unit, lang, plant)}]")
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            on = (sp.key in old) if old is not None else (sp.group in self.DEFAULT_GROUPS or bool(plant.series.get(sp.key)))
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, sp.key)
            self.var_list.addItem(it)
        self.var_list.blockSignals(False)
        rows = -(-self.var_list.count() // 3) + 1               # three columns plus one row of slack
        self.var_list.setFixedHeight(max(160, rows * 32 + 12))

    def checked_keys(self) -> List[str]:
        out = []
        for i in range(self.var_list.count()):
            it = self.var_list.item(i)
            k = it.data(Qt.ItemDataRole.UserRole)
            if k and it.checkState() == Qt.CheckState.Checked:
                out.append(k)
        return out

    @staticmethod
    def preset_match(kind: str, spec: "TS.VarSpec") -> bool:
        k = spec.key
        if kind == "water":
            return spec.group in ("source", "outlet", "subsystem")
        if kind == "loss":
            return spec.group == "loss"
        if kind == "prod":
            return spec.group == "production"
        if kind == "price":
            return spec.group == "price"
        return spec.group in ("energy", "env", "site", "quality")

    def _add_preset(self, kind: str) -> None:
        if self.plant is None:
            return
        keys = set(self.checked_keys())
        keys |= {sp.key for sp in TS.catalog(self.plant) if self.preset_match(kind, sp)}
        self.set_checked(list(keys))

    def set_checked(self, keys: List[str]) -> None:
        self.var_list.blockSignals(True)
        for i in range(self.var_list.count()):
            it = self.var_list.item(i)
            k = it.data(Qt.ItemDataRole.UserRole)
            if k:
                it.setCheckState(Qt.CheckState.Checked if k in keys else Qt.CheckState.Unchecked)
        self.var_list.blockSignals(False)
        self._rebuild()

    # ------------------------------------------------------------------ period controls
    def _calendar_changed(self, *_a) -> None:
        if self._loading or self.plant is None:
            return
        calendar = self.cal_combo.currentData()
        self.plant.site.calendar = calendar
        self._loading = True
        for w in (self.start, self.end, self.w_start, self.w_end):
            w.set_calendar(calendar)
        self._loading = False
        self._rebuild()

    def _preset_year(self) -> None:
        a, b = self.start, self.end
        y = cal.parts(self.start.date(), a.cal)[0]
        self._loading = True
        a.set_date(cal.make_date(a.cal, y, 1, 1))
        b.set_date(cal.make_date(a.cal, y, 12, 31))
        self._loading = False
        self._rebuild()

    def _preset_last12(self) -> None:
        span = TS.data_span(self.plant) if self.plant else None
        end = span[1] if span else date.today()
        y, m, _d = cal.parts(end, self.start.cal)
        last = cal.make_date(self.start.cal, y, m, cal.month_days(self.start.cal, y, m))
        first_y, first_m = (y - 1, m + 1) if m < 12 else (y, 1)
        self._loading = True
        self.start.set_date(cal.make_date(self.start.cal, first_y, first_m, 1))
        self.end.set_date(last)
        self._loading = False
        self._rebuild()

    def _preset_data(self) -> None:
        span = TS.data_span(self.plant) if self.plant else None
        if span:
            self._loading = True
            self.start.set_date(span[0])
            self.end.set_date(span[1])
            self._loading = False
            self._rebuild()

    def _window_from_table(self) -> None:
        self.w_start.set_date(self.start.date())
        self.w_end.set_date(self.end.date())

    def _window_edited(self) -> None:
        if self._loading or self.plant is None:
            return
        a, b = self.w_start.date(), self.w_end.date()
        if a <= b:
            self.plant.window = {"start": a.isoformat(), "end": b.isoformat()}
        self._window_info()

    def _window_info(self) -> None:
        a, b = self.w_start.date(), self.w_end.date()
        days = (b - a).days + 1
        self.w_info.setText(self.t("ts_w_info", days=days) if b >= a else self.t("ts_bad_range"))

    # ------------------------------------------------------------------ table
    def _specs(self) -> Dict[str, TS.VarSpec]:
        return {s.key: s for s in TS.catalog(self.plant)} if self.plant else {}

    def _vars_changed(self, *_a) -> None:
        self._rebuild()

    def _rebuild(self, *_a) -> None:
        if self._loading or self.plant is None:
            return
        plant, t = self.plant, self.t
        a, b = self.start.date(), self.end.date()
        self.msg.setText("")
        if b < a:
            self.msg.setText(t("ts_bad_range"))
            self.slices, self.cols = [], []
            self.tb.setRowCount(0)
            return
        step = self.step_combo.currentData()
        calendar = self.start.cal
        self.slices = cal.slices(a, b, step, calendar, t.lang)
        if len(self.slices) > MAX_SLICES:
            self.slices = self.slices[:MAX_SLICES]
            self.msg.setText(t("ts_too_long", n=MAX_SLICES))
        specs = self._specs()
        self.cols = [specs[k] for k in self.checked_keys() if k in specs]
        self._loading = True
        self.tb.clear()
        self.tb.setColumnCount(2 + len(self.cols))
        self.tb.setRowCount(len(self.slices) + 1)
        heads = [t("ts_col_period"), t("ts_col_days")] + [
            sp.label(t.lang) + "\n[" + TS.unit_text(sp.unit, t.lang, plant) + "]" for sp in self.cols]
        self.tb.setHorizontalHeaderLabels(heads)
        hh = self.tb.horizontalHeader()
        hh.setFixedHeight(58)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(2, 2 + len(self.cols)):
            self.tb.setColumnWidth(c, 190)
            hi = self.tb.horizontalHeaderItem(c)
            if hi is not None:
                hi.setToolTip(self.cols[c - 2].label(t.lang))
        for r, s in enumerate(self.slices):
            lab = QTableWidgetItem(s.label + ("  *" if s.partial else ""))
            lab.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if s.partial:
                lab.setToolTip(t("ts_partial_tip"))
            self.tb.setItem(r, 0, lab)
            d = QTableWidgetItem(str(s.days))
            d.setFlags(Qt.ItemFlag.ItemIsEnabled)
            d.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tb.setItem(r, 1, d)
            for c in range(len(self.cols)):
                self._render_cell(r, 2 + c)
        self._render_footer()
        self._loading = False
        cur = self.chart_var.currentData()
        self.chart_var.blockSignals(True)
        self.chart_var.clear()
        for sp in self.cols:
            self.chart_var.addItem(sp.label(t.lang), sp.key)
        i = self.chart_var.findData(cur)
        self.chart_var.setCurrentIndex(i if i >= 0 else 0)
        self.chart_var.blockSignals(False)
        self._draw_chart()
        self._window_info()

    def _cell_value(self, r: int, c: int):
        sp = self.cols[c - 2]
        s = self.slices[r]
        return TS.value_in(self.plant.series.get(sp.key, []), s.start, s.end, sp.agg)

    def _render_cell(self, r: int, c: int) -> None:
        v, cov = self._cell_value(r, c)
        it = QTableWidgetItem(_fmt(v))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if v is not None and cov < 0.999:
            it.setBackground(WARN_BG)
            it.setToolTip(self.t("ts_cov_tip", pct=f"{100 * cov:.0f}"))
        self.tb.setItem(r, c, it)

    def _render_footer(self) -> None:
        r = len(self.slices)
        lab = QTableWidgetItem(self.t("ts_footer"))
        lab.setFlags(Qt.ItemFlag.ItemIsEnabled)
        f = lab.font()
        f.setBold(True)
        lab.setFont(f)
        self.tb.setItem(r, 0, lab)
        blank = QTableWidgetItem("")
        blank.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.tb.setItem(r, 1, blank)
        for c, sp in enumerate(self.cols, start=2):
            pts = self.plant.series.get(sp.key, [])
            got = [(TS.value_in(pts, x.start, x.end, sp.agg)[0], x.days) for x in self.slices]
            got = [(val, d) for val, d in got if val is not None]
            if not got:
                v = None
            elif sp.agg == "sum":
                v = sum(val for val, _ in got)
            else:
                v = sum(val * d for val, d in got) / sum(d for _, d in got)
            it = QTableWidgetItem(_fmt(v))
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            self.tb.setItem(r, c, it)

    def _draw_chart(self, *_a) -> None:
        key = self.chart_var.currentData()
        sp = next((s for s in self.cols if s.key == key), None)
        if sp is None:
            self.chart.set_data("", [], [], "")
            return
        vals = [self._cell_value(r, 2 + self.cols.index(sp))[0] for r in range(len(self.slices))]
        calendar = self.start.cal
        labels = []
        for s in self.slices:
            y, m, _d = cal.parts(s.start, calendar)
            labels.append(f"{y}" if self.step_combo.currentData() == "year" else f"{y}/{m:02d}")
        self.chart.set_data(sp.label(self.t.lang), labels, vals, TS.unit_text(sp.unit, self.t.lang, self.plant))

    # ------------------------------------------------------------------ editing
    def set_cell(self, r: int, c: int, text: str, ask: bool = True) -> bool:
        """Store the value typed into slice r, variable column c. Returns False if the text is not a number."""
        sp, s = self.cols[c - 2], self.slices[r]
        text = text.strip()
        v = parse_float(text)
        if text and v is None:
            return False
        if ask and v is not None and self._has_finer_data(sp.key, s):
            q = QMessageBox.question(self, self.t("app_title"), self.t("ts_finer_q"),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if q != QMessageBox.StandardButton.Yes:
                return True
        TS.put(self.plant, sp.key, s.start, s.end, v)
        return True

    def _has_finer_data(self, key: str, s: cal.Slice) -> bool:
        for p in self.plant.series.get(key, []):
            a, b = date.fromisoformat(p.start), date.fromisoformat(p.end)
            if b >= s.start and a <= s.end and (b - a).days + 1 < s.days and a >= s.start and b <= s.end:
                return True
        return False

    def _cell_edited(self, item: QTableWidgetItem) -> None:
        if self._loading or self.plant is None:
            return
        r, c = item.row(), item.column()
        if r >= len(self.slices) or c < 2:
            return
        ok = self.set_cell(r, c, item.text())
        self._loading = True
        self._render_cell(r, c)
        self._render_footer()
        self._loading = False
        self._draw_chart()
        if not ok:
            self.msg.setText(self.t("ts_not_number"))

    def _paste(self, r0: int, c0: int, rows: List[List[str]]) -> None:
        if self.plant is None or c0 < 2:
            return
        bad = 0
        for i, line in enumerate(rows):
            for j, text in enumerate(line):
                r, c = r0 + i, c0 + j
                if r < len(self.slices) and c < 2 + len(self.cols):
                    if not self.set_cell(r, c, text, ask=False):
                        bad += 1
        self._rebuild()
        self.msg.setText(self.t("ts_not_number") if bad else "")

    def _clear_cells(self, cells: List[tuple]) -> None:
        if self.plant is None:
            return
        for r, c in cells:
            if r < len(self.slices) and 2 <= c < 2 + len(self.cols):
                self.set_cell(r, c, "", ask=False)
        self._rebuild()

    # ------------------------------------------------------------------ apply to the annual model
    def apply_window(self, ask: bool = True) -> int:
        """Take the window as the basis of the annual model. Returns the number of values written."""
        if self.plant is None:
            return 0
        a, b = self.w_start.date(), self.w_end.date()
        if b < a:
            self.w_info.setText(self.t("ts_bad_range"))
            return 0
        self.plant.window = {"start": a.isoformat(), "end": b.isoformat()}
        changes = TS.plan_changes(self.plant, a, b)
        if not changes:
            self.w_info.setText(self.t("ts_nothing"))
            return 0
        if ask:
            dlg = ApplyDialog(self.t, self.plant, changes, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return 0
        n = TS.commit(self.plant, changes)
        self.w_info.setText(self.t("ts_applied", n=n))
        self.model_changed.emit()
        return n

    # ------------------------------------------------------------------ files
    def export_csv(self, path: str) -> int:
        rows = TS.to_rows(self.plant)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(TS.CSV_HEADER)
            w.writerows(rows)
        return len(rows)

    def import_csv(self, path: str) -> int:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        if rows and rows[0] and rows[0][0].strip().lower() == "key":
            rows = rows[1:]
        ok, bad = TS.from_rows(self.plant, rows)
        self.refresh(self.plant)
        self.msg.setText(self.t("ts_imported", n=ok, bad=len(bad)))
        return ok

    def export_xlsx(self, path: str) -> int:
        """Excel template for the periods and variables currently shown, prefilled with existing data."""
        return XL.export_template(self.plant, path, self.slices, self.cols, self.t.lang)

    def import_xlsx(self, path: str) -> int:
        ok, bad = XL.import_template(self.plant, path)
        self.refresh(self.plant)
        self.msg.setText(self.t("ts_x_imported", n=ok, bad=len(bad)))
        return ok

    def export_xlsx_dialog(self) -> None:
        if self.plant is None or not self.slices or not self.cols:
            self.msg.setText(self.t("ts_x_nothing"))
            return
        path, _ = QFileDialog.getSaveFileName(self, self.t("ts_x_export"), "timeseries-template.xlsx", "Excel (*.xlsx)")
        if path:
            n = self.export_xlsx(path)
            self.msg.setText(self.t("ts_x_exported", n=n, m=len(self.cols)))

    def import_xlsx_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.t("ts_x_import"), "", "Excel (*.xlsx)")
        if path and self.plant is not None:
            self.import_xlsx(path)

    def export_csv_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.t("ts_export"), "timeseries.csv", "CSV (*.csv)")
        if path and self.plant is not None:
            self.export_csv(path)

    def import_csv_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.t("ts_import"), "", "CSV (*.csv)")
        if path and self.plant is not None:
            self.import_csv(path)

