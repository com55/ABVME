"""
Save Dialog - Dialog for saving bundle files with compression options
"""

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QComboBox,
    QLabel,
    QFileDialog,
    QMessageBox,
)

from models.save_options import CRC_LABELS, PACKER_LABELS, RESOURCE_LABELS
from viewmodels import MainViewModel


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
        self.setMinimumSize(600, 300)

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
        main_layout.addWidget(self.file_list, stretch=3)

        # Right side: Controls
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(10)
        controls_layout.setContentsMargins(5, 0, 0, 0)

        # Compression mode section
        compression_label = QLabel("Compression Method")
        controls_layout.addWidget(compression_label)

        self.compression_combo = QComboBox()
        self.compression_combo.addItems(list(PACKER_LABELS.keys()))
        controls_layout.addWidget(self.compression_combo)

        resource_label = QLabel("Resource files")
        controls_layout.addWidget(resource_label)
        self.resource_combo = QComboBox()
        self.resource_combo.addItems(list(RESOURCE_LABELS.keys()))
        controls_layout.addWidget(self.resource_combo)

        crc_label = QLabel("CRC")
        controls_layout.addWidget(crc_label)
        self.crc_combo = QComboBox()
        self.crc_combo.addItems(list(CRC_LABELS.keys()))
        controls_layout.addWidget(self.crc_combo)

        self._init_combos_from_viewmodel()

        controls_layout.addStretch()

        # Save Selected button
        self.save_selected_btn = QPushButton("Save Selected")
        self.save_selected_btn.setToolTip("Save selected bundle file")
        self.save_selected_btn.clicked.connect(self._on_save_selected_clicked)
        self.save_selected_btn.setEnabled(False)
        controls_layout.addWidget(self.save_selected_btn)

        # Save All button
        self.save_all_btn = QPushButton("Save All Changed")
        self.save_all_btn.setToolTip("Save all modified bundle files")
        self.save_all_btn.clicked.connect(self._on_save_all_clicked)
        controls_layout.addWidget(self.save_all_btn)

        main_layout.addLayout(controls_layout, stretch=1)

        # Connect selection change
        self.file_list.itemSelectionChanged.connect(self._on_selection_changed)

    def _load_files(self):
        """Load source files into list"""
        files = self.viewmodel.get_source_files()

        for filepath, is_changed in files:
            filename = Path(filepath).name

            # Create list item
            item = QListWidgetItem(filename)
            item.setData(Qt.ItemDataRole.UserRole, filepath)

            # Mark changed files with asterisk
            if is_changed:
                item.setText(f"{filename} *")
                item.setToolTip(f"{filepath} (modified)")
            else:
                item.setToolTip(filepath)

            self.file_list.addItem(item)

        # Update button states
        has_files = len(files) > 0
        has_changed = self.viewmodel.has_changed_files()

        self.save_all_btn.setEnabled(has_changed)

        if not has_files:
            self.file_list.addItem("No files loaded")

    def _on_selection_changed(self):
        """Handle selection change"""
        has_selection = len(self.file_list.selectedItems()) > 0
        self.save_selected_btn.setEnabled(has_selection)

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
        if len(selected_items) > 1:
            self._save_multiple_selected(selected_items)
        else:
            self._save_single_selected(selected_items[0])

    def _save_single_selected(self, item: QListWidgetItem):
        """Save a single selected file with Save As dialog"""
        # Get selected file info
        filepath = item.data(Qt.ItemDataRole.UserRole)
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

    def _save_multiple_selected(self, selected_items: list[QListWidgetItem]):
        """Save multiple selected files to a directory"""
        # Collect filepaths
        filepaths = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]

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
