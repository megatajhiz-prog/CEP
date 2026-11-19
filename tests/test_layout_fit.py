"""The window must fit small (scaled) laptop screens and every page must be reachable by scrolling. Runs in CI (needs PySide6)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QMessageBox, QScrollArea, QVBoxLayout, QWidget  # noqa: E402

# a 1366 x 768 laptop at 125 % scaling leaves about 1093 x 590 logical pixels below the taskbar
SMALL = QRect(0, 0, 1093, 590)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))


def _small_window(monkeypatch, lang="fa", screen=SMALL):
    from waterprofiler.gui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_avail", staticmethod(lambda: screen))
    w = MainWindow(lang)
    w.show()
    return w


def _mw(w):
    return max(w.minimumWidth(), w.minimumSizeHint().width())


def _widest(area, n=6):
    """The widgets whose own minimum width is not explained by one single child: leaves (a long label, a wide
    drop-down) and rows (several widgets side by side). These are what make a page wider than the window."""
    rows = []
    for c in area.widget().findChildren(QWidget):
        if not c.isVisibleTo(area.widget()):
            continue
        m = _mw(c)
        if m < 260:
            continue
        kids = [k for k in c.children() if isinstance(k, QWidget) and k.isVisibleTo(area.widget())]
        if any(_mw(k) >= m - 70 for k in kids):
            continue
        txt = c.text() if hasattr(c, "text") and callable(c.text) else ""
        lay = type(c.layout()).__name__ if c.layout() is not None else "-"
        rows.append((m, f"{m}px {type(c).__name__}#{c.objectName()} '{str(txt)[:30]}' layout={lay} kids={len(kids)} "
                        f"in {type(c.parentWidget()).__name__}"))
    rows.sort(key=lambda r: -r[0])
    return " || ".join(t for _m, t in rows[:n])


def _scroll_areas(page):
    out = []
    for a in ([page] if isinstance(page, QScrollArea) else []) + page.findChildren(QScrollArea):
        if a.isVisibleTo(page) and a.viewport().height() > 0:
            out.append(a)
    return out


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_window_opens_inside_a_small_screen(app, monkeypatch, lang):
    w = _small_window(monkeypatch, lang)
    app.processEvents()
    assert w.width() <= SMALL.width() and w.height() <= SMALL.height(), (w.width(), w.height())
    assert w.minimumWidth() <= SMALL.width() and w.minimumHeight() <= SMALL.height()
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        app.processEvents()
        assert w.width() <= SMALL.width() and w.height() <= SMALL.height(), (i, w.width(), w.height())
    w.close()


def test_sidebar_scrolls_to_the_last_page(app, monkeypatch):
    w = _small_window(monkeypatch)
    app.processEvents()
    sc = w.sidebar_scroll
    assert sc.verticalScrollBar().maximum() > 0          # the page list is taller than the window: it must scroll
    sc.verticalScrollBar().setValue(sc.verticalScrollBar().maximum())
    app.processEvents()
    last = w.nav[-1]
    bottom = last.mapTo(sc.viewport(), QPoint(0, last.height())).y()
    assert bottom <= sc.viewport().height() + 2
    sc.verticalScrollBar().setValue(0)
    app.processEvents()
    assert w.nav[0].mapTo(sc.viewport(), QPoint(0, 0)).y() >= -2
    w.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_every_page_fits_the_width_and_scrolls_to_its_end(app, monkeypatch, lang):
    from waterprofiler.sample import demo_with_history
    w = _small_window(monkeypatch, lang)
    w._set_plant(demo_with_history(lang), None)
    bad = []
    for i, (_icon, name_key, _d, page) in enumerate(w._pages):
        if page is w.pfd_tab:                      # the diagram page is a canvas, not a scrolled form
            continue
        w.tabs.setCurrentIndex(i)
        app.processEvents()
        for a in _scroll_areas(page):
            hs, vs = a.horizontalScrollBar(), a.verticalScrollBar()
            if hs.maximum() > 0:
                bad.append(f"{name_key}: wider than the window by {hs.maximum()} px (viewport {a.viewport().width()}) <- {_widest(a)}")
            vs.setValue(vs.maximum())
            app.processEvents()
            body = a.widget()
            end = body.mapTo(a.viewport(), QPoint(0, body.height())).y()
            if end > a.viewport().height() + 2:
                bad.append(f"{name_key}: the end of the page is {end - a.viewport().height()} px out of reach")
            vs.setValue(0)
    w.close()
    assert not bad, "\n".join(bad)


def test_mouse_wheel_over_a_number_box_scrolls_the_page(app):
    from waterprofiler.gui.widgets import install_wheel_guard
    install_wheel_guard(app)
    area = QScrollArea()
    area.setWidgetResizable(True)
    body = QWidget()
    lay = QVBoxLayout(body)
    spin = QDoubleSpinBox()
    spin.setValue(5.0)
    lay.addWidget(spin)
    other = QDoubleSpinBox()
    lay.addWidget(other)
    filler = QWidget()
    filler.setMinimumHeight(2000)
    lay.addWidget(filler)
    area.setWidget(body)
    area.resize(300, 200)
    area.show()
    other.setFocus()                      # the box under the mouse is not the one being edited
    app.processEvents()
    assert not spin.hasFocus()
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(spin, ev)
    app.processEvents()
    assert spin.value() == 5.0
    assert area.verticalScrollBar().value() > 0
    area.close()
