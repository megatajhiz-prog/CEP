"""A grid of profile inputs (numbers stored in ``plant.profile``), shared by the complex and indicators pages."""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from ..i18n import Translator
from ..indicator_text import PROFILE_LABEL
from ..model import Plant
from .widgets import dspin


class ProfileInputs(QWidget):
    """Groups of labelled number fields; every edit is written straight into the plant profile."""

    changed = Signal()

    def __init__(self, t: Translator, groups: Sequence[tuple]):
        super().__init__()
        self.plant: Optional[Plant] = None
        self._loading = False
        self.spins: Dict[str, object] = {}
        fa = t.lang == "fa"
        iv = QVBoxLayout(self)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(12)
        for g_fa, g_en, names in groups:
            head = QLabel(g_fa if fa else g_en)
            head.setObjectName("cardnote")
            f = head.font()
            f.setBold(True)
            head.setFont(f)
            iv.addWidget(head)
            gw = QWidget()
            grid = QGridLayout(gw)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(8)
            for n, name in enumerate(names):
                lf, le, uf, ue, mx, dec = PROFILE_LABEL[name]
                box = QWidget()
                bl = QVBoxLayout(box)
                bl.setContentsMargins(0, 0, 0, 0)
                bl.setSpacing(3)
                lab = QLabel(f"{lf if fa else le}  ({uf if fa else ue})")
                lab.setObjectName("cardnote")
                lab.setWordWrap(True)
                sp = dspin(maximum=mx, decimals=dec, step=1.0)
                sp.setMinimumWidth(0)
                sp.valueChanged.connect(lambda v, a=name: self._set(a, v))
                self.spins[name] = sp
                bl.addWidget(lab)
                bl.addWidget(sp)
                grid.addWidget(box, n // 4, n % 4)
            for c in range(4):
                grid.setColumnStretch(c, 1)
            iv.addWidget(gw)

    def load(self, plant: Plant) -> None:
        self.plant = plant
        self._loading = True
        for name, sp in self.spins.items():
            sp.setValue(float(getattr(plant.profile, name)))
        self._loading = False

    def _set(self, name: str, value: float) -> None:
        if self._loading or self.plant is None:
            return
        setattr(self.plant.profile, name, float(value))
        self.changed.emit()
