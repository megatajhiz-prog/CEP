"""Process-flow-diagram symbols drawn with QPainter (simplified P&ID style, one function per kind)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF

INK = "#0B3D78"
FILL = "#E8F3FC"
WATER = "#0A74C8"


def _pen(p: QPainter, color: str = INK, w: float = 2.0) -> None:
    p.setPen(QPen(QColor(color), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))


def _fill(p: QPainter, color: str = FILL) -> None:
    p.setBrush(QBrush(QColor(color)))


def _cylinder(p: QPainter, r: QRectF, dome: bool = False) -> None:
    e = min(r.height() * 0.16, 9.0)
    body = QPainterPath()
    body.moveTo(r.left(), r.top() + e)
    body.lineTo(r.left(), r.bottom() - e)
    body.arcTo(QRectF(r.left(), r.bottom() - 2 * e, r.width(), 2 * e), 180, 180)
    body.lineTo(r.right(), r.top() + e)
    body.arcTo(QRectF(r.left(), r.top(), r.width(), 2 * e), 0, 180)
    body.closeSubpath()
    _fill(p)
    p.drawPath(body)
    p.drawEllipse(QRectF(r.left(), r.top(), r.width(), 2 * e))


def _wave(p: QPainter, x0: float, x1: float, y: float, amp: float = 2.5, n: int = 3) -> None:
    path = QPainterPath(QPointF(x0, y))
    seg = (x1 - x0) / (2 * n)
    for k in range(2 * n):
        sign = -1 if k % 2 == 0 else 1
        path.quadTo(QPointF(x0 + seg * (k + 0.5), y + sign * amp * 2), QPointF(x0 + seg * (k + 1), y))
    p.drawPath(path)


def draw_symbol(p: QPainter, kind: str, r: QRectF, status_color: str = "") -> None:
    """Draw ``kind`` inside ``r`` (about 80 x 54 px)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _pen(p)
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    if kind == "source":                                  # reservoir / supply with waves
        _fill(p)
        p.drawRoundedRect(r, 10, 10)
        _pen(p, WATER, 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in range(3):
            _wave(p, r.left() + 12, r.right() - 12, r.top() + h * (0.32 + 0.22 * k))
    elif kind == "outlet":                                # outfall: triangle pointing to the discharge
        _fill(p, "#EEF2F7")
        p.drawPolygon(QPolygonF([QPointF(r.left() + 6, r.top() + 4), QPointF(r.right() - 6, cy), QPointF(r.left() + 6, r.bottom() - 4)]))
        p.drawLine(QPointF(r.left() + 6, cy), QPointF(r.left() + w * 0.45, cy))
    elif kind == "evap":                                  # three rising wavy arrows
        _pen(p, "#E9892B", 2.2)
        for k in range(3):
            x = r.left() + w * (0.25 + 0.25 * k)
            path = QPainterPath(QPointF(x, r.bottom() - 4))
            path.cubicTo(QPointF(x - 7, r.bottom() - h * 0.35), QPointF(x + 7, r.bottom() - h * 0.6), QPointF(x, r.top() + 8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.drawLine(QPointF(x, r.top() + 5), QPointF(x - 4, r.top() + 12))
            p.drawLine(QPointF(x, r.top() + 5), QPointF(x + 4, r.top() + 12))
    elif kind == "product":                               # package
        _pen(p, "#14572A", 2)
        _fill(p, "#E7F5EB")
        p.drawRoundedRect(QRectF(r.left() + 10, r.top() + 6, w - 20, h - 12), 4, 4)
        p.drawLine(QPointF(cx, r.top() + 6), QPointF(cx, r.bottom() - 6))
        p.drawLine(QPointF(r.left() + 10, cy), QPointF(r.right() - 10, cy))
    elif kind == "pool":                                  # undefined transfer: dashed circle
        pen = QPen(QColor("#14B8A6"), 2.2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        _fill(p, "#E6FAF7")
        p.drawEllipse(r.adjusted(w * 0.18, 2, -w * 0.18, -2))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "?")
    elif kind == "loss":                                  # balance residual: drop in a circle
        _pen(p, "#D64545", 2.2)
        _fill(p, "#FDEBEB")
        p.drawEllipse(r.adjusted(w * 0.18, 2, -w * 0.18, -2))
        drop = QPainterPath(QPointF(cx, cy - 12))
        drop.cubicTo(QPointF(cx + 12, cy + 2), QPointF(cx + 8, cy + 12), QPointF(cx, cy + 12))
        drop.cubicTo(QPointF(cx - 8, cy + 12), QPointF(cx - 12, cy + 2), QPointF(cx, cy - 12))
        p.drawPath(drop)
    elif kind == "cooling_tower":
        _fill(p)
        tower = QPolygonF([QPointF(r.left() + w * 0.22, r.bottom() - 3), QPointF(r.left() + w * 0.30, cy),
                           QPointF(r.left() + w * 0.22, r.top() + 12), QPointF(r.right() - w * 0.22, r.top() + 12),
                           QPointF(r.right() - w * 0.30, cy), QPointF(r.right() - w * 0.22, r.bottom() - 3)])
        p.drawPolygon(tower)
        p.drawEllipse(QRectF(cx - 14, r.top() + 3, 28, 10))                   # fan stack
        _pen(p, WATER, 1.6)
        for k in range(3):
            _wave(p, r.left() + w * 0.34, r.right() - w * 0.34, cy + 4 + 6 * k, 1.6, 2)
    elif kind == "boiler":
        _fill(p)
        p.drawRoundedRect(QRectF(r.left() + 4, r.top() + 4, w - 8, h * 0.62), h * 0.3, h * 0.3)
        p.drawLine(QPointF(cx - 10, r.top() + 4), QPointF(cx - 10, r.top() - 2))
        flame = QPainterPath(QPointF(cx, r.bottom() - 2))
        flame.cubicTo(QPointF(cx - 10, r.bottom() - 8), QPointF(cx - 4, r.top() + h * 0.7), QPointF(cx, r.top() + h * 0.68))
        flame.cubicTo(QPointF(cx + 4, r.top() + h * 0.7), QPointF(cx + 10, r.bottom() - 8), QPointF(cx, r.bottom() - 2))
        _pen(p, "#E9892B", 2)
        p.drawPath(flame)
    elif kind == "sanitary":                              # basin with a tap
        _fill(p)
        p.drawRoundedRect(QRectF(r.left() + 10, cy - 2, w - 20, h * 0.42), 8, 8)
        path = QPainterPath(QPointF(cx, cy - 2))
        path.lineTo(QPointF(cx, r.top() + 8))
        path.lineTo(QPointF(cx + 12, r.top() + 8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        _pen(p, WATER, 2)
        p.drawLine(QPointF(cx + 12, r.top() + 11), QPointF(cx + 12, r.top() + 18))
    elif kind == "irrigation":                            # sprinkler arcs
        _pen(p, "#2E9E4B", 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, r.bottom() - 3), QPointF(cx, cy + 4))
        for k, rad in enumerate((12, 20, 28)):
            p.drawArc(QRectF(cx - rad, cy + 4 - rad, 2 * rad, 2 * rad), 30 * 16, 120 * 16)
    elif kind == "tank":
        _cylinder(p, r.adjusted(w * 0.2, 2, -w * 0.2, -2))
        _pen(p, WATER, 1.8)
        _wave(p, r.left() + w * 0.26, r.right() - w * 0.26, cy + 2, 1.6, 2)
    elif kind == "vessel":
        _cylinder(p, r.adjusted(w * 0.2, 2, -w * 0.2, -2))
    elif kind == "pump":
        rad = min(w, h) / 2 - 3
        _fill(p)
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.drawPolygon(QPolygonF([QPointF(cx - rad * 0.55, cy - rad * 0.8), QPointF(cx + rad, cy), QPointF(cx - rad * 0.55, cy + rad * 0.8)]))
    elif kind == "treatment":                             # filter: box with diagonal bed
        _fill(p)
        p.drawRoundedRect(r.adjusted(8, 4, -8, -4), 4, 4)
        _pen(p, WATER, 1.6)
        for k in range(1, 6):
            x = r.left() + 8 + (w - 16) * k / 6
            p.drawLine(QPointF(x, r.top() + 8), QPointF(x - 10, r.bottom() - 8))
    else:                                                 # process unit: box with a gear-like circle
        _fill(p)
        p.drawRoundedRect(r.adjusted(4, 3, -4, -3), 6, 6)
        p.drawEllipse(QPointF(cx, cy), min(w, h) * 0.2, min(w, h) * 0.2)
        for k in range(8):
            a = math.radians(45 * k)
            p.drawLine(QPointF(cx + math.cos(a) * min(w, h) * 0.2, cy + math.sin(a) * min(w, h) * 0.2),
                       QPointF(cx + math.cos(a) * min(w, h) * 0.29, cy + math.sin(a) * min(w, h) * 0.29))
    if status_color:                                      # balance status: a ring around the symbol
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(status_color), 3.0))
        p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 10, 10)
    p.restore()
