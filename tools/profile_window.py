"""Time building and showing the main window (used by CI to find why start-up is slow)."""
import faulthandler
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
faulthandler.dump_traceback_later(150, exit=True)       # a hang prints where it is stuck

from PySide6.QtWidgets import QApplication


def stamp(label, t0):
    print(f"{label:<28}{time.perf_counter() - t0:7.1f}s", flush=True)
    return time.perf_counter()


t = time.perf_counter()
app = QApplication.instance() or QApplication([])
from waterprofiler.gui.main_window import MainWindow
from waterprofiler.sample import demo_with_history
t = stamp("imports", t)
w = MainWindow("fa")
t = stamp("construct window", t)
w.show()
app.processEvents()
t = stamp("show", t)
w._set_plant(demo_with_history("fa"), None)
app.processEvents()
t = stamp("load demo plant", t)
for i in range(w.tabs.count()):
    w.tabs.setCurrentIndex(i)
    app.processEvents()
    t = stamp(f"page {i:2d} {w._pages[i][1]}", t)
w.close()
