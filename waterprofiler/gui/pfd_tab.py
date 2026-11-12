"""Process-flow diagram page: movable symbols, streams, containers for units with equipment, a data panel for the selected node."""

from __future__ import annotations

import copy
import math
from html import escape
from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QKeySequence, QPageSize, QPainter, QPainterPath, QPainterPathStroker, QPdfWriter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QGraphicsItem, QGraphicsLineItem, QGraphicsObject, QGraphicsPathItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog, QLabel, QMenu, QScrollArea, QVBoxLayout,
                               QWidget)

from .. import flow as F
from .. import pfd as P
from ..analysis import Analysis
from ..i18n import Translator
from ..model import Plant
from .flow_tab import EDGE_COLOR, NODE_COLOR, STATUS_COLOR, labels_for
from .pfd_symbols import draw_symbol
from .theme import COL
from .widgets import button

SYMBOL_COLOR = {"source": "#0A74C8", "outlet": "#64748B", "evap": "#E9892B", "product": "#2E9E4B", "pool": "#14B8A6", "loss": "#D64545"}


def _short(v: float) -> str:
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:.2f}M"
    if a >= 1e3:
        return f"{v / 1e3:.1f}k"
    return f"{v:.0f}"


class NodeItem(QGraphicsObject):
    def __init__(self, n: P.PNode, scene_ref: "PfdScene"):
        super().__init__()
        self.n = n
        self.sc = scene_ref
        self.edges: List["EdgeItem"] = []
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.setAcceptHoverEvents(True)
        self._press_pos: Optional[QPointF] = None

    # symbol area (the part streams attach to)
    def symbol_rect(self) -> QRectF:
        if self.n.container:
            return QRectF(0, 0, self.n.w, self.n.h)
        return QRectF(8, 4, self.n.w - 16, self.n.h - 40)

    def scene_symbol_rect(self) -> QRectF:
        return self.mapRectToScene(self.symbol_rect())

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt API)
        return QRectF(-4, -4, self.n.w + 8, self.n.h + 8)

    def paint(self, p: QPainter, _opt, _w=None) -> None:  # noqa: N802 (Qt API)
        n = self.n
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if n.container:
            r = QRectF(0, 0, n.w, n.h)
            col = QColor(COL["blue"] if self.isSelected() else COL["line2"])
            p.setBrush(QBrush(QColor("#F8FAFD")))
            pen = QPen(col, 2.0 if self.isSelected() else 1.6, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRoundedRect(r, 12, 12)
            st = STATUS_COLOR.get(n.status, "")
            p.setPen(QColor(COL["navy"]))
            f = QFont(p.font())
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(10, 4, n.w - 20, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       p.fontMetrics().elidedText(n.label, Qt.TextElideMode.ElideRight, int(n.w - 70)))
            p.setFont(QFont(p.font().family(), p.font().pointSize(), QFont.Weight.Normal))
            p.setPen(QColor(COL["sub"]))
            p.drawText(QRectF(10, 4, n.w - 20, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, _short(n.volume) + " m³")
            if st and n.status != "balanced":
                p.setBrush(QBrush(QColor(st)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(n.w - 12, 14), 4, 4)
            return
        if self.isSelected():
            p.setPen(QPen(QColor(COL["blue"]), 1.6, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(COL["sky"])))
            p.drawRoundedRect(QRectF(0, 0, n.w, n.h), 8, 8)
        status = STATUS_COLOR.get(n.status, "") if n.kind == "subsystem" and n.status != "balanced" else ""
        draw_symbol(p, n.symbol, self.symbol_rect(), status)
        p.setPen(QColor(COL["text"]))
        f = QFont(p.font())
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        p.drawText(QRectF(0, n.h - 34, n.w, 18), Qt.AlignmentFlag.AlignCenter,
                   fm.elidedText(n.label, Qt.TextElideMode.ElideRight, int(n.w - 4)))
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(COL["sub"]))
        p.drawText(QRectF(0, n.h - 17, n.w, 15), Qt.AlignmentFlag.AlignCenter, "‎" + _short(n.volume) + " m³")

    def itemChange(self, change, value):  # noqa: N802 (Qt API)
        if change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
            for e in self.edges:
                e.adjust()
        return super().itemChange(change, value)

    def mousePressEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        self._press_pos = QPointF(self.pos())
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        super().mouseReleaseEvent(ev)
        if self._press_pos is not None and (self.pos() - self._press_pos).manhattanLength() > 0.5:
            self.sc.node_moved.emit(self.n.id, self.pos().x(), self.pos().y())
        self._press_pos = None

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        self.sc.node_opened.emit(self.n.id)
        super().mouseDoubleClickEvent(ev)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, e: P.PEdge, a: NodeItem, b: NodeItem, vmax: float, index: int):
        super().__init__()
        self.e, self.a, self.b, self.index = e, a, b, index
        self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.width = 1.6 + 9.0 * math.sqrt(max(0.0, e.volume) / vmax) if vmax > 0 else 2.0
        self.col = QColor(EDGE_COLOR.get(e.kind, "#64748B"))
        self.arrow = QPolygonF()
        self.mid = QPointF()
        self.setToolTip(f"{e.volume:,.0f} m³/yr")
        a.edges.append(self)
        b.edges.append(self)
        self.adjust()

    def adjust(self) -> None:
        ra, rb = self.a.scene_symbol_rect(), self.b.scene_symbol_rect()
        self.prepareGeometryChange()
        if rb.left() > ra.right() + 24:                       # left to right: one elbow
            p1, p2 = QPointF(ra.right(), ra.center().y()), QPointF(rb.left(), rb.center().y())
            mx = (p1.x() + p2.x()) / 2
            pts = [p1, QPointF(mx, p1.y()), QPointF(mx, p2.y()), p2]
            self.mid = QPointF(mx, (p1.y() + p2.y()) / 2)
            d = QPointF(1, 0)
        else:                                                 # backwards or same column: go over the top/bottom
            down = rb.center().y() >= ra.center().y()
            p1 = QPointF(ra.center().x(), ra.bottom() if down else ra.top())
            p2 = QPointF(rb.center().x(), rb.top() if down else rb.bottom())
            my = (p1.y() + p2.y()) / 2
            pts = [p1, QPointF(p1.x(), my), QPointF(p2.x(), my), p2]
            self.mid = QPointF((p1.x() + p2.x()) / 2, my)
            d = QPointF(0, 1 if down else -1)
        path = QPainterPath(pts[0])
        for q in pts[1:-1]:
            path.lineTo(q)
        tip = pts[-1]
        head = 7.0 + self.width * 0.6
        base = tip - d * head
        path.lineTo(base)
        n = QPointF(-d.y(), d.x())
        self.arrow = QPolygonF([tip, base + n * (head * 0.55), base - n * (head * 0.55)])
        self.setPath(path)

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt API)
        return super().boundingRect().adjusted(-50, -20, 50, 20)

    def shape(self) -> QPainterPath:  # noqa: N802 (Qt API)
        st = QPainterPathStroker()
        st.setWidth(max(self.width, 12.0))
        return st.createStroke(self.path())

    def paint(self, p: QPainter, _opt, _w=None) -> None:  # noqa: N802 (Qt API)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QColor(self.col)
        if self.isSelected():
            col = QColor(COL["navy"])
        col.setAlpha(210)
        pen = QPen(col, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self.path())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawPolygon(self.arrow)
        txt = "‎" + _short(self.e.volume)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(txt) + 10
        r = QRectF(self.mid.x() - w / 2, self.mid.y() - 9, w, 18)
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(QColor(COL["line2"]), 0.8))
        p.drawRoundedRect(r, 5, 5)
        p.setPen(QColor(COL["text"]))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)


