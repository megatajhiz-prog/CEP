"""Profile building and showing the main window (used by CI to find why GUI tests are slow)."""
import faulthandler
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
from waterprofiler.gui.main_window import MainWindow

faulthandler.dump_traceback_later(60, repeat=True, file=sys.stdout)     # where is it stuck? printed every minute


def lap(msg, t0=[time.perf_counter()]):
    now = time.perf_counter()
    print(f"{msg}: {now - t0[0]:.1f}s", flush=True)
    t0[0] = now


lap("imports")
w = MainWindow("fa")
lap("construct")
w.show()
app.processEvents()
lap("show")
w.action_demo()
app.processEvents()
lap("demo")
for i in range(w.tabs.count()):
    w.tabs.setCurrentIndex(i)
    app.processEvents()
    lap(f"tab {i} {w._pages[i][1]}")
faulthandler.cancel_dump_traceback_later()
