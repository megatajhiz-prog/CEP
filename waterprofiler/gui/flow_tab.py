"""Water-flow diagram (Sankey style) and the editor for transfers between subsystems."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFileDialog, QLabel, QToolTip, QWidget

from ..analysis import Analysis
from ..flow import FlowGraph, FlowNode, build_flow
from ..i18n import Translator
from ..model import Plant, sync_transfers
from .tabs import _Scroll, _message_label
from .theme import COL
from .widgets import DataTable, button, card

LRM = "‎"
EDGE_COLOR = {"intake": "#0A74C8", "discharge": "#64748B", "transfer": "#14B8A6",
              "evap": "#E9892B", "product": "#2E9E4B", "loss": "#D64545"}
NODE_COLOR = {"source": "#0A74C8", "outlet": "#64748B", "evap": "#E9892B", "product": "#2E9E4B",
              "loss": "#D64545", "pool": "#14B8A6"}
STATUS_COLOR = {"balanced": "#0B3D78", "unaccounted loss": "#E9892B", "excess outflow": "#D64545"}
COL_ORDER = {"outlet": 0, "evap": 1, "product": 2, "loss": 3, "pool": 4}


def _num(v: float) -> str:
    return f"{LRM}{v:,.0f}{LRM}"


def labels_for(t: Translator) -> Dict[str, str]:
    return {"evap": t("flow_evap"), "product": t("flow_product"), "loss": t("flow_loss"), "pool": t("flow_pool")}


def paint_flow(p: QPainter, rect: QRectF, g: FlowGraph, rtl: bool, t: Translator) -> List[Tuple[QRectF, FlowNode]]:
    """Draw the diagram into ``rect``; returns node hit boxes."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    hits: List[Tuple[QRectF, FlowNode]] = []
    if not g.nodes:
        return hits
    pad_x, pad_y, gap = 150.0, 18.0, 14.0
    sub_w, thin_w = 132.0, 14.0
    left, right = rect.left() + pad_x, rect.right() - pad_x
    top, height = rect.top() + pad_y, rect.height() - 2 * pad_y
    cols: Dict[int, List[FlowNode]] = {0: [], 1: [], 2: []}
    for n in g.nodes:
        cols[n.column].append(n)
    cols[2].sort(key=lambda n: COL_ORDER.get(n.kind, 9))

    def node_h(n: FlowNode, scale: float) -> float:
        return max(n.volume * scale, 44.0 if n.kind == "subsystem" else 16.0)

    total_vol = max(sum(n.volume for n in c) for c in cols.values() if c) or 1.0
    n_max = max(len(c) for c in cols.values())
    scale = max(1e-6, (height - gap * (n_max - 1)) / total_vol)
    for _ in range(10):
        worst = max(sum(node_h(n, scale) for n in c) + gap * (len(c) - 1) for c in cols.values() if c)
        if worst <= height:
            break
        scale *= 0.88
    xs = {0: left, 1: (left + right) / 2 - sub_w / 2, 2: right - thin_w}
    wid = {0: thin_w, 1: sub_w, 2: thin_w}

    def X(x: float, w: float = 0.0) -> float:
        return (rect.left() + rect.right() - x - w) if rtl else x

    box: Dict[str, QRectF] = {}
    for c, nodes in cols.items():
        if not nodes:
            continue
        used = sum(node_h(n, scale) for n in nodes) + gap * (len(nodes) - 1)
        y = top + max(0.0, (height - used) / 2)
        for n in nodes:
            h = node_h(n, scale)
            box[n.id] = QRectF(X(xs[c], wid[c]), y, wid[c], h)
            y += h + gap

    out_used: Dict[str, float] = {}
    in_used: Dict[str, float] = {}
    out_tot: Dict[str, float] = {}
    in_tot: Dict[str, float] = {}
    for e in g.edges:
        out_tot[e.src] = out_tot.get(e.src, 0.0) + e.volume
        in_tot[e.dst] = in_tot.get(e.dst, 0.0) + e.volume

    def thick(n: FlowNode, vol: float, tot: float) -> float:
        return box[n.id].height() * vol / max(tot, n.volume, 1e-9)

    by_id = {n.id: n for n in g.nodes}
    order = {"transfer": 1}
    for e in sorted(g.edges, key=lambda e: (order.get(e.kind, 0), -e.volume)):
        s, d = by_id[e.src], by_id[e.dst]
        bs, bd = box[s.id], box[d.id]
        ts, td = thick(s, e.volume, out_tot[s.id]), thick(d, e.volume, in_tot[d.id])
        ys = bs.top() + out_used.get(s.id, 0.0)
        yd = bd.top() + in_used.get(d.id, 0.0)
        out_used[s.id] = out_used.get(s.id, 0.0) + ts
        in_used[d.id] = in_used.get(d.id, 0.0) + td
        path = QPainterPath()
        if e.kind == "transfer" and d.kind == "subsystem":
            sign = -1.0 if rtl else 1.0
            x1 = bs.right() if not rtl else bs.left()
            x2 = bd.right() if not rtl else bd.left()
            bulge = sign * (46.0 + 10.0 * (abs(ys - yd) / max(height, 1)) * 10)
            path.moveTo(x1, ys)
            path.cubicTo(x1 + bulge, ys, x2 + bulge, yd, x2, yd)
            path.lineTo(x2, yd + td)
            path.cubicTo(x2 + bulge, yd + td, x1 + bulge, ys + ts, x1, ys + ts)
            path.closeSubpath()
        else:
            if rtl:
                x1, x2 = bs.left(), bd.right()
            else:
                x1, x2 = bs.right(), bd.left()
            mx = (x1 + x2) / 2
            path.moveTo(x1, ys)
            path.cubicTo(mx, ys, mx, yd, x2, yd)
            path.lineTo(x2, yd + td)
            path.cubicTo(mx, yd + td, mx, ys + ts, x1, ys + ts)
            path.closeSubpath()
        col = QColor(EDGE_COLOR[e.kind])
        col.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPath(path)

    f = QFont(p.font())
    f.setPixelSize(12)
    p.setFont(f)
    for n in g.nodes:
        b = box[n.id]
        if n.kind == "subsystem":
            c = QColor(STATUS_COLOR.get(n.status, "#0B3D78"))
            grad = QLinearGradient(b.topLeft(), b.bottomLeft())
            grad.setColorAt(0, c.lighter(115))
            grad.setColorAt(1, c)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(b, 9, 9)
            p.setPen(QColor("#FFFFFF"))
            fb = QFont(f)
            fb.setBold(True)
            p.setFont(fb)
            p.drawText(b.adjusted(4, 3, -4, -b.height() / 2 + 2), Qt.AlignmentFlag.AlignCenter, n.name)
            p.setFont(f)
            p.drawText(b.adjusted(4, b.height() / 2 - 4, -4, -3), Qt.AlignmentFlag.AlignCenter, _num(n.volume) + " m³")
        else:
            c = QColor(NODE_COLOR.get(n.kind, "#64748B"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(b, 4, 4)
            p.setPen(QColor(COL["text"]))
            label_w = pad_x - 14
            on_left = (n.column == 0) != rtl
            lr = QRectF(b.left() - 6 - label_w, b.center().y() - 18, label_w, 36) if on_left \
                else QRectF(b.right() + 6, b.center().y() - 18, label_w, 36)
            al = Qt.AlignmentFlag.AlignRight if on_left else Qt.AlignmentFlag.AlignLeft
            p.drawText(lr, al | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, f"{n.name}\n{_num(n.volume)} m³")
        hits.append((b, n))
    return hits


def render_png(g: FlowGraph, path: str, rtl: bool, t: Translator, width: int = 1500, height: int = 820) -> bool:
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    paint_flow(p, QRectF(0, 0, width, height), g, rtl, t)
    p.end()
    return img.save(path)


def render_image(g: FlowGraph, rtl: bool, t: Translator, width: int = 1500, height: int = 820) -> QImage:
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    paint_flow(p, QRectF(0, 0, width, height), g, rtl, t)
    p.end()
    return img


class FlowDiagram(QWidget):
    node_clicked = Signal(str)

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.graph = FlowGraph()
        self._hits: List[Tuple[QRectF, FlowNode]] = []
        self.setMinimumHeight(540)
        self.setMouseTracking(True)

    def set_graph(self, g: FlowGraph) -> None:
        self.graph = g
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        self._hits = paint_flow(p, QRectF(self.rect()), self.graph, self.t.rtl, self.t)
        p.end()

    def _node_at(self, pos) -> Optional[FlowNode]:
        for r, n in self._hits:
            if r.adjusted(-3, -3, 3, 3).contains(QPointF(pos)):
                return n
        return None

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        n = self._node_at(ev.position())
        if n is None:
            QToolTip.hideText()
            self.unsetCursor()
            return
        self.setCursor(Qt.CursorShape.PointingHandCursor if n.kind == "subsystem" else Qt.CursorShape.ArrowCursor)
        QToolTip.showText(ev.globalPosition().toPoint(), f"{n.name}: {_num(n.volume)} m³", self)

    def mousePressEvent(self, ev) -> None:  # noqa: N802 (Qt API)
        n = self._node_at(ev.position())
        if n is not None and n.kind == "subsystem":
            self.node_clicked.emit(n.name)


class FlowTab(_Scroll):
    subsystem_requested = Signal(str)
    links_changed = Signal()

    def __init__(self, t: Translator):
        super().__init__()
        self.t = t
        self.plant: Optional[Plant] = None
        self._analysis: Optional[Analysis] = None
        self._loading = False
        self.msg = _message_label()
        self.lay.addWidget(self.msg)

        self.diagram = FlowDiagram(t)
        self.diagram.node_clicked.connect(self.subsystem_requested)
        legend = QLabel()
        legend.setTextFormat(Qt.TextFormat.RichText)
        items = [("intake", t("flow_l_intake")), ("transfer", t("flow_l_transfer")), ("discharge", t("flow_l_discharge")),
                 ("evap", t("flow_l_evap")), ("product", t("flow_l_product")), ("loss", t("flow_l_loss"))]
        legend.setText("&nbsp;&nbsp;&nbsp;".join(f"<span style='color:{EDGE_COLOR[k]}'>■</span> {txt}" for k, txt in items))
        legend.setObjectName("cardnote")
        hint = QLabel(t("flow_hint"))
        hint.setObjectName("cardnote")
        hint.setWordWrap(True)
        save = button(t("flow_save"), "", self._save_png)
        self.lay.addWidget(card(t("tab_flow"), self.diagram, legend, hint, save))

        self.table = DataTable([t("flow_from"), t("flow_to"), t("flow_volume")], ["combo", "combo", "num"])
        self.table.setMinimumHeight(170)
        self.table.changed.connect(self._links_edited)
        add = button("+  " + t("add"), "primary", lambda: self.table.add_row([self._names()[0] if self._names() else "", "", 0]))
        rem = button(t("remove"), "danger", self.table.remove_selected)
        self.lay.addWidget(card(t("flow_links"), self.table, add, rem, note=t("flow_links_note")))
        self.lay.addStretch(1)

    # ------------------------------------------------------------------ data
    def _names(self) -> List[str]:
        return [s.name for s in (self.plant.subsystems if self.plant else [])]

    def refresh(self, plant: Plant, a: Optional[Analysis]) -> None:
        self.plant = plant
        self._analysis = a
        names = self._names()
        self.table.combo_items = {0: names, 1: names}
        self._loading = True
        self.table.set_rows([[x.src, x.dst, x.volume] for x in plant.links])
        self._loading = False
        self._redraw()

    def _redraw(self) -> None:
        if self._analysis is None or not self.plant or not self.plant.subsystems:
            self.msg.setText(self.t("no_data"))
            self.diagram.set_graph(FlowGraph())
            return
        self.msg.setText("")
        self.diagram.set_graph(build_flow(self._analysis, labels_for(self.t)))

    def update_analysis(self, a: Optional[Analysis]) -> None:
        self._analysis = a
        self._redraw()

    def show_error(self, text: str) -> None:
        self.msg.setText(text)

    def _links_edited(self) -> None:
        if self._loading or self.plant is None:
            return
        from ..model import Transfer
        old = {x.src for x in self.plant.links} | {x.dst for x in self.plant.links}
        links = []
        for src, dst, vol in self.table.rows():
            if src and dst and src != dst and vol and vol > 0:
                links.append(Transfer(src, dst, float(vol)))
        self.plant.links = links
        sync_transfers(self.plant, touched=old)
        self.links_changed.emit()

    def _save_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.t("flow_save"), "flow.png", "PNG (*.png)")
        if path:
            render_png(self.diagram.graph, path, self.t.rtl, self.t)