class PfdScene(QGraphicsScene):
    node_moved = Signal(str, float, float)
    node_opened = Signal(str)
    connect_requested = Signal(str, str)
    context_requested = Signal(object, object)         # item (or None), screen position

    def __init__(self):
        super().__init__()
        self.connect_mode = False
        self._start: Optional[NodeItem] = None
        self._line: Optional[QGraphicsLineItem] = None

    @staticmethod
    def _node_at(items) -> Optional[NodeItem]:
        for it in items:
            if isinstance(it, NodeItem):
                return it
        return None

    def mousePressEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        if self.connect_mode and ev.button() == Qt.MouseButton.LeftButton:
            n = self._node_at(self.items(ev.scenePos()))
            if n is not None:
                self._start = n
                self._line = QGraphicsLineItem()
                self._line.setPen(QPen(QColor(COL["navy"]), 2.4, Qt.PenStyle.DashLine))
                self._line.setZValue(10)
                self.addItem(self._line)
                c = n.scene_symbol_rect().center()
                self._line.setLine(c.x(), c.y(), ev.scenePos().x(), ev.scenePos().y())
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        if self._line is not None and self._start is not None:
            c = self._start.scene_symbol_rect().center()
            self._line.setLine(c.x(), c.y(), ev.scenePos().x(), ev.scenePos().y())
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        if self._line is not None and self._start is not None:
            end = self._node_at(self.items(ev.scenePos()))
            start = self._start
            self.removeItem(self._line)
            self._line, self._start = None, None
            if end is not None and end is not start:
                self.connect_requested.emit(start.n.id, end.n.id)
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def contextMenuEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        items = self.items(ev.scenePos())
        it = next((i for i in items if isinstance(i, (NodeItem, EdgeItem))), None)
        if isinstance(it, NodeItem):                  # a symbol inside a container wins over the container
            inner = [i for i in items if isinstance(i, NodeItem) and not i.n.container]
            it = inner[0] if inner else it
        self.context_requested.emit(it, ev.screenPos())
        ev.accept()


