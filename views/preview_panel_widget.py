"""
Preview Panel Widget - View component for displaying asset previews
"""

import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QStackedWidget, QTextEdit, QPlainTextEdit, QLabel, QTabWidget
)
from PIL.Image import Image

from views.components.photoviewer import PhotoViewer
from models import AssetInfo, ResultStatus

log = logging.getLogger("ABVME")

class PreviewPanelWidget(QWidget):
    """
    Widget for displaying asset previews
    Supports Image, Text, and Placeholder views
    """
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dump_asset: AssetInfo | None = None
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tab widget as main container
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        
        # ===== Tab 1: Preview =====
        # Create stacked widget for different preview types
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(
            "QStackedWidget {"
            " border: 1px solid #616161;"
            " border-radius: 4px;"
            " background-color: #1f1f1f;"
            "}"
        )
        
        # 1. Image Viewer (for Texture2D)
        self.image_viewer = PhotoViewer(self.stack)
        
        # 2. Text Editor (for TextAsset)
        self.text_editor = QTextEdit(self.stack)
        self.text_editor.setReadOnly(True)
        
        # 3. Placeholder (for Mesh/Unsupported)
        self.placeholder = QLabel("Preview not available")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        
        # Add widgets to stack
        self.image_index = self.stack.addWidget(self.image_viewer)
        self.text_index = self.stack.addWidget(self.text_editor)
        self.placeholder_index = self.stack.addWidget(self.placeholder)
        
        # Initialize with placeholder
        self.stack.setCurrentIndex(self.placeholder_index)
        
        # Add Preview tab
        self.preview_tab_index = self.tab_widget.addTab(self.stack, "Preview")
        
        # ===== Tab 2: Dump (parsed object text) =====
        self.dump_editor = QPlainTextEdit()
        self.dump_editor.setReadOnly(True)
        self.dump_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.dump_editor.setPlaceholderText(
            "Select an asset, then open this tab to load parsed data."
        )
        self.dump_tab_index = self.tab_widget.addTab(self.dump_editor, "Dump")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        layout.addWidget(self.tab_widget)
        
    def show_placeholder(self, message: str = "Select an asset from the list to view its preview."):
        """Show placeholder with message and clear dump editor (for no asset selected)"""
        self._dump_asset = None
        self._show_preview_placeholder(message)
        self.dump_editor.clear()
        
    def _show_preview_placeholder(self, message: str):
        """Show placeholder in Preview tab only (keeps dump editor content)"""
        self.placeholder.setText(message)
        self.stack.setCurrentIndex(self.placeholder_index)

    def _on_tab_changed(self, index: int) -> None:
        if index == self.dump_tab_index:
            self._fill_dump()

    def _fill_dump(self) -> None:
        if self._dump_asset is None:
            self.dump_editor.clear()
            return
        self.dump_editor.setPlainText(self._dump_asset.get_dump_text())
        
    def show_asset_preview(self, asset: AssetInfo):
        """
        Show preview for given asset
        
        Args:
            asset: AssetInfo object to preview
        """
        if not asset:
            self.show_placeholder("No asset selected")
            return

        try:
            self._dump_asset = asset
            preview_result = asset.get_preview()
            if self.tab_widget.currentIndex() == self.dump_tab_index:
                self._fill_dump()
            else:
                self.dump_editor.clear()

            is_previewable = (
                preview_result.status == ResultStatus.COMPLETE
                and preview_result.asset_type in ("Texture2D", "TextAsset")
            )
            if not is_previewable:
                self._show_preview_placeholder("Preview is unavailable.")
                log.info(
                    f"Preview unavailable for {asset.obj_type.name} "
                    f"(Status: {preview_result.status.value}): {preview_result.message}"
                )
                return

            if preview_result.asset_type == "Texture2D":
                # Data is PIL.Image
                if preview_result.data and isinstance(preview_result.data, Image):
                    self.image_viewer.setPhoto(preview_result.data.toqpixmap())
                    self.stack.setCurrentIndex(self.image_index)
                    log.info(f"Showing Texture2D preview: {asset.name}")
                else:
                    self._show_preview_placeholder("Preview is unavailable.")

            elif preview_result.asset_type == "TextAsset":
                # Data is str
                self.text_editor.setPlainText(str(preview_result.data))
                self.stack.setCurrentIndex(self.text_index)
                log.info(f"Showing TextAsset preview: {asset.name}")

        except Exception as e:
            log.error(f"Error generating preview: {e}", exc_info=True)
            self._show_preview_placeholder(f"An unexpected error occurred during preview:\n{str(e)}")
            
    def get_preview_widgets(self) -> set[QWidget]:
        """Get set of widgets that can receive drops"""
        return {
            self.tab_widget,
            self.stack,
            self.image_viewer,
            self.image_viewer.viewport(),
            self.text_editor,
            self.placeholder,
            self.dump_editor,
        }
