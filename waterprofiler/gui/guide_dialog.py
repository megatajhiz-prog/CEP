"""The user guide window (Help > User guide): contents list, search and the Markdown text."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLineEdit, QTextBrowser, QVBoxLayout

from ..guide_text import GUIDE_FA
from ..i18n import Translator
from .widgets import button


def headings(md: str):
    """The '## ' section titles of the guide, in order."""
    return [ln[3:].strip() for ln in md.splitlines() if ln.startswith("## ")]


class GuideDialog(QDialog):
    def __init__(self, t: Translator, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("user_guide"))
        self.resize(900, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)       # the guide is in Persian
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.toc = QComboBox()
        self.toc.addItem(t("guide_contents"))
        self.toc.addItems(headings(GUIDE_FA))
        self.toc.currentIndexChanged.connect(self._goto)
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("guide_search"))
        self.search.returnPressed.connect(self._find)
        bar.addWidget(self.toc, 1)
        bar.addWidget(self.search, 1)
        bar.addWidget(button(t("guide_find"), "", self._find))
        lay.addLayout(bar)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setMarkdown(GUIDE_FA)
        lay.addWidget(self.view, 1)

    def _goto(self, i: int) -> None:
        if i <= 0:
            return
        self.view.moveCursor(QTextCursor.MoveOperation.Start)
        self.view.find(self.toc.itemText(i))
        self.view.ensureCursorVisible()

    def _find(self) -> None:
        text = self.search.text().strip()
        if text and not self.view.find(text):                          # wrap around
            self.view.moveCursor(QTextCursor.MoveOperation.Start)
            self.view.find(text)
