"""Application entry point."""

from __future__ import annotations

import os
import sys


def _resource_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)          # PyInstaller bundle
    return base or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_fonts(app) -> None:
    from PySide6.QtGui import QFont, QFontDatabase
    fonts = os.path.join(_resource_dir(), "assets", "fonts")
    family = None
    if os.path.isdir(fonts):
        for fn in sorted(os.listdir(fonts)):
            if fn.lower().endswith((".ttf", ".otf")):
                fid = QFontDatabase.addApplicationFont(os.path.join(fonts, fn))
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                family = family or (fams[0] if fams else None)
    if family is None:
        for cand in ("Vazirmatn", "Segoe UI", "Tahoma"):
            if cand in QFontDatabase.families():
                family = cand
                break
    if family:
        app.setFont(QFont(family, 10))


def selftest() -> int:
    """Headless check used by CI on the frozen executable. Returns 0 on success."""
    import tempfile
    from .gui.main_window import MainWindow
    from .balance import plant_balance
    from .sample import demo_plant

    win = MainWindow("fa")
    win._set_plant(demo_plant(), None)
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
    bal = plant_balance(win.plant)
    assert abs(bal.unknown_loss) < 1e-6 * bal.sum_intake, "demo plant balance does not close"
    with tempfile.TemporaryDirectory() as d:
        win.export_xlsx_to(os.path.join(d, "t.xlsx"))
        win.export_pdf_to(os.path.join(d, "t.pdf"))
        for f in ("t.xlsx", "t.pdf"):
            assert os.path.getsize(os.path.join(d, f)) > 2000, f"{f} too small"
    win.collect()
    win._mark_clean()
    win.close()
    print("selftest ok")
    return 0


def main(argv=None) -> int:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from .gui.main_window import APP, ORG, MainWindow

    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(argv)
    if "--selftest" in argv:
        try:
            return selftest()
        except Exception as e:  # noqa: BLE001
            print(f"selftest failed: {e!r}", file=sys.stderr)
            return 1
    app.setOrganizationName(ORG)
    app.setApplicationName(APP)
    _load_fonts(app)
    lang = QSettings(ORG, APP).value("lang", "fa")
    win = MainWindow(lang if lang in ("fa", "en") else "fa")
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
