# PyInstaller spec. Build with:  pyinstaller build/Watra.spec --noconfirm
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = []
brand = os.path.join(ROOT, "assets", "brand")
if os.path.isdir(brand):
    datas.append((brand, os.path.join("assets", "brand")))
fonts = os.path.join(ROOT, "assets", "fonts")
if os.path.isdir(fonts):
    datas.append((fonts, os.path.join("assets", "fonts")))

# Qt modules the program never touches; excluding them keeps the installer small.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtSql", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtNetwork", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "tkinter", "matplotlib", "scipy", "pandas", "pytest",
]

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["openpyxl", "numpy"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Watra",
    icon=os.path.join(ROOT, "assets", "brand", "app.ico"),
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Watra")
