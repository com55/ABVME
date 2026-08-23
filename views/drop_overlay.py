"""Full-window drop overlay — visual only; not a drop target."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QResizeEvent
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utilities.drop_classifier import DropAction, DropDecision

_MAX_VISIBLE_FILES = 5
_CONTENT_MARGIN = 96

# Light tinted panels. REPLACE_CONFIRM shares REPLACE via _style_action().
_PANEL_STYLES = {
    DropAction.OPEN: "background-color: rgba(117, 180, 255, 170);",
    DropAction.REPLACE: "background-color: rgba(112, 212, 112, 170);",
    DropAction.REJECT: "background-color: rgba(255, 97, 97, 170);",
}

_TITLE_COLORS = {
    DropAction.OPEN: "#FFFFFF",
    DropAction.REPLACE: "#FFFFFF",
    DropAction.REJECT: "#FFFFFF",
}

_TITLE_STYLE = (
    "background-color: transparent; font-size: 42px; font-weight: 800;"
)
_BODY_STYLE = (
    "background-color: transparent; color: #FFFFFF;"
    " font-size: 24px; font-weight: 600;"
)
_ARROW_STYLE = (
    "background-color: transparent; color: #FFFFFF;"
    " font-size: 24px; font-weight: 800;"
)


def _style_action(action: DropAction) -> DropAction:
    if action == DropAction.REPLACE_CONFIRM:
        return DropAction.REPLACE
    return action


def _apply_text_glow(widget: QWidget) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(16.0)
    effect.setOffset(0.0, 1.0)
    effect.setColor(QColor(0, 0, 0, 210))
    widget.setGraphicsEffect(effect)


def _elide(label: QLabel, text: str, width: int) -> None:
    # Skip elide until layout has a real width — otherwise names collapse to "n".
    if width < 40:
        label.setText(text)
        label.setToolTip("")
        return
    label.setMaximumWidth(width)
    label.ensurePolished()
    elided = label.fontMetrics().elidedText(
        text, Qt.TextElideMode.ElideRight, width
    )
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
            _apply_text_glow(label)
        self._left.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setStyleSheet(_ARROW_STYLE)
        self._arrow.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        _apply_text_glow(self._arrow)
        self._right.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(12)
        layout.addWidget(self._left, 1)
        layout.addWidget(self._arrow, 0)
        layout.addWidget(self._right, 1)

    def apply_elide(self, side_width: int) -> None:
        _elide(self._left, self._left_text, side_width)
        _elide(self._right, self._right_text, side_width)


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
        _apply_text_glow(self._title)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(48, 0, 48, 0)
        self._body_layout.setSpacing(10)
        self._body_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 70, 0, 0)
        layout.addWidget(self._title, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)
        layout.addWidget(self._body, 0)
        layout.addStretch(3)

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
        style_key = _style_action(decision.action)
        self.setStyleSheet(_PANEL_STYLES[style_key])
        color = _TITLE_COLORS[style_key]
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

    def _content_width(self) -> int:
        return max(120, self.width() - _CONTENT_MARGIN)

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
        _apply_text_glow(label)
        self._body_layout.addWidget(label)
        self._line_labels.append((label, text))

    def _apply_elide(self) -> None:
        width = self._content_width()
        _elide(self._title, self._full_title, width)
        for label, text in self._line_labels:
            _elide(label, text, width)
        if not self._replace_rows:
            return
        arrow_width = self._replace_rows[0]._arrow.sizeHint().width()
        row_chrome = 24 * 2 + 12 * 2 + arrow_width
        side_width = max(80, (width - row_chrome) // 2)
        for row in self._replace_rows:
            row.apply_elide(side_width)


def _decision_key(
    decision: DropDecision,
    target_name: str | None,
) -> tuple:
    return (decision.action, decision.file_paths, decision.title, target_name)


def _target_from_detail(detail: str) -> str:
    if " → " in detail:
        return detail.rsplit(" → ", 1)[-1]
    return detail
