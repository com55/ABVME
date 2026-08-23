"""Full-window drop overlay — visual only; not a drop target."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from utilities.drop_classifier import DropAction, DropDecision

_PANEL_STYLES = {
    DropAction.OPEN: "background-color: rgba(33, 97, 140, 180);",
    DropAction.REPLACE: "background-color: rgba(20, 90, 50, 180);",
    DropAction.REPLACE_CONFIRM: "background-color: rgba(20, 90, 50, 180);",
    DropAction.REJECT: "background-color: rgba(120, 40, 40, 180);",
}

_TITLE_COLORS = {
    DropAction.OPEN: "#041628",
    DropAction.REPLACE: "#03150c",
    DropAction.REPLACE_CONFIRM: "#03150c",
    DropAction.REJECT: "#2a0808",
}

_TITLE_STYLE = (
    "background-color: transparent; font-size: 42px; font-weight: 800;"
)
_BODY_STYLE = (
    "background-color: transparent; color: #f2f2f2;"
    " font-size: 13px; font-weight: 400;"
)
_ARROW_STYLE = (
    "background-color: transparent; color: #f2f2f2;"
    " font-size: 13px; font-weight: 700;"
)


def _elide(label: QLabel, text: str, width: int) -> None:
    if width <= 8:
        label.setText(text)
        return
    metrics = QFontMetrics(label.font())
    elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)
    label.setText(elided)
    label.setToolTip(text if elided != text else "")


class _ReplaceRow(QWidget):
    """One replace line: left name | centered arrow | right name."""

    def __init__(self, left_text: str, right_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._left_text = left_text
        self._right_text = right_text

        self._left = QLabel(self)
        self._arrow = QLabel("→", self)
        self._right = QLabel(self)
        for label in (self._left, self._right):
            label.setStyleSheet(_BODY_STYLE)
            label.setWordWrap(False)
        self._left.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setStyleSheet(_ARROW_STYLE)
        self._arrow.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._right.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(12)
        layout.addWidget(self._left, 1)
        layout.addWidget(self._arrow, 0)
        layout.addWidget(self._right, 1)

    def apply_elide(self) -> None:
        side = max(self._left.width(), 8)
        _elide(self._left, self._left_text, side)
        _elide(self._right, self._right_text, side)


class DropOverlay(QWidget):
    """Mouse-transparent overlay that paints a drop decision over its parent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._title = QLabel(self)
        self._title.setWordWrap(False)
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(48, 0, 48, 0)
        self._body_layout.setSpacing(4)
        self._body_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(2)
        layout.addWidget(self._title, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(16)
        layout.addWidget(self._body, 0)
        layout.addStretch(5)

        self._full_title = ""
        self._line_labels: list[tuple[QLabel, str]] = []
        self._replace_rows: list[_ReplaceRow] = []
        self.hide()

    def show_decision(
        self,
        decision: DropDecision,
        target_name: str | None = None,
    ) -> None:
        self.setStyleSheet(_PANEL_STYLES[decision.action])
        color = _TITLE_COLORS[decision.action]
        self._title.setStyleSheet(f"{_TITLE_STYLE} color: {color};")
        self._full_title = decision.title
        self._rebuild_body(decision, target_name)
        self.show()
        self.raise_()
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        QTimer.singleShot(0, self._apply_elide)

    def clear(self) -> None:
        self.hide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        parent = self.parentWidget()
        if parent is not None and self.isVisible():
            self.setGeometry(parent.rect())
        self._apply_elide()

    def _rebuild_body(self, decision: DropDecision, target_name: str | None) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._line_labels.clear()
        self._replace_rows.clear()

        names = [Path(path).name for path in decision.file_paths]
        is_replace = decision.action in {DropAction.REPLACE, DropAction.REPLACE_CONFIRM}
        if is_replace and names:
            right = target_name or _target_from_detail(decision.detail)
            for name in names:
                row = _ReplaceRow(name, right, self._body)
                self._body_layout.addWidget(row)
                self._replace_rows.append(row)
            return

        lines = names if names else [decision.detail]
        if decision.action == DropAction.REJECT and decision.detail:
            if names:
                lines = names + [decision.detail]
            else:
                lines = [decision.detail]
        for line in lines:
            label = QLabel(self._body)
            label.setStyleSheet(_BODY_STYLE)
            label.setWordWrap(False)
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self._body_layout.addWidget(label)
            self._line_labels.append((label, line))

    def _apply_elide(self) -> None:
        _elide(self._title, self._full_title, max(self.width() - 96, 8))
        body_width = max(self._body.width() - 8, 8)
        for label, text in self._line_labels:
            _elide(label, text, body_width)
        for row in self._replace_rows:
            row.apply_elide()


def _target_from_detail(detail: str) -> str:
    if " → " in detail:
        return detail.rsplit(" → ", 1)[-1]
    return detail
