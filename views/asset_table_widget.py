"""
Asset Table Widget - View component for displaying asset list
"""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.asset_model import EMPTY_CELL_TEXT, AssetInfo, format_byte_size
from views.components.custom_filter_header import FilterHeader

_CHANGED_FOREGROUND = QColor("#7DCEA0")
_PLACEHOLDER_FOREGROUND = QColor("#808080")
MAX_COLUMN_WIDTH = 360
_CELL_TEXT_PADDING = 16
_HEADERS = ["Name", "Type", "PathID", "Container", "Size", "SourceFile"]
_COL_NAME = 0
_COL_TYPE = 1
_COL_PATH_ID = 2
_COL_CONTAINER = 3
_COL_SIZE = 4
_COL_SOURCE = 5


class _ByteSizeItem(QTableWidgetItem):
    def __init__(self, byte_size: int) -> None:
        super().__init__(format_byte_size(byte_size))
        self.byte_size = byte_size
        self.setToolTip(str(byte_size))

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _ByteSizeItem):
            return self.byte_size < other.byte_size
        return super().__lt__(other)


def _display_or_none(value: str) -> str:
    return EMPTY_CELL_TEXT if value == "" else value


def _source_filename(source_path: str) -> str:
    return Path(source_path).name


class AssetTableWidget(QWidget):
    """
    Widget for displaying asset list in a table with filtering
    Encapsulates QTableWidget with FilterHeader
    """
    # Signals
    selection_changed = Signal(list)  # List of selected AssetInfo objects
    filter_changed = Signal()
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._auto_fit_timer = QTimer(self)
        self._auto_fit_timer.setSingleShot(True)
        self._auto_fit_timer.timeout.connect(self._auto_fit_columns)
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        
        # Replace default header with FilterHeader
        self.header = FilterHeader(self.table)
        self.header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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
        self.table.horizontalScrollBar().setSingleStep(20)
        row_height = self.table.fontMetrics().height() + 8
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setResizeContentsPrecision(0)
        # self.table.setStyleSheet("QTableWidget::item { padding-top: 5px; padding-bottom: 5px; }")
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        
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
        assets: list[AssetInfo] = []
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
        
    def clear_table(self):
        """Clear table"""
        self.table.setRowCount(0)
        self.table.clearSelection()
        self.table.viewport().update()
        
    def load_assets(self, assets: list[AssetInfo], *, auto_fit: bool = False):
        """
        Load assets into table
        
        Args:
            assets: List of AssetInfo objects to display
            auto_fit: When True, size columns to the first visible page
                after layout (capped). Use only on the first load after
                opening files, not on filter rebuilds.
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
            name_item.setToolTip(asset.name or "")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, asset)
            self.table.setItem(row, _COL_NAME, name_item)

            type_item = QTableWidgetItem(asset.obj_type.name)
            type_item.setToolTip(asset.obj_type.name)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, _COL_TYPE, type_item)

            path_id_item = QTableWidgetItem(asset.path_id)
            path_id_item.setToolTip(asset.path_id)
            path_id_item.setFlags(path_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, _COL_PATH_ID, path_id_item)

            container_text = _display_or_none(asset.container)
            container_item = QTableWidgetItem(container_text)
            container_item.setToolTip(asset.container)
            container_item.setFlags(container_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, _COL_CONTAINER, container_item)

            size_item = _ByteSizeItem(int(getattr(asset, "byte_size", 0) or 0))
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, _COL_SIZE, size_item)

            source_name = _source_filename(asset.source_path)
            source_item = QTableWidgetItem(_display_or_none(source_name))
            source_item.setToolTip(asset.source_path)
            source_item.setData(Qt.ItemDataRole.UserRole, asset.source_path)
            source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, _COL_SOURCE, source_item)
            self._apply_changed_style(row, asset)

        self.header.set_filter_boxes(1, list(all_types))
        self.header.set_filter_boxes(5, list(all_sources))
        
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.setSortingEnabled(True)
        if auto_fit:
            self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
            self._auto_fit_timer.start(0)
        else:
            self._auto_fit_timer.stop()

    def _visible_row_indexes(self) -> list[int]:
        row_count = self.table.rowCount()
        if row_count <= 0:
            return []
        default_h = max(self.table.verticalHeader().defaultSectionSize(), 1)
        heights = [
            height for height in (
                self.table.viewport().height(),
                self.height() - self.table.horizontalHeader().height(),
            )
            if height > 0
        ]
        viewport_height = min(heights) if heights else default_h
        page = max(viewport_height // default_h, 1) + 1
        top = self.table.indexAt(QPoint(0, 0)).row()
        bottom = self.table.indexAt(QPoint(0, max(viewport_height - 1, 0))).row()
        if top < 0:
            top = 0
        if bottom < 0:
            bottom = min(row_count - 1, top + page - 1)
        bottom = min(bottom, top + page - 1, row_count - 1)
        return [
            row for row in range(top, bottom + 1)
            if not self.table.isRowHidden(row)
        ]

    def _cell_text_width(self, row: int, column: int) -> int:
        item = self.table.item(row, column)
        if item is None:
            return 0
        return self.table.fontMetrics().horizontalAdvance(item.text())

    def _auto_fit_columns(self) -> None:
        header = self.table.horizontalHeader()
        visible_rows = self._visible_row_indexes()
        for column in range(self.table.columnCount()):
            width = header.sectionSizeHint(column)
            for row in visible_rows:
                width = max(width, self._cell_text_width(row, column) + _CELL_TEXT_PADDING)
            width = min(max(width, header.minimumSectionSize()), MAX_COLUMN_WIDTH)
            self.table.setColumnWidth(column, width)
        
    def _cell_is_placeholder(self, asset: AssetInfo, column: int) -> bool:
        if column == _COL_NAME:
            return asset.name == ""
        if column == _COL_CONTAINER:
            return asset.container == ""
        if column == _COL_SOURCE:
            return _source_filename(asset.source_path) == ""
        if column == _COL_TYPE:
            return asset.obj_type.name == ""
        if column == _COL_PATH_ID:
            return asset.path_id == ""
        return False

    def _apply_changed_style(self, row: int, asset: AssetInfo):
        """Apply visual indicator for changed assets"""
        name_item = self.table.item(row, _COL_NAME)
        if not name_item:
            return
        is_changed = bool(getattr(asset, "is_changed", False))
        if asset.name == "":
            name_item.setText(
                f"{EMPTY_CELL_TEXT} *" if is_changed else EMPTY_CELL_TEXT
            )
        else:
            suffix = " *" if is_changed else "   "
            name_item.setText(f"{asset.name}{suffix}")
        green = QBrush(_CHANGED_FOREGROUND) if is_changed else None
        dim = QBrush(_PLACEHOLDER_FOREGROUND)
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if not item:
                continue
            if self._cell_is_placeholder(asset, col):
                item.setForeground(dim)
            elif green is None:
                item.setData(Qt.ItemDataRole.ForegroundRole, None)
            else:
                item.setForeground(green)
        
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
                    if item_data is None:
                        check_val = (
                            "" if cell_text == EMPTY_CELL_TEXT else cell_text
                        )
                    else:
                        check_val = item_data
                        
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

