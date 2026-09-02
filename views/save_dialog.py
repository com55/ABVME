"""
Save Dialog - Dialog for saving bundle files with compression options
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from models.save_options import (
    CRC_LABELS,
    PACKER_LABELS,
    RESOURCE_LABELS,
    SAVE_OPTION_HELP,
)
from viewmodels import MainViewModel

_CHANGED_FOREGROUND = QColor("#7DCEA0")


class _ForegroundRoleDelegate(QStyledItemDelegate):
    """Paint QListWidget ForegroundRole even when a stylesheet is on the view."""

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        if not (index.flags() & Qt.ItemFlag.ItemIsSelectable):
            option.state &= ~QStyle.StateFlag.State_MouseOver  # type: ignore[attr-defined]
        data = index.data(Qt.ItemDataRole.ForegroundRole)
        if data is None:
            return
        color = data.color() if isinstance(data, QBrush) else QColor(data)
        option.palette.setColor(QPalette.ColorRole.Text, color)  # type: ignore[attr-defined]
        option.palette.setColor(QPalette.ColorRole.HighlightedText, color)  # type: ignore[attr-defined]


class SaveDialog(QDialog):
    """
    Dialog for selecting files and compression mode for saving bundles
    """

    # Signals
    save_all_requested = Signal(str, str, str, str)  # dir, packer, resource, crc
    save_selected_requested = Signal(
        str, str, str, str, str
    )  # filepath, output_path, packer, resource, crc
    save_multiple_selected_requested = Signal(list, str, str, str, str)

    def __init__(self, viewmodel: MainViewModel, parent=None):
        super().__init__(parent)
        self.viewmodel = viewmodel
        self.output_dir = None
        self._setup_ui()
        self._load_files()

    def _setup_ui(self):
        """Setup UI components"""
        self.setWindowTitle("Save Asset Bundles")
        self.setModal(True)
        self.setMinimumSize(800, 400)

        # Main layout
        main_layout = QHBoxLayout(self)

        # Left side: File list
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.file_list.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.file_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.file_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.file_list.verticalScrollBar().setSingleStep(10)
        self.file_list.horizontalScrollBar().setSingleStep(10)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setItemDelegate(_ForegroundRoleDelegate(self.file_list))
        main_layout.addWidget(self.file_list, stretch=3)

        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(10)
        controls_layout.setContentsMargins(5, 0, 0, 0)

        self.save_options_btn = QToolButton()
        self.save_options_btn.setText("Save Options")
        self.save_options_btn.setCheckable(True)
        self.save_options_btn.setChecked(False)
        self.save_options_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.save_options_btn.setArrowType(Qt.ArrowType.RightArrow)
        controls_layout.addWidget(self.save_options_btn)

        self.save_options_panel = QWidget()
        panel_layout = QVBoxLayout(self.save_options_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(10)

        (
            compression_row,
            self.compression_heading,
            self.compression_help,
        ) = self._option_heading("Compression Method")
        panel_layout.addWidget(compression_row)
        self.compression_combo = QComboBox()
        self.compression_combo.addItems(list(PACKER_LABELS.keys()))
        panel_layout.addWidget(self.compression_combo)

        (
            resource_row,
            self.resource_heading,
            self.resource_help,
        ) = self._option_heading("Resource Patch Method")
        panel_layout.addWidget(resource_row)
        self.resource_combo = QComboBox()
        self.resource_combo.addItems(list(RESOURCE_LABELS.keys()))
        panel_layout.addWidget(self.resource_combo)

        crc_row, self.crc_heading, self.crc_help = self._option_heading(
            "CRC Correction"
        )
        panel_layout.addWidget(crc_row)
        self.crc_combo = QComboBox()
        self.crc_combo.addItems(list(CRC_LABELS.keys()))
        panel_layout.addWidget(self.crc_combo)

        self.save_options_panel.setVisible(False)
        self.save_options_btn.toggled.connect(self._on_save_options_toggled)
        controls_layout.addWidget(self.save_options_panel)

        self._init_combos_from_viewmodel()

        controls_layout.addStretch()

        self.show_only_changed_checkbox = QCheckBox("Show only changed files")
        self.show_only_changed_checkbox.setChecked(
            self.viewmodel.show_only_changed_files
        )
        self.show_only_changed_checkbox.clicked.connect(self._on_filter_clicked)
        controls_layout.addWidget(self.show_only_changed_checkbox)

        self.save_selected_btn = QPushButton("Save Selected")
        self.save_selected_btn.setToolTip("Save selected bundle file")
        self.save_selected_btn.clicked.connect(self._on_save_selected_clicked)
        self.save_selected_btn.setEnabled(False)
        controls_layout.addWidget(self.save_selected_btn)

        self.save_all_btn = QPushButton("Save All Changed")
        self.save_all_btn.setToolTip("Save all modified bundle files")
        self.save_all_btn.clicked.connect(self._on_save_all_clicked)
        controls_layout.addWidget(self.save_all_btn)

        main_layout.addLayout(controls_layout, stretch=1)

        self.file_list.itemSelectionChanged.connect(self._on_selection_changed)

    def _option_heading(self, title: str) -> tuple[QWidget, QLabel, QLabel]:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        heading = QLabel(title)
        help_icon = QLabel("ⓘ")
        help_icon.setToolTip(SAVE_OPTION_HELP[title])
        help_icon.setCursor(Qt.CursorShape.WhatsThisCursor)
        layout.addWidget(heading)
        layout.addWidget(help_icon)
        layout.addStretch()
        return row, heading, help_icon

    def _on_save_options_toggled(self, checked: bool) -> None:
        self.save_options_panel.setVisible(checked)
        arrow = Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        self.save_options_btn.setArrowType(arrow)

    def _on_filter_clicked(self, checked: bool) -> None:
        self.viewmodel.set_show_only_changed_files(checked)
        self._load_files()

    def _add_placeholder(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.file_list.addItem(item)

    def _add_file_row(self, filepath: str, is_changed: bool) -> None:
        filename = Path(filepath).name
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, filepath)
        if is_changed:
            item.setText(f"* {filename}")
            item.setForeground(QBrush(_CHANGED_FOREGROUND))
            item.setToolTip(f"{filepath} (modified)")
        else:
            item.setText(filename)
            item.setToolTip(filepath)
        self.file_list.addItem(item)

    def _load_files(self):
        self.file_list.clear()
        all_files = self.viewmodel.get_source_files()
        if not all_files:
            self._add_placeholder("No files loaded")
        else:
            if self.viewmodel.show_only_changed_files:
                visible = [(path, changed) for path, changed in all_files if changed]
            else:
                visible = all_files
            if not visible:
                self._add_placeholder("No changed files")
            else:
                for filepath, is_changed in visible:
                    self._add_file_row(filepath, is_changed)
        self.save_all_btn.setEnabled(self.viewmodel.has_changed_files())
        self._on_selection_changed()

    def _selected_filepaths(self) -> list[str]:
        paths: list[str] = []
        for item in self.file_list.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(path, str) and path:
                paths.append(path)
        return paths

    def _on_selection_changed(self):
        self.save_selected_btn.setEnabled(bool(self._selected_filepaths()))

    def _label_for(self, labels: dict[str, str], value: object) -> str:
        for label, stored in labels.items():
            if stored == value:
                return label
        return next(iter(labels))

    def _init_combos_from_viewmodel(self) -> None:
        self.compression_combo.setCurrentText(
            self._label_for(PACKER_LABELS, self.viewmodel.packer)
        )
        self.resource_combo.setCurrentText(
            self._label_for(RESOURCE_LABELS, self.viewmodel.resource_patch_mode)
        )
        self.crc_combo.setCurrentText(
            self._label_for(CRC_LABELS, self.viewmodel.crc_mode)
        )

    def _scratch_modes(self) -> tuple[str, str, str]:
        packer = PACKER_LABELS.get(self.compression_combo.currentText(), "original")
        resource = RESOURCE_LABELS.get(
            self.resource_combo.currentText(), "resource_patch"
        )
        crc = CRC_LABELS.get(self.crc_combo.currentText(), "auto")
        return packer, resource, crc

    def _select_output_directory(self) -> bool:
        """
        Show directory selection dialog
        Returns True if directory was selected, False otherwise
        """
        if self.output_dir is None:
            default_dir = self.viewmodel.get_dialog_start_directory()
        else:
            default_dir = str(self.output_dir)

        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", default_dir
        )

        if directory:
            self.output_dir = Path(directory)
            return True
        return False

    def _on_save_all_clicked(self):
        """Handle Save All button click"""
        if not self._select_output_directory():
            return

        packer, resource, crc = self._scratch_modes()

        self.accept()

        # Emit signal
        self.save_all_requested.emit(str(self.output_dir), packer, resource, crc)

    def _on_save_selected_clicked(self):
        """Handle Save Selected button click"""
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return

        # Check if multiple files selected
        if len(self._selected_filepaths()) > 1:
            self._save_multiple_selected()
        else:
            self._save_single_selected(selected_items[0])

    def _save_single_selected(self, item: QListWidgetItem):
        """Save a single selected file with Save As dialog"""
        # Get selected file info
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(filepath, str) or not filepath:
            return
        filename = Path(filepath).name

        # Show Save As dialog
        if self.output_dir is None:
            default_path = str(
                Path(self.viewmodel.get_dialog_start_directory()) / filename
            )
        else:
            default_path = str(self.output_dir / filename)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As...",
            default_path,
            "Asset Bundles (*.bundle *.unity3d);;All Files (*.*)",
        )

        if not save_path:
            return

        # Extract directory and update for next time
        save_path = Path(save_path)
        self.output_dir = save_path.parent

        packer, resource, crc = self._scratch_modes()

        self.accept()

        # Emit signal with full output path
        self.save_selected_requested.emit(
            filepath, str(save_path), packer, resource, crc
        )

    def _save_multiple_selected(self) -> None:
        """Save multiple selected files to a directory"""
        # Collect filepaths
        filepaths = self._selected_filepaths()
        if not filepaths:
            return

        # Show directory selection dialog
        if not self._select_output_directory():
            return

        packer, resource, crc = self._scratch_modes()

        self.accept()

        # Emit signal
        self.save_multiple_selected_requested.emit(
            filepaths, str(self.output_dir), packer, resource, crc
        )

    def on_save_finished(self, success: bool, message: str):
        """
        Handle save completion

        Args:
            success: Whether save was successful
            message: Result message
        """
        if not success:
            QMessageBox.critical(self, "Save Failed", message)
        elif "CRC not applied" in message or "Resource patch:" in message:
            QMessageBox.warning(self, "Save Complete", message)
        else:
            QMessageBox.information(self, "Save Complete", message)
