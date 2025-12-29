"""
Preview Panel Widget - View component for displaying asset previews
"""

import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QStackedWidget, QTextEdit, QLabel, QTabWidget
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
        self.tab_widget.addTab(self.stack, "Preview")
        
        # ===== Tab 2: Dump (parsed_data JSON) =====
        self.dump_editor = QTextEdit()
        self.dump_editor.setReadOnly(True)
        self.dump_editor.setPlaceholderText("Select an asset to view its parsed data.")
        self.tab_widget.addTab(self.dump_editor, "Dump")
        
        layout.addWidget(self.tab_widget)
        
    def show_placeholder(self, message: str = "Select an asset from the list to view its preview."):
        """Show placeholder with message and clear dump editor (for no asset selected)"""
        self._show_preview_placeholder(message)
        self.dump_editor.clear()
        
    def _show_preview_placeholder(self, message: str):
        """Show placeholder in Preview tab only (keeps dump editor content)"""
        self.placeholder.setText(message)
        self.stack.setCurrentIndex(self.placeholder_index)
        
    def show_asset_preview(self, asset: AssetInfo):
        """
        Show preview for given asset
        
        Args:
            asset: AssetInfo object to preview
        """
        if not asset:
            self.show_placeholder("No asset selected")
            return
            
        log.info(f"Preparing preview for: {asset.name} ({asset.obj_type.name})")

        try:
            preview_result = asset.get_preview()
            
            # Always populate dump editor with parsed data
            self.dump_editor.setText(preview_result.parsed_data)
            
            if preview_result.status != ResultStatus.COMPLETE:
                self._show_preview_placeholder(
                    f"Preview failed for {asset.obj_type.name} (Status: {preview_result.status.value}):\n"
                    f"{preview_result.message}"
                )
                return

            if preview_result.asset_type == "Texture2D":
                # Data is PIL.Image
                if preview_result.data and isinstance(preview_result.data, Image):
                    self.image_viewer.setPhoto(preview_result.data.toqpixmap())
                    self.stack.setCurrentIndex(self.image_index)
                    log.info(f"Showing Texture2D preview: {asset.name}")
                else:
                    self._show_preview_placeholder("Texture2D data is empty.")

            elif preview_result.asset_type == "TextAsset":
                # Data is str
                self.text_editor.setText(str(preview_result.data))
                self.stack.setCurrentIndex(self.text_index)
                log.info(f"Showing TextAsset preview: {asset.name}")

            elif preview_result.asset_type == "Mesh":
                # Data is str (exported OBJ data)
                text_data = preview_result.data if preview_result.data else "No Mesh data available."
                self._show_preview_placeholder(
                    f"Mesh preview (Unsupported):\n"
                    f"Raw OBJ data snippet:\n{str(text_data)[:500]}..."
                )
                log.warning(f"Mesh preview unsupported: {asset.name}")

            else:
                self._show_preview_placeholder(
                    f"Preview not supported for type: {preview_result.asset_type}"
                )

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

