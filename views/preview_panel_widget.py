"""
Preview Panel Widget - View component for displaying asset previews
"""

import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QStackedWidget, QTextEdit, QLabel
)
from PIL.Image import Image

from photoviewer import PhotoViewer
from models import AssetInfo, ResultStatus


log = logging.getLogger("ModMaker")


class PreviewPanelWidget(QWidget):
    """
    Widget for displaying asset previews
    Supports Image, Text, and Placeholder views
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
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
        self.text_editor.setStyleSheet(
            "QTextEdit { "
            "font-family: 'Consolas', 'Monospace'; "
            "font-size: 10pt; "
            "font-weight: normal; "
            "}"
        )
        
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
        
        layout.addWidget(self.stack)
        
    def show_placeholder(self, message: str = "Select an asset from the list to view its preview."):
        """Show placeholder with message"""
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
            
            if preview_result.status != ResultStatus.COMPLETE:
                self.show_placeholder(
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
                    self.show_placeholder("Texture2D data is empty.")

            elif preview_result.asset_type == "TextAsset":
                # Data is str
                self.text_editor.setText(str(preview_result.data))
                self.stack.setCurrentIndex(self.text_index)
                log.info(f"Showing TextAsset preview: {asset.name}")

            elif preview_result.asset_type == "Mesh":
                # Data is str (exported OBJ data)
                text_data = preview_result.data if preview_result.data else "No Mesh data available."
                self.show_placeholder(
                    f"Mesh preview (Unsupported):\n"
                    f"Raw OBJ data snippet:\n{str(text_data)[:500]}..."
                )
                log.warning(f"Mesh preview unsupported: {asset.name}")

            else:
                self.show_placeholder(
                    f"Preview not supported for type: {preview_result.asset_type}"
                )

        except Exception as e:
            log.error(f"Error generating preview: {e}", exc_info=True)
            self.show_placeholder(f"An unexpected error occurred during preview:\n{str(e)}")
            
    def get_preview_widgets(self) -> set:
        """Get set of widgets that can receive drops"""
        return {
            self.stack,
            self.image_viewer,
            self.image_viewer.viewport(),
            self.text_editor,
            self.placeholder,
        }

