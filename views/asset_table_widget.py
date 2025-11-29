"""
Asset Table Widget - View component for displaying asset list
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
)

from custom_filter_header import FilterHeader
from models import AssetInfo


class AssetTableWidget(QWidget):
    """
    Widget for displaying asset list in a table with filtering
    Encapsulates QTableWidget with FilterHeader
    """
    # Signals
    selection_changed = Signal(list)  # List of selected AssetInfo objects
    filter_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "PathID", "Container", "SourceFile"])
        
        # Replace default header with FilterHeader
        self.header = FilterHeader(self.table)
        self.header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.header.setFixedHeight(24)
        self.header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setHorizontalHeader(self.header)
        self.table.verticalHeader().setVisible(False)
        
        # Configure table behavior
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.verticalScrollBar().setSingleStep(10)
        self.table.horizontalScrollBar().setSingleStep(10)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet("QTableWidget::item { padding-top: 5px; padding-bottom: 5px; }")
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        
        layout.addWidget(self.table)
        
    def _connect_signals(self):
        """Connect internal signals"""
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.header.filter_changed.connect(self._on_filter_changed)
        
    def _on_selection_changed(self):
        """Handle selection changes"""
        selected_assets = self.get_selected_assets()
        self.selection_changed.emit(selected_assets)
        
    def _on_filter_changed(self):
        """Handle filter changes"""
        self.filter_changed.emit()
        
    def get_selected_assets(self) -> list[AssetInfo]:
        """Get list of currently selected assets"""
        selected_rows = self.table.selectionModel().selectedRows()
        assets = []
        for index in selected_rows:
            item = self.table.item(index.row(), 0)
            asset = item.data(Qt.ItemDataRole.UserRole) if item else None
            if asset and isinstance(asset, AssetInfo):
                assets.append(asset)
        return assets
        
    def clear_selection(self):
        """Clear table selection"""
        self.table.clearSelection()
        
    def set_sorting_enabled(self, enabled: bool):
        """Enable or disable sorting"""
        self.table.setSortingEnabled(enabled)
        
    def load_assets(self, assets: list[AssetInfo]):
        """
        Load assets into table
        
        Args:
            assets: List of AssetInfo objects to display
        """
        # Prepare for loading
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(assets))
        self.table.clearSelection()
        
        all_types = set()
        all_sources = set()
        
        for row, asset in enumerate(assets):
            all_types.add(asset.obj_type.name)
            all_sources.add(asset.source_path)
            
            # Name (Column 0) - Store AssetInfo in UserRole
            name_item = QTableWidgetItem()
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, asset)
            self.table.setItem(row, 0, name_item)
            self._apply_changed_style(row, asset)
            
            # Type (Column 1)
            type_item = QTableWidgetItem(asset.obj_type.name)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, type_item)
            
            # PathID (Column 2)
            path_id_item = QTableWidgetItem(asset.path_id)
            path_id_item.setFlags(path_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, path_id_item)
            
            # Container (Column 3)
            container_item = QTableWidgetItem(asset.container)
            container_item.setFlags(container_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, container_item)
            
            # SourceFile (Column 4)
            from pathlib import Path
            source_item = QTableWidgetItem(str(Path(asset.source_path).name))
            source_item.setToolTip(asset.source_path)
            source_item.setData(Qt.ItemDataRole.UserRole, asset.source_path)
            source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 4, source_item)
        
        # Setup filter boxes for Type and SourceFile columns
        self.header.set_filter_boxes(1, list(all_types))
        self.header.set_filter_boxes(4, list(all_sources))
        
        # Adjust column widths
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        
    def _apply_changed_style(self, row: int, asset: AssetInfo):
        """Apply visual indicator for changed assets"""
        item = self.table.item(row, 0)
        if not item:
            return
        suffix = " *" if bool(getattr(asset, "is_changed", False)) else "   "
        base_name = asset.name or ""
        item.setText(f"{base_name}{suffix}")
        
    def refresh_asset_display(self, asset: AssetInfo):
        """Refresh display for a specific asset"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) is asset:
                self._apply_changed_style(row, asset)
                break
                
    def apply_filter(self, clear: bool = False):
        """
        Apply current filters to table rows
        
        Args:
            clear: If True, clear all filters first
        """
        if clear:
            self.header.active_filters.clear()
            self.header.viewport().update()
        
        active_filters = self.header.active_filters
        
        for row in range(self.table.rowCount()):
            should_show = True
            
            for col, val in active_filters.items():
                item = self.table.item(row, col)
                if not item:
                    should_show = False
                    break
                
                cell_text = item.text()

                # Check filter type
                if isinstance(val, list):
                    # Checkbox filter
                    if not val:
                        should_show = False
                        break
                    
                    item_data = item.data(Qt.ItemDataRole.UserRole)
                    check_val = item_data if item_data is not None else cell_text
                        
                    if check_val not in val:
                        should_show = False
                        break
                        
                elif isinstance(val, tuple):
                    # Text search filter
                    filter_text, use_match_case = val
                    
                    if not filter_text:
                        continue
                    
                    if use_match_case:
                        if filter_text not in cell_text:
                            should_show = False
                            break
                    else:
                        if filter_text.lower() not in cell_text.lower():
                            should_show = False
                            break
                            
            self.table.setRowHidden(row, not should_show)

