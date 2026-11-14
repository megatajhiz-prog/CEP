"""Profile building and showing the main window (used by CI to find why GUI tests are slow)."""
import cProfile
import os
import pstats
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
from waterprofiler.gui.main_window import MainWindow

t0 = time.perf_counter()
pr = cProfile.Profile()
pr.enable()
w = MainWindow("fa")
t1 = time.perf_counter()
w.show()
app.processEvents()
t2 = time.perf_counter()
w.action_demo()
app.processEvents()
t3 = time.perf_counter()
for i in range(w.tabs.count()):
    w.tabs.setCurrentIndex(i)
    app.processEvents()
t4 = time.perf_counter()
pr.disable()
print(f"construct {t1 - t0:.1f}s  show {t2 - t1:.1f}s  demo {t3 - t2:.1f}s  all tabs {t4 - t3:.1f}s")
pstats.Stats(pr).sort_stats("cumulative").print_stats(35)
