"""Estimate-from-specifications dialog."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox, QVBoxLayout,
)

from ..estimate_apply import PARAMS, estimate
from ..estimators import InputError
from ..i18n import Translator
from .widgets import dspin

PARAM_LABEL = {
    "units": "est_units", "g": "est_g", "r": "est_r", "p": "est_p",
    "hours": "est_hours", "load": "est_load", "tons": "est_tons", "dt": "est_dt",
    "mc": "est_mc", "bc": "est_bc", "fc": "est_fc", "bhp": "est_bhp",
    "employees": "est_emp", "days": "est_days", "lpd": "est_lpd",
    "area": "est_area", "depth": "est_depth",
}

DEFAULTS: Dict[str, Dict[str, float]] = {
    "process": {"units": 1000.0, "g": 1.0, "r": 0.0, "p": 0.0},
    "cooling_tower": {"hours": 6000.0, "load": 0.7, "tons": 100.0, "dt": 5.5, "mc": 300.0, "bc": 1200.0},
    "boiler": {"hours": 7000.0, "load": 0.6, "bhp": 100.0, "fc": 200.0, "mc": 400.0, "bc": 2800.0},
    "sanitary": {"employees": 100.0, "days": 300.0, "lpd": 80.0},
    "irrigation": {"area": 1000.0, "depth": 600.0},
}
FRACTIONS = {"r", "load"}


class EstimateDialog(QDialog):
    def __init__(self, t: Translator, kind: str, params: Dict[str, float], sources: List[str],
                 outlets: List[str], cur_source: Optional[str], cur_outlet: Optional[str], parent=None):
        super().__init__(parent)
        self.t = t
        self.kind = kind
        self.setWindowTitle(f"{t('est_title')} — {t('kind_' + kind)}")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(t("est_note")))
        form = QFormLayout()
        lay.addLayout(form)

        base = dict(DEFAULTS.get(kind, {}))
        base.update({k: v for k, v in (params or {}).items() if k in base})
        self.fields = {}
        for key in PARAMS[kind]:
            sp = dspin(maximum=1e9 if key not in FRACTIONS else 1.0, decimals=4 if key in FRACTIONS or key in ("g", "p") else 2)
            sp.setValue(base.get(key, 0.0))
            self.fields[key] = sp
            form.addRow(t(PARAM_LABEL[key]), sp)

        self.source = QComboBox()
        self.source.addItems(sources)
        if cur_source and cur_source in sources:
            self.source.setCurrentText(cur_source)
        self.outlet = QComboBox()
        self.outlet.addItems([""] + outlets)
        if cur_outlet and cur_outlet in outlets:
            self.outlet.setCurrentText(cur_outlet)
        form.addRow(t("est_source"), self.source)
        form.addRow(t("est_outlet"), self.outlet)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(t("ok"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(t("cancel"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self) -> Dict[str, float]:
        return {k: sp.value() for k, sp in self.fields.items()}

    def selected_source(self) -> str:
        return self.source.currentText()

    def selected_outlet(self) -> Optional[str]:
        return self.outlet.currentText() or None

    def _accept(self) -> None:
        try:
            estimate(self.kind, self.values())   # validate before closing
        except (InputError, KeyError) as e:
            QMessageBox.warning(self, self.t("error"), str(e))
            return
        if not self.selected_source():
            QMessageBox.warning(self, self.t("error"), self.t("catalog_hint"))
            return
        self.accept()
