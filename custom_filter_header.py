from PySide6.QtWidgets import (
    QHeaderView, QMenu, QWidgetAction, QLineEdit, 
    QCheckBox, QWidget, QVBoxLayout, QLabel
)
from PySide6.QtGui import QIcon, QPainter, QAction, QPen, QColor, QFont, QPixmap
from PySide6.QtCore import QPoint, Qt, Signal, QRect

class FilterHeader(QHeaderView):
    # Signal: col_index, filter_value
    filter_changed = Signal(int, object) 

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.active_filters = {} 
        self._unique_values = {} 
        
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        
        # 2. เพิ่ม Tooltip บอก User ว่าคลิกขวาได้
        self.setToolTip("Right-click to open filter menu")

    def set_filter_boxes(self, col, values):
        """กำหนดให้คอลัมน์นี้ใช้ระบบ Checkbox ตามค่าที่ส่งมา"""
        sorted_values = sorted(list(set(values)))
        self._unique_values[col] = sorted_values
        if col not in self.active_filters:
            self.active_filters[col] = sorted_values

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()
        
        # ตรวจสอบว่าคอลัมน์นี้มีการกรองอยู่หรือไม่
        has_filter = False
        if logicalIndex in self.active_filters:
            val = self.active_filters[logicalIndex]
            if isinstance(val, list): # แบบ Checkbox
                full_options = self._unique_values.get(logicalIndex, [])
                if len(val) < len(full_options):
                    has_filter = True
            elif isinstance(val, tuple): # แบบ Text
                if val[0]: # มีข้อความ
                    has_filter = True

        # 1. ถ้ามี Filter ให้ขีดเส้นใต้สีน้ำเงิน
        if has_filter:
            painter.save()
            
            # ตั้งค่าปากกา (สีน้ำเงิน, หนา 3px)
            pen = QPen(QColor(0, 120, 215)) # สีน้ำเงินแบบ Windows Accent
            pen.setWidth(2)
            painter.setPen(pen)
            
            # คำนวณตำแหน่งเส้น (ขอบล่างสุดของ Header)
            p1 = rect.bottomLeft()
            p2 = rect.bottomRight()
            
            y_pos = p1.y()
            p1.setY(y_pos)
            p2.setY(y_pos)
            
            painter.drawLine(p1, p2)
            painter.restore()
            
        # Override text drawing to ensure left alignment
        # Note: super().paintSection draws the background and sort indicator, 
        # but it also draws text. To force left alignment without completely reimplementing 
        # the style, we might need to rely on setDefaultAlignment in main_ui.py working.
        # However, if we want to be sure, we can redraw the text here.
        # But simply setting setDefaultAlignment usually works for QHeaderView.
        # Let's trust setDefaultAlignment first. If not, we can come back.
        # Wait, the user specifically asked for left alignment and I put it in the plan.
        # Let's add a small fix here just in case:
        # Actually, QHeaderView uses the model's headerData(Qt.TextAlignmentRole) if available,
        # or defaultAlignment.
        # So I don't strictly need to draw text here if I set it in main_ui.py.
        # But let's leave this method clean.

    def contextMenuEvent(self, event):
        col = self.logicalIndexAt(event.pos())
        if col == -1: return
        # --- แก้ไข: คำนวณตำแหน่งมุมซ้ายล่างของ Header Section นั้น ---
        # sectionViewportPosition(col) จะได้ค่า X ของคอลัมน์เทียบกับ Header
        x = self.sectionViewportPosition(col)
        y = self.height() # ความสูงของ Header (คือขอบล่างพอดี)
        
        # แปลงพิกัด Widget (Local) -> พิกัดหน้าจอ (Global)
        global_pos = self.mapToGlobal(QPoint(x, y))
        
        self.show_filter_menu(col, global_pos)

    def show_filter_menu(self, col, pos):
        menu = QMenu(self)
        
        # 3. เพิ่ม Header บอกชื่อคอลัมน์ที่กำลังกรอง
        col_name = self.model().headerData(col, Qt.Orientation.Horizontal)
        
        # สร้าง Label สวยๆ
        header_label = QLabel(f"Filter: {col_name}")
        header_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                color: #444;
                padding: 2px 5px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
            }
        """)
        header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # ใส่ Label ลงใน Menu
        header_action = QWidgetAction(menu)
        header_action.setDefaultWidget(header_label)
        menu.addAction(header_action)
        
        # --- Logic เดิม: สร้างเมนูตามประเภท ---
        if col in self._unique_values:
            # ... (Checkbox Logic) ...
            unique_vals = self._unique_values[col]
            current_filter = self.active_filters.get(col, unique_vals)
            if not isinstance(current_filter, list): current_filter = unique_vals
            
            checkbox_widgets: list[QCheckBox] = []
            
            select_all_checkbox = QCheckBox("Select All")
            all_selected = len(current_filter) == len(unique_vals)
            select_all_checkbox.setChecked(all_selected)
            select_all_action = QWidgetAction(menu)
            select_all_action.setDefaultWidget(select_all_checkbox)
            
            def toggle_all(checked):
                for widget in checkbox_widgets:
                    widget.blockSignals(True)
                    widget.setChecked(False)
                    widget.blockSignals(False)
                new_val = unique_vals if checked else []
                self._apply_filter(col, new_val)
                
            select_all_checkbox.toggled.connect(toggle_all)
            menu.addAction(select_all_action)
            menu.addSeparator()
            
            for val in unique_vals:
                checkbox = QCheckBox(str(val))
                checkbox.setChecked(val in current_filter and not all_selected)
                
                def on_toggled(checked, v=val, widgets_ref=checkbox_widgets):
                    if select_all_checkbox.isChecked():
                        select_all_checkbox.blockSignals(True)
                        select_all_checkbox.setChecked(False)
                        select_all_checkbox.blockSignals(False)
                    current_selected = [cb.text() for cb in widgets_ref if cb.isChecked()]
                    self._apply_filter(col, current_selected)
                    is_all = len(current_selected) == len(unique_vals)
                    select_all_checkbox.blockSignals(True)
                    select_all_checkbox.setChecked(is_all)
                    if is_all:
                        for cb in widgets_ref:
                            cb.blockSignals(True)
                            cb.setChecked(False)
                            cb.blockSignals(False)
                    select_all_checkbox.blockSignals(False)

                checkbox.toggled.connect(on_toggled)
                checkbox_action = QWidgetAction(menu)
                checkbox_action.setDefaultWidget(checkbox)
                menu.addAction(checkbox_action)
                checkbox_widgets.append(checkbox)
                
        else:
            # ... (Text Search Logic) ...
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(8, 8, 8, 8)
            
            search_input = QLineEdit()
            search_input.setPlaceholderText("Type to filter...")
            match_case_cb = QCheckBox("Match Case")

            # --- เพิ่มปุ่ม X สีแดง ---
            # 1. วาดรูป X สีแดงลงใน Pixmap
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(Qt.GlobalColor.red, 2)) # สีแดง หนา 2px
            painter.drawLine(4, 4, 12, 12) # เส้นเฉียง 1
            painter.drawLine(12, 4, 4, 12) # เส้นเฉียง 2
            painter.end()
            
            # 2. ใส่ Action เข้าไปใน QLineEdit (ด้านขวา)
            clear_action = search_input.addAction(QIcon(pixmap), QLineEdit.ActionPosition.TrailingPosition)
            clear_action.triggered.connect(search_input.clear)
            
            # 3. ซ่อนปุ่มถ้าไม่มีข้อความ (Optional: เพื่อความสวยงาม)
            clear_action.setVisible(False) # เริ่มต้นซ่อนไว้ก่อน
            search_input.textChanged.connect(lambda text: clear_action.setVisible(bool(text)))
            # -----------------------

            current_text, current_case = self.active_filters.get(col, ("", False))
            search_input.setText(current_text)
            match_case_cb.setChecked(current_case)
            
            layout.addWidget(search_input)
            layout.addWidget(match_case_cb)
            
            action = QWidgetAction(menu)
            action.setDefaultWidget(widget)
            menu.addAction(action)
            
            def update_text_filter():
                self._apply_filter(col, (search_input.text(), match_case_cb.isChecked()))

            search_input.textChanged.connect(update_text_filter)
            match_case_cb.toggled.connect(update_text_filter)
            search_input.setFocus()

        menu.exec(pos)

    def _apply_filter(self, col, value):
        self.active_filters[col] = value
        self.filter_changed.emit(col, value)
        self.viewport().update()