class PfdView(QGraphicsView):
    def __init__(self, scene: PfdScene):
        super().__init__(scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#FFFFFF")))
        self.setMinimumHeight(520)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def wheelEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        k = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self.zoom(k)

    def zoom(self, k: float) -> None:
        cur = self.transform().m11()
        if 0.15 < cur * k < 3.5:
            self.scale(k, k)

    def fit(self) -> None:
        r = self.scene().itemsBoundingRect().adjusted(-30, -30, 30, 30)
        if r.width() > 0 and r.height() > 0:
            self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)


class PfdTab(QWidget):
    subsystem_requested = Signal(str)
    plant_edited = Signal()                 # the data changed: the window recomputes everything

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self.analysis: Optional[Analysis] = None
        self.graph: Optional[P.PFD] = None
        self.items: Dict[str, NodeItem] = {}
        self.edge_items: List[EdgeItem] = []
        self._undo: List[dict] = []
        self._fitted = False
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(f"color:{COL['red']};")
        lay.addWidget(self.msg)
        bar = QHBoxLayout()
        self.connect_btn = button(t("pfd_connect"), "", self._toggle_connect)
        self.connect_btn.setCheckable(True)
        self.connect_btn.setToolTip(t("pfd_connect_tip"))
        self.undo_btn = button(t("flow_undo"), "", self.undo)
        self.undo_btn.setEnabled(False)
        bar.addWidget(self.connect_btn)
        bar.addWidget(button(t("flow_reset"), "", self._reset_layout))
        bar.addWidget(button(t("pfd_fit"), "", lambda: self.view.fit()))
        bar.addWidget(button("+", "", lambda: self.view.zoom(1.25)))
        bar.addWidget(button("−", "", lambda: self.view.zoom(1 / 1.25)))
        bar.addWidget(self.undo_btn)
        bar.addStretch(1)
        bar.addWidget(button(t("pfd_save_png"), "", self._save_png))
        bar.addWidget(button(t("pfd_save_pdf"), "", self._save_pdf))
        lay.addLayout(bar)
        legend = QLabel()
        legend.setTextFormat(Qt.TextFormat.RichText)
        keys = [("intake", "flow_l_intake"), ("transfer", "flow_l_transfer"), ("discharge", "flow_l_discharge"),
                ("evap", "flow_l_evap"), ("product", "flow_l_product"), ("loss", "flow_l_loss")]
        legend.setText("&nbsp;&nbsp;&nbsp;".join(f"<span style='background-color:{EDGE_COLOR[k]}'>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span> {t(v)}"
                                                for k, v in keys))
        legend.setObjectName("cardnote")
        lay.addWidget(legend)
        body = QHBoxLayout()
        self.scene = PfdScene()
        self.view = PfdView(self.scene)
        self.scene.selectionChanged.connect(self._selection_changed)
        self.scene.node_moved.connect(self._node_moved)
        self.scene.node_opened.connect(self._node_opened)
        self.scene.connect_requested.connect(self._connect)
        self.scene.context_requested.connect(self._context)
        body.addWidget(self.view, 1)
        side = QFrame()
        side.setObjectName("card")
        side.setFixedWidth(330)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 12, 12, 12)
        self.panel = QLabel(t("pfd_hint"))
        self.panel.setWordWrap(True)
        self.panel.setTextFormat(Qt.TextFormat.RichText)
        self.panel.setAlignment(Qt.AlignmentFlag.AlignTop | (Qt.AlignmentFlag.AlignRight if t.rtl else Qt.AlignmentFlag.AlignLeft))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(self.panel)
        sl.addWidget(sc, 1)
        self.open_btn = button(t("pfd_open_data"), "primary", self._open_selected)
        self.open_btn.setVisible(False)
        sl.addWidget(self.open_btn)
        body.addWidget(side)
        lay.addLayout(body, 1)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)

    # ------------------------------------------------------------------------------------------ data -> view
    def refresh(self, plant: Plant, a: Optional[Analysis]) -> None:
        self.plant, self.analysis = plant, a
        if a is None:
            return
        self._rebuild()

    def _rebuild(self) -> None:
        if self.plant is None or self.analysis is None:
            return
        self._busy = True
        keep = self._selected_id()
        self.scene.clear()
        self.items, self.edge_items = {}, []
        self.graph = P.build_pfd(self.analysis, labels_for(self.t))
        g = self.graph
        order = sorted(g.nodes.values(), key=lambda n: (bool(n.parent), 0 if n.container else 1))
        for n in order:                                           # containers first, so that equipment can be their children
            it = NodeItem(n, self.scene)
            it.setZValue(0 if n.container else 2)
            self.scene.addItem(it)
            if n.parent and n.parent in self.items:
                it.setParentItem(self.items[n.parent])
            it.setPos(n.x, n.y)
            self.items[n.id] = it
        vmax = max((e.volume for e in g.edges), default=0.0)
        for i, e in enumerate(g.edges):
            if e.src in self.items and e.dst in self.items:
                ei = EdgeItem(e, self.items[e.src], self.items[e.dst], vmax, i)
                self.scene.addItem(ei)
                self.edge_items.append(ei)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        self._busy = False
        if keep in self.items:
            self.items[keep].setSelected(True)
        if not self._fitted and g.nodes:
            self.view.fit()
            self._fitted = True
        self.msg.setText(self.t("pfd_warn").format("; ".join(g.warnings[:3])) if g.warnings else "")
        self._selection_changed()

    def _selected_id(self) -> str:
        for it in self.scene.selectedItems():
            if isinstance(it, NodeItem):
                return it.n.id
        return ""

    # ------------------------------------------------------------------------------------------ side panel
    def _fmt(self, v, fmt: str) -> str:
        t = self.t
        cur = self.plant.currency if self.plant else ""
        if fmt == "m3":
            return "‎" + f"{v:,.0f} m³"
        if fmt == "cur":
            return "‎" + f"{v:,.0f} {cur}"
        if fmt == "cur3":
            return "—" if v is None else "‎" + f"{v:,.3f} {cur}/m³"
        if fmt == "pct":
            return "‎" + f"{v:.1f}%"
        if fmt == "num":
            return "‎" + f"{v:,.0f}"
        if fmt == "flag":
            return t("pfd_yes") if v == "yes" else t("pfd_no")
        if fmt == "status":
            return t("st_" + str(v))
        return escape(str(v))

    def _selection_changed(self) -> None:
        if self._busy or self.analysis is None:
            return
        t = self.t
        sel = self.scene.selectedItems()
        self.open_btn.setVisible(False)
        if not sel:
            self.panel.setText(t("pfd_hint"))
            return
        it = sel[0]
        if isinstance(it, EdgeItem):
            e = it.e
            self.panel.setText(f"<h3>{escape(t('flow_l_' + e.kind))}</h3><p>{self._fmt(e.volume, 'm3')}</p>"
                               f"<p>{escape(e.sub)}{' → ' + escape(e.ref) if e.ref else ''}</p><p>{escape(t('pfd_edge_hint'))}</p>")
            return
        info = P.node_info(self.analysis, it.n.id, t.lang)
        if info is None:
            self.panel.setText("")
            return
        h = [f"<h3>{escape(info.title)}</h3>", "<table cellspacing='4'>"]
        for key, val, fmt in info.rows:
            h.append(f"<tr><td style='color:{COL['sub']}'>{escape(t(key))}</td><td><b>{self._fmt(val, fmt)}</b></td></tr>")
        h.append("</table>")
        for sec, rows in info.lists.items():
            if not rows:
                continue
            h.append(f"<p style='color:{COL['navy']}'><b>{escape(t(sec))}</b></p><table cellspacing='3'>")
            for lab, val, fmt in rows:
                h.append(f"<tr><td>{escape(str(lab))}</td><td>{self._fmt(val, fmt)}</td></tr>")
            h.append("</table>")
        self.panel.setText("".join(h))
        self.open_btn.setVisible(bool(info.subsystem))
        self._open_name = info.subsystem

    def _open_selected(self) -> None:
        name = getattr(self, "_open_name", "")
        if name:
            self.subsystem_requested.emit(name)

    # ------------------------------------------------------------------------------------------ editing
    def _mutate(self, fn) -> bool:
        if self.plant is None:
            return False
        snap = copy.deepcopy(self.plant.to_dict())
        try:
            fn(self.plant)
        except (KeyError, ValueError) as e:
            new = Plant.from_dict(snap)
            self.plant.__dict__.update(new.__dict__)
            self.msg.setText(self.t("missing_ref", name=str(e).strip("'\"")) if isinstance(e, KeyError) else str(e))
            return False
        self.msg.setText("")
        self._undo.append(snap)
        del self._undo[:-40]
        self.undo_btn.setEnabled(True)
        return True

    def undo(self) -> None:
        if not self._undo or self.plant is None:
            return
        new = Plant.from_dict(self._undo.pop())
        self.plant.__dict__.update(new.__dict__)
        self.undo_btn.setEnabled(bool(self._undo))
        self.plant_edited.emit()

    def _node_moved(self, nid: str, x: float, y: float) -> None:
        if self._mutate(lambda p: P.set_position(p, nid, x, y)):
            n = self.graph.nodes.get(nid) if self.graph else None
            if n is not None:
                n.x, n.y = x, y

    def _node_opened(self, nid: str) -> None:
        k, name = P.split_id(nid)
        if k == "subsystem":
            self.subsystem_requested.emit(name)

    def _reset_layout(self) -> None:
        if self.plant is not None and (self.plant.pfd or {}).get("pos"):
            self._mutate(P.reset_layout)
            self._rebuild()
            self.view.fit()

    def _toggle_connect(self) -> None:
        self.scene.connect_mode = self.connect_btn.isChecked()
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if self.scene.connect_mode else QGraphicsView.DragMode.ScrollHandDrag)
        for it in self.items.values():
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self.scene.connect_mode)

    def _ask(self, title: str, default: float) -> Optional[float]:
        v, ok = QInputDialog.getDouble(self, title, self.t("flow_volume_prompt"), float(default), 0.0, 1e12, 1)
        return v if ok else None

    def _connect(self, a_id: str, b_id: str) -> None:
        if self.plant is None:
            return
        try:
            kind, sub, ref = P.resolve_connection(a_id, b_id)
        except ValueError:
            self.msg.setText(self.t("flow_bad_link"))
            return
        if self.plant.has_children(sub) or (kind == "transfer" and self.plant.has_children(ref)):
            self.msg.setText(self.t("pfd_derived"))
            return
        default = F.current_volume(self.plant, kind, sub, ref) if kind in ("evap", "product") else 0.0
        v = self._ask(sub, default)
        if v is None or v <= 0:
            return
        fn = F.set_flow if kind in ("evap", "product") else F.add_flow
        if self._mutate(lambda p: fn(p, kind, sub, ref, v)):
            self.plant_edited.emit()

    def _edit_edge(self, e: P.PEdge) -> None:
        v = self._ask(f"{e.sub}", e.volume)
        if v is not None and self._mutate(lambda p: F.set_flow(p, e.kind, e.sub, e.ref, v)):
            self.plant_edited.emit()

    def _delete_edge(self, e: P.PEdge) -> None:
        if self._mutate(lambda p: F.delete_flow(p, e.kind, e.sub, e.ref)):
            self.plant_edited.emit()

    def _context(self, item, pos) -> None:
        t = self.t
        if self.plant is None:
            return
        m = QMenu(self)
        if isinstance(item, EdgeItem):
            e = item.e
            if e.kind == "loss":
                return
            m.addAction(t("flow_edit_volume"), lambda: self._edit_edge(e))
            m.addAction(t("flow_delete"), lambda: self._delete_edge(e))
        elif isinstance(item, NodeItem):
            n = item.n
            if n.kind == "subsystem":
                m.addAction(t("pfd_open_data"), lambda: self.subsystem_requested.emit(n.name))
                if not n.container:
                    sub = m.addMenu(t("pfd_symbol"))
                    for s in P.SUBSYSTEM_SYMBOLS:
                        sub.addAction(t("pfd_sym_" + s), lambda s=s: self._set_symbol(n.id, s))
        else:
            return
        m.exec(pos)

    def _set_symbol(self, nid: str, symbol: str) -> None:
        if self._mutate(lambda p: P.set_symbol(p, nid, symbol)):
            n = self.graph.nodes.get(nid) if self.graph else None
            if n is not None:
                n.symbol = symbol
            self.items[nid].update()

    # ------------------------------------------------------------------------------------------ output
    def _render(self, painter: QPainter, target: QRectF) -> None:
        src = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        sel = self.scene.selectedItems()
        for it in sel:
            it.setSelected(False)
        self.scene.render(painter, target, src, Qt.AspectRatioMode.KeepAspectRatio)
        for it in sel:
            it.setSelected(True)

    def _save_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.t("pfd_save_png"), "pfd.png", "PNG (*.png)")
        if not path:
            return
        src = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        k = min(3.0, 3000.0 / max(src.width(), 1.0))
        img = QImage(int(src.width() * k), int(src.height() * k), QImage.Format.Format_ARGB32)
        img.fill(QColor("#FFFFFF"))
        p = QPainter(img)
        self._render(p, QRectF(0, 0, img.width(), img.height()))
        p.end()
        img.save(path)

    def _save_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.t("pfd_save_pdf"), "pfd.pdf", "PDF (*.pdf)")
        if not path:
            return
        w = QPdfWriter(path)
        w.setPageSize(QPageSize(QPageSize.PageSizeId.A3))
        from PySide6.QtGui import QPageLayout
        w.setPageOrientation(QPageLayout.Orientation.Landscape)
        p = QPainter(w)
        self._render(p, QRectF(0, 0, w.width(), w.height()))
        p.end()
