"""Full-window drop overlay — visual only; not a drop target."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QResizeEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from utilities.drop_classifier import DropAction, DropDecision

_STYLESHEETS = {
    DropAction.OPEN: (
        "background-color: rgba(33, 97, 140, 180); color: white;"
    ),
    DropAction.REPLACE: (
        "background-color: rgba(20, 90, 50, 180); color: white;"
    ),
    DropAction.REPLACE_CONFIRM: (
        "background-color: rgba(20, 90, 50, 180); color: white;"
    ),
    DropAction.REJECT: (
        "background-color: rgba(120, 40, 40, 180); color: white;"
    ),
}


class DropOverlay(QWidget):
    """Mouse-transparent overlay that paints a drop decision over its parent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPixelSize(22)
        font.setBold(True)
        self._label.setFont(font)
        self._label.setStyleSheet("background-color: transparent; color: white;")

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

        self.hide()

    def show_decision(self, decision: DropDecision) -> None:
        self.setStyleSheet(_STYLESHEETS[decision.action])
        self._label.setText(f"{decision.title}\n{decision.detail}")
        self.show()
        self.raise_()
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def clear(self) -> None:
        self.hide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        parent = self.parentWidget()
        if parent is not None and self.isVisible():
            self.setGeometry(parent.rect())
