"""Summary dialog for replacing several dropped files at once."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.texture_replace_options import TextureReplaceOptions
from utilities.replace_matcher import FileMatch, MatchStatus, ReplaceTarget

_COL_CHECK, _COL_FILE, _COL_TARGET, _COL_STATUS = range(4)
_HEADERS = ["", "File", "Replace object", "Status"]
_PLACEHOLDER = "Select object..."
_CHECK_SIZE = 16
_CHECK_COLUMN_WIDTH = 30

_MATCHED_TEXT = "Matched by name"
_NO_MATCH_TEXT = "No match - choose one"
# Status shown while a row has no object chosen; a matched row the user
# cleared falls back to the no-match wording via .get().
_STATUS_TEXT = {
    MatchStatus.AMBIGUOUS: "Same name - choose one",
    MatchStatus.NO_MATCH: _NO_MATCH_TEXT,
}

TextureOptionsChooser = Callable[
    [str, ReplaceTarget | None], TextureReplaceOptions | None
]


def _target_label(target: ReplaceTarget) -> str:
    parts = [target.name or "(unnamed)"]
    if target.container:
        parts.append(f"[{target.container}]")
    parts.append(f"#{target.path_id}")
    return "  ".join(parts)


class _ClickCell(QWidget):
    """Cell host where a click anywhere toggles its checkbox."""

    def __init__(self, check: QCheckBox) -> None:
        super().__init__()
        self._check = check

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._check.toggle()
        super().mouseReleaseEvent(event)


class BatchReplaceDialog(QDialog):
    def __init__(
        self,
        matches: list[FileMatch],
        targets: list[ReplaceTarget],
        choose_texture_options: TextureOptionsChooser,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._targets = {target.index: target for target in targets}
        self._choose_texture_options = choose_texture_options
        self._matches = matches
        self._texture_options: TextureReplaceOptions | None = None
        self._combos: list[QComboBox] = []
        self._checks: list[QCheckBox] = []

        self.setWindowTitle(f"Replace {len(matches)} files")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(780, 320)

        self.table = QTableWidget(len(matches), len(_HEADERS), self)
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(_COL_CHECK, _CHECK_COLUMN_WIDTH)
        header.setSectionResizeMode(_COL_FILE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_TARGET, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)

        for row, match in enumerate(matches):
            self._build_row(row, match)

        self.texture_options_button = QPushButton("Texture Options...")
        self.texture_options_button.clicked.connect(self._on_texture_options)
        self.texture_options_button.setVisible(
            any(match.kind == "Texture2D" for match in matches)
        )
        self.hint_label = QLabel("")
        self.cancel_button = QPushButton("Cancel")
        self.replace_button = QPushButton("Replace")
        self.replace_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.replace_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.texture_options_button)
        buttons.addWidget(self.hint_label, 1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.replace_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        self._refresh()

    def _build_row(self, row: int, match: FileMatch) -> None:
        # A real QCheckBox picks up the app's QCheckBox theme; item check
        # indicators do not.
        check = QCheckBox()
        check.setChecked(True)
        # The theme reserves 6px of label spacing, which skews a text-less box.
        check.setStyleSheet(
            "QCheckBox { spacing: 0px; }"
            f"QCheckBox::indicator {{ width: {_CHECK_SIZE}px; height: {_CHECK_SIZE}px; }}"
        )
        check.toggled.connect(lambda _checked: self._refresh())
        host = _ClickCell(check)
        host_layout = QHBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.addWidget(check, 0, Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, _COL_CHECK, host)
        self._checks.append(check)

        name = QTableWidgetItem(Path(match.file_path).name)
        name.setToolTip(match.file_path)
        name.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(row, _COL_FILE, name)

        combo = QComboBox()
        combo.addItem(_PLACEHOLDER, None)
        for target in self._targets.values():
            if target.kind == match.kind:
                combo.addItem(_target_label(target), target.index)
        if match.target_index is not None:
            combo.setCurrentIndex(combo.findData(match.target_index))
        combo.currentIndexChanged.connect(lambda _index: self._refresh())
        self.table.setCellWidget(row, _COL_TARGET, combo)
        self._combos.append(combo)

        status = QTableWidgetItem("")
        status.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(row, _COL_STATUS, status)

    def _is_checked(self, row: int) -> bool:
        return self._checks[row].isChecked()

    def _refresh(self) -> None:
        checked_rows = [row for row in range(len(self._matches)) if self._is_checked(row)]
        chosen = Counter(
            self._combos[row].currentData()
            for row in checked_rows
            if self._combos[row].currentData() is not None
        )
        valid = bool(checked_rows)
        for row, match in enumerate(self._matches):
            target_index = self._combos[row].currentData()
            if not self._is_checked(row):
                text = "Skipped"
            elif target_index is None:
                text = _STATUS_TEXT.get(match.status, _NO_MATCH_TEXT)
                valid = False
            elif chosen[target_index] > 1:
                text = "Same object chosen twice"
                valid = False
            elif target_index == match.target_index:
                text = _MATCHED_TEXT
            else:
                text = "Chosen manually"
            self.table.item(row, _COL_STATUS).setText(text)
        self.replace_button.setText(f"Replace {len(checked_rows)}")
        self.replace_button.setEnabled(valid)
        self.hint_label.setText(
            "" if valid or not checked_rows else "Resolve the rows marked in Status"
        )

    def _on_texture_options(self) -> None:
        for row, match in enumerate(self._matches):
            if match.kind != "Texture2D" or not self._is_checked(row):
                continue
            index = self._combos[row].currentData()
            target = self._targets.get(index) if index is not None else None
            options = self._choose_texture_options(match.file_path, target)
            if options is not None:
                self._texture_options = options
            return

    def texture_options(self) -> TextureReplaceOptions | None:
        return self._texture_options

    def selected_jobs(self) -> list[tuple[str, ReplaceTarget]]:
        jobs: list[tuple[str, ReplaceTarget]] = []
        for row, match in enumerate(self._matches):
            index = self._combos[row].currentData()
            if self._is_checked(row) and index is not None:
                jobs.append((match.file_path, self._targets[index]))
        return jobs
