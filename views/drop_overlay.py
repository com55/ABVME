"""Full-window drop overlay — visual only; not a drop target."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from utilities.drop_classifier import DropAction, DropDecision

_MAX_VISIBLE_FILES = 5

# Light tinted panels; titles are a darker shade of the same action color.
_PANEL_STYLES = {
    DropAction.OPEN: "background-color: rgba(150, 198, 230, 170);",
    DropAction.REPLACE: "background-color: rgba(150, 205, 165, 170);",
    DropAction.REPLACE_CONFIRM: "background-color: rgba(150, 205, 165, 170);",
    DropAction.REJECT: "background-color: rgba(230, 160, 160, 170);",
}

_TITLE_COLORS = {
    DropAction.OPEN: "#1a4d73",
    DropAction.REPLACE: "#1b5c32",
    DropAction.REPLACE_CONFIRM: "#1b5c32",
    DropAction.REJECT: "#8a2424",
}

_TITLE_STYLE = (
    "background-color: transparent; font-size: 42px; font-weight: 800;"
)
_BODY_STYLE = (
    "background-color: transparent; color: #1a1a1a;"
    " font-size: 13px; font-weight: 400;"
)
_ARROW_STYLE = (
    "background-color: transparent; color: #1a1a1a;"
    " font-size: 13px; font-weight: 700;"
)


def _elide(label: QLabel, text: str, width: int) -> None:
    # Skip elide until layout has a real width — otherwise names collapse to "n".
    if width < 40:
        label.setText(text)
        label.setToolTip("")
        return
    metrics = QFontMetrics(label.font())
    elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)
    label.setText(elided)
    label.setToolTip(text if elided != text else "")


def _visible_names(paths: tuple[str, ...]) -> list[str]:
    names = [Path(path).name for path in paths]
    extra = len(names) - _MAX_VISIBLE_FILES
    if extra > 0:
        return names[:_MAX_VISIBLE_FILES] + [f"+ {extra} more"]
    return names


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
        _elide(self._left, self._left_text, max(self._left.width(), 0))
        _elide(self._right, self._right_text, max(self._right.width(), 0))


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
        self._body_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 36, 0, 0)
        layout.addWidget(self._title, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        layout.addWidget(self._body, 0)
        layout.addStretch(1)

        self._full_title = ""
        self._shown_key: tuple | None = None
        self._line_labels: list[tuple[QLabel, str]] = []
        self._replace_rows: list[_ReplaceRow] = []
        self.hide()

    def matches(self, decision: DropDecision, target_name: str | None) -> bool:
        return self.isVisible() and self._shown_key == _decision_key(decision, target_name)

    def show_decision(
        self,
        decision: DropDecision,
        target_name: str | None = None,
    ) -> None:
        key = _decision_key(decision, target_name)
        if self.isVisible() and key == self._shown_key:
            return
        self._shown_key = key
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
        self._shown_key = None
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

        names = _visible_names(decision.file_paths)
        is_replace = decision.action in {DropAction.REPLACE, DropAction.REPLACE_CONFIRM}
        if is_replace and names:
            right = target_name or _target_from_detail(decision.detail)
            for name in names:
                if name.startswith("+ "):
                    self._add_line(name)
                    continue
                row = _ReplaceRow(name, right, self._body)
                self._body_layout.addWidget(row)
                self._replace_rows.append(row)
            return

        lines = names if names else [decision.detail]
        for line in lines:
            self._add_line(line)

    def _add_line(self, text: str) -> None:
        label = QLabel(self._body)
        label.setStyleSheet(_BODY_STYLE)
        label.setWordWrap(False)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._body_layout.addWidget(label)
        self._line_labels.append((label, text))

    def _apply_elide(self) -> None:
        _elide(self._title, self._full_title, self.width() - 96)
        body_width = self._body.width() - 8
        for label, text in self._line_labels:
            _elide(label, text, body_width)
        for row in self._replace_rows:
            row.apply_elide()


def _decision_key(
    decision: DropDecision,
    target_name: str | None,
) -> tuple:
    return (decision.action, decision.file_paths, decision.title, target_name)


def _target_from_detail(detail: str) -> str:
    if " → " in detail:
        return detail.rsplit(" → ", 1)[-1]
    return detail
