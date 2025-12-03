"""
Save Dialog - Dialog for saving bundle files with compression options
"""

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QComboBox, QLabel, QFileDialog, QMessageBox
)

from viewmodels import MainViewModel


class SaveDialog(QDialog):
    """
    Dialog for selecting files and compression mode for saving bundles
    """
    # Signals
    save_all_requested = Signal(str, str)  # output_dir, packer
    save_selected_requested = Signal(str, str, str)  # filepath, output_path, packer
    
    # Compression mode mapping
    COMPRESSION_MODES = {
        "None": None,
        "LZ4": "lz4",
        "LZMA": "lzma",
        "Auto": "original"
    }
    
    def __init__(self, viewmodel: MainViewModel, parent=None):
        super().__init__(parent)
        self.viewmodel = viewmodel
        self.output_dir = None
        self._setup_ui()
        self._load_files()
        
    def _setup_ui(self):
        """Setup UI components"""
        self.setWindowTitle("Save Bundle Files")
        self.setModal(True)
        self.setMinimumSize(600, 300)
        
        # Main layout
        main_layout = QHBoxLayout(self)
        
        # Left side: File list
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        main_layout.addWidget(self.file_list, stretch=3)
        
        # Right side: Controls
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(10)
        
        # Compression mode section
        compression_label = QLabel("Compression mode")
        controls_layout.addWidget(compression_label)
        
        self.compression_combo = QComboBox()
        self.compression_combo.addItems(list(self.COMPRESSION_MODES.keys()))
        self.compression_combo.setCurrentText("Auto")
        controls_layout.addWidget(self.compression_combo)
        
        controls_layout.addStretch()
        
        # Save All button
        self.save_all_btn = QPushButton("Save All")
        self.save_all_btn.setToolTip("Save all modified bundle files")
        self.save_all_btn.clicked.connect(self._on_save_all_clicked)
        controls_layout.addWidget(self.save_all_btn)
        
        # Save Selected button
        self.save_selected_btn = QPushButton("Save Selected")
        self.save_selected_btn.setToolTip("Save selected bundle file")
        self.save_selected_btn.clicked.connect(self._on_save_selected_clicked)
        self.save_selected_btn.setEnabled(False)
        controls_layout.addWidget(self.save_selected_btn)
        
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
        
    def _get_compression_mode(self) -> str:
        """Get selected compression mode"""
        mode_text = self.compression_combo.currentText()
        return self.COMPRESSION_MODES.get(mode_text, "original")
        
    def _select_output_directory(self) -> bool:
        """
        Show directory selection dialog
        Returns True if directory was selected, False otherwise
        """
        if self.output_dir is None:
            default_dir = str(Path.cwd() / "output")
        else:
            default_dir = str(self.output_dir)
            
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            default_dir
        )
        
        if directory:
            self.output_dir = Path(directory)
            return True
        return False
        
    def _on_save_all_clicked(self):
        """Handle Save All button click"""
        if not self._select_output_directory():
            return
            
        packer = self._get_compression_mode()
        
        # Disable dialog during save
        self.setEnabled(False)
        
        # Emit signal
        self.save_all_requested.emit(str(self.output_dir), packer)
        
    def _on_save_selected_clicked(self):
        """Handle Save Selected button click"""
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
            
        # Get selected file info
        filepath = selected_items[0].data(Qt.ItemDataRole.UserRole)
        filename = Path(filepath).name
        
        # Show Save As dialog
        if self.output_dir is None:
            default_path = str(Path.cwd() / "output" / filename)
        else:
            default_path = str(self.output_dir / filename)
            
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Bundle File",
            default_path,
            "Bundle Files (*.bundle);;All Files (*.*)"
        )
        
        if not save_path:
            return
            
        # Extract directory and update for next time
        save_path = Path(save_path)
        self.output_dir = save_path.parent
        
        packer = self._get_compression_mode()
        
        # Disable dialog during save
        self.setEnabled(False)
        
        # Emit signal with full output path
        self.save_selected_requested.emit(filepath, str(save_path), packer)
        
    def on_save_finished(self, success: bool, message: str, close_dialog: bool = False):
        """
        Handle save completion
        
        Args:
            success: Whether save was successful
            message: Result message
            close_dialog: Whether to close dialog after showing message
        """
        # Re-enable dialog
        self.setEnabled(True)
        
        # Show result message
        if success:
            QMessageBox.information(self, "Save Complete", message)
            if close_dialog:
                self.accept()  # Close dialog
        else:
            QMessageBox.critical(self, "Save Failed", message)

