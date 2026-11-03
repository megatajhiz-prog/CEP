"""Visual theme: colours, global Qt stylesheet, vector navigation icons."""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

from ..branding import asset

COL = {
    "bg": "#F1F5FA", "card": "#FFFFFF", "line": "#E1E8F1", "line2": "#CBD6E3",
    "navy": "#0B3D78", "blue": "#0A74C8", "blue_d": "#0858A6", "sky": "#E8F3FC", "sky2": "#D5E9FA",
    "green": "#2E9E4B", "green_l": "#E7F5EB", "orange": "#E9892B", "orange_l": "#FFF3E0",
    "red": "#D64545", "red_l": "#FDEBEB", "text": "#1F2A3B", "sub": "#64748B", "zebra": "#F8FAFD",
}
CHART = ["#0A74C8", "#2E9E4B", "#F2994A", "#0B3D78", "#14B8A6", "#8E6BBF"]


def stylesheet() -> str:
    chevron = asset("brand", "chevron.png").replace("\\", "/")
    c = COL
    return f"""
* {{ outline: 0; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QWidget {{ color: {c['text']}; }}
QToolTip {{ background: {c['navy']}; color: white; border: 0; padding: 6px 8px; }}

QMenuBar {{ background: {c['card']}; border-bottom: 1px solid {c['line']}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 7px 14px; border-radius: 8px; background: transparent; }}
QMenuBar::item:selected {{ background: {c['sky']}; color: {c['navy']}; }}
QMenu {{ background: {c['card']}; border: 1px solid {c['line2']}; padding: 6px; border-radius: 10px; }}
QMenu::item {{ padding: 8px 28px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['sky']}; color: {c['navy']}; }}
QMenu::separator {{ height: 1px; background: {c['line']}; margin: 6px 10px; }}
QStatusBar {{ background: {c['card']}; border-top: 1px solid {c['line']}; color: {c['sub']}; }}
QStatusBar::item {{ border: 0; }}

QFrame#sidebar {{ background: {c['card']}; border-left: 1px solid {c['line']}; border-right: 1px solid {c['line']}; }}
QFrame#accent {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['blue']}, stop:1 #3BC148); border: 0; border-radius: 1px; }}
QLabel#appname {{ color: {c['navy']}; font-size: 22px; font-weight: 700; }}
QLabel#appsub {{ color: {c['sub']}; font-size: 11px; }}
QLabel#sidefoot {{ color: {c['sub']}; font-size: 11px; }}
QPushButton#nav {{ background: transparent; border: 0; border-radius: 12px; text-align: center; }}
QPushButton#nav:hover {{ background: {c['sky']}; }}
QPushButton#nav:checked {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c['blue']}, stop:1 {c['blue_d']}); }}

QFrame#header {{ background: {c['card']}; border-bottom: 1px solid {c['line']}; }}
QLabel#pagetitle {{ font-size: 21px; font-weight: 700; color: {c['navy']}; }}
QLabel#pagedesc {{ font-size: 12px; color: {c['sub']}; }}

QFrame#card {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 14px; }}
QLabel#cardtitle {{ font-size: 14px; font-weight: 700; color: {c['navy']}; background: transparent; }}
QLabel#cardnote {{ font-size: 12px; color: {c['sub']}; background: transparent; }}
QFrame#stat {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 14px; }}
QLabel#stattitle {{ font-size: 12px; color: {c['sub']}; background: transparent; }}
QLabel#statvalue {{ font-size: 24px; font-weight: 700; background: transparent; }}
QLabel#stathint {{ font-size: 11px; color: {c['sub']}; background: transparent; }}
QLabel#msg {{ color: {c['orange']}; font-size: 12px; }}
QLabel#warnbox {{ background: {c['orange_l']}; color: #8A4B08; border: 1px solid #F6D9AE; border-radius: 10px; padding: 10px 14px; }}
QLabel#result {{ background: {c['green_l']}; color: #14572A; border: 1px solid #BFE3CB; border-radius: 10px; padding: 10px 14px; }}

QGroupBox {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 14px; margin-top: 22px; padding: 18px 14px 12px 14px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 2px 14px; color: {c['navy']}; font-size: 13px; font-weight: 700; }}

QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['line2']}; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: #9FB3C8; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['line2']}; border-radius: 4px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QLineEdit, QDoubleSpinBox, QComboBox {{ background: {c['card']}; border: 1px solid {c['line2']}; border-radius: 9px; padding: 6px 10px; min-height: 22px; selection-background-color: {c['blue']}; selection-color: white; }}
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1.5px solid {c['blue']}; }}
QLineEdit:read-only {{ background: transparent; border: 0; color: {c['sub']}; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['line2']}; selection-background-color: {c['sky']}; selection-color: {c['navy']}; padding: 4px; }}

QPushButton {{ background: {c['card']}; color: {c['navy']}; border: 1px solid {c['line2']}; border-radius: 10px; padding: 8px 18px; font-weight: 600; min-height: 22px; }}
QPushButton:hover {{ background: {c['sky']}; border-color: {c['blue']}; }}
QPushButton:pressed {{ background: {c['sky2']}; }}
QPushButton:disabled {{ color: #A3B1C2; background: #F4F7FA; border-color: {c['line']}; }}
QPushButton[kind="primary"] {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['blue']}, stop:1 {c['blue_d']}); color: white; border: 0; }}
QPushButton[kind="primary"]:hover {{ background: {c['blue_d']}; }}
QPushButton[kind="primary"]:disabled {{ background: #B7C9DB; color: white; }}
QPushButton[kind="danger"] {{ color: {c['red']}; border-color: #F0C4C4; }}
QPushButton[kind="danger"]:hover {{ background: {c['red_l']}; border-color: {c['red']}; }}
QPushButton[kind="ghost"] {{ border-color: transparent; background: transparent; }}
QPushButton[kind="ghost"]:hover {{ background: {c['sky']}; }}

QListWidget {{ background: transparent; border: 0; }}
QListWidget::item {{ padding: 11px 12px; border-radius: 10px; margin: 2px 0; }}
QListWidget::item:hover {{ background: {c['zebra']}; }}
QListWidget::item:selected {{ background: {c['sky']}; color: {c['navy']}; font-weight: 600; }}

QTableWidget, QTableView {{ background: {c['card']}; alternate-background-color: {c['zebra']}; border: 1px solid {c['line']}; border-radius: 10px; gridline-color: transparent; selection-background-color: {c['sky']}; selection-color: {c['navy']}; }}
QTableWidget::item {{ padding: 4px 8px; border: 0; }}
QTableWidget QComboBox {{ margin: 3px 5px; padding: 2px 8px; min-height: 22px; border-radius: 7px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: #EDF3FA; color: {c['navy']}; border: 0; border-bottom: 1px solid {c['line']}; padding: 9px 8px; font-weight: 700; }}
QTableCornerButton::section {{ background: #EDF3FA; border: 0; }}

QSplitter::handle {{ background: transparent; }}
QDialogButtonBox QPushButton {{ min-width: 90px; }}
QMessageBox {{ background: {c['card']}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())


# ------------------------------------------------------------------ icons
def nav_pixmap(name: str, color: str, size: int = 22) -> QPixmap:
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    P = QPointF
    if name == "plant":
        p.drawPolygon(QPolygonF([P(3, 20), P(3, 10), P(9, 14), P(9, 10), P(15, 14), P(15, 5), P(19.5, 5), P(19.5, 20)]))
    elif name == "subsystems":
        for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
            p.drawRoundedRect(QRectF(x, y, 7, 7), 1.8, 1.8)
    elif name == "flow":
        for x, y in ((3, 5), (3, 15)):
            p.drawRoundedRect(QRectF(x, y, 4.5, 4.5), 1.2, 1.2)
        p.drawRoundedRect(QRectF(16.5, 9.5, 4.5, 4.5), 1.2, 1.2)
        for y in (7.2, 17.2):
            path = QPainterPath()
            path.moveTo(7.5, y)
            path.cubicTo(12, y, 12, 11.8, 16.5, 11.8)
            p.drawPath(path)
    elif name == "balance":
        p.drawLine(P(12, 4), P(12, 20))
        p.drawLine(P(7, 20), P(17, 20))
        p.drawLine(P(4, 7.5), P(20, 7.5))
        for cx in (4, 20):
            p.drawLine(P(cx, 7.5), P(cx - 2.6, 14))
            p.drawLine(P(cx, 7.5), P(cx + 2.6, 14))
            p.drawLine(P(cx - 3.2, 14), P(cx + 3.2, 14))
    elif name == "cost":
        p.drawEllipse(QRectF(5, 4, 14, 6))
        p.drawLine(P(5, 7), P(5, 16))
        p.drawLine(P(19, 7), P(19, 16))
        p.drawArc(QRectF(5, 7.5, 14, 6), 180 * 16, 180 * 16)
        p.drawArc(QRectF(5, 13, 14, 6), 180 * 16, 180 * 16)
    elif name == "savings":
        path = QPainterPath()
        path.moveTo(12, 3)
        path.cubicTo(12, 3, 5, 10, 5, 15)
        path.cubicTo(5, 19, 8.5, 21, 12, 21)
        path.cubicTo(15.5, 21, 19, 19, 19, 15)
        path.cubicTo(19, 10, 12, 3, 12, 3)
        p.drawPath(path)
        p.drawLine(P(9, 15), P(11.2, 17.2))
        p.drawLine(P(11.2, 17.2), P(15.2, 12.8))
    elif name == "measures":
        p.drawEllipse(QRectF(6, 3, 12, 12))
        p.drawLine(P(9.5, 18), P(14.5, 18))
        p.drawLine(P(10.5, 21), P(13.5, 21))
        p.drawLine(P(12, 15), P(12, 9.5))
        p.drawLine(P(9.5, 7.5), P(12, 9.5))
        p.drawLine(P(14.5, 7.5), P(12, 9.5))
    elif name == "plan":
        p.drawRoundedRect(QRectF(5, 4, 14, 17), 2, 2)
        p.drawRoundedRect(QRectF(9, 2.5, 6, 3.5), 1.2, 1.2)
        p.drawLine(P(8.5, 11), P(10, 12.5))
        p.drawLine(P(10, 12.5), P(12.5, 9.8))
        p.drawLine(P(14, 12), P(16, 12))
        p.drawLine(P(8.5, 17), P(16, 17))
    elif name == "econ":
        p.drawLine(P(4, 20), P(20, 20))
        p.drawLine(P(4, 20), P(4, 4))
        p.drawPolyline(QPolygonF([P(7, 15), P(11, 11), P(14, 13.5), P(19, 7)]))
        p.drawLine(P(15.5, 7), P(19, 7))
        p.drawLine(P(19, 7), P(19, 10.5))
    elif name == "site":
        p.drawRect(QRectF(4, 11, 16, 9))
        p.drawPolyline(QPolygonF([P(4, 11), P(9, 7), P(9, 11), P(14, 7), P(14, 11)]))
        p.drawRect(QRectF(16, 4, 3, 7))
        p.drawLine(P(8, 20), P(8, 15))
        p.drawLine(P(12, 20), P(12, 15))
    elif name == "ts":
        p.drawLine(P(4, 20), P(20, 20))
        p.drawLine(P(4, 20), P(4, 4))
        for x, h in ((8, 6), (12, 10), (16, 7)):
            p.drawRect(QRectF(x - 1.5, 20 - h, 3, h))
    elif name == "ind":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
        p.drawLine(P(4, 9.5), P(20, 9.5))
        p.drawLine(P(4, 14.5), P(20, 14.5))
        p.drawLine(P(10, 9.5), P(10, 20))
    elif name == "reconcile":
        for y, kx in ((6, 9), (12, 15), (18, 8)):
            p.drawLine(P(4, y), P(20, y))
            p.setBrush(QColor(color))
            p.drawEllipse(P(kx, y), 2.3, 2.3)
            p.setBrush(Qt.BrushStyle.NoBrush)
    p.end()
    return pm


def brand_icon() -> QIcon:
    from ..branding import logo_path
    return QIcon(logo_path("mark")) if os.path.exists(logo_path("mark")) else QIcon()
