from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFont, QPainter

from gui.styles import Colors
from gui.strings import UIStrings
from gui.dialogs.limit_dialog import LimitsDialog


class CustomHeader(QHeaderView):
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.active_cols = set()
        self.setDefaultAlignment(Qt.AlignCenter)
        self.setSectionsClickable(True)
        
    def set_active_cols(self, cols):
        self.active_cols = cols
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        
        # Background
        if logicalIndex == 0:
            painter.fillRect(rect, Colors.BG_DARK)
        elif logicalIndex in self.active_cols:
            painter.fillRect(rect, Colors.BG_ACTIVE_GREEN) # Active Green
        else:
            painter.fillRect(rect, Colors.BG_INACTIVE) # Inactive Gray
            
        # Border
        painter.setPen(Colors.BORDER_DARK)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        
        # Text
        if logicalIndex == 0 or logicalIndex in self.active_cols:
            painter.setPen(Colors.TEXT_WHITE)
        else:
            painter.setPen(Colors.TEXT_MUTED)
            
        text = self.model().headerData(logicalIndex, Qt.Horizontal, Qt.DisplayRole)
        if text:
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, str(text))
            
        painter.restore()


class CalibrationTableMixin:
    """Mixin for managing table headers, rows, limits dialog, and result table updates."""

    @Slot(int)
    def _on_header_left_clicked(self, logical_index):
        if logical_index == 0:
            return
        ch = logical_index
        if ch in self.selected_channels:
            self.selected_channels.remove(ch)
            self.settings.setValue(f"calib_ch_{ch}_en", "false")
        else:
            self.selected_channels.add(ch)
            self.settings.setValue(f"calib_ch_{ch}_en", "true")
            
        self._update_headers()
        
    def _update_headers(self):
        labels = ["Parameter"]
        for i in range(1, 7):
            if i in self.selected_channels:
                labels.append(f"✔ CH{i}")
            else:
                labels.append(f"✖ CH{i}")
                
        self.table_data.setHorizontalHeaderLabels(labels)
        if hasattr(self, 'custom_header'):
            self.custom_header.set_active_cols(self.selected_channels)

    @Slot(int)
    def clear_table_column(self, ch):
        for r in range(self.table_data.rowCount()):
            item = self.table_data.item(r, ch)
            if item:
                item.setText("")
                item.setForeground(Colors.TEXT_ROW)

    @Slot(str, int, str, str)
    def update_or_add_table_row(self, param, ch, value, status):
        if not hasattr(self, 'param_statuses'):
            self.param_statuses = {}
            
        if param not in self.param_statuses:
            self.param_statuses[param] = {}
        self.param_statuses[param][ch] = status
        
        param_order_list = [
            "CC Gain (mOhm)", "Capacity Gain (mOhm)", "CC Offset", "Coulomb Counter Offset Samples", "Shunt Resistor",
            "Cell 1 Gain", "Pack Gain", "Bat Gain",
            "Cell 1 Offset", "Cell 2 Offset", "Cell 3 Offset", "Cell 4 Offset",
            "Cell 5 Offset", "Cell 6 Offset", "Cell 7 Offset", "Cell 8 Offset",
            "Cell 9 Offset", "Cell 10 Offset", "Cell 11 Offset", "Cell 12 Offset",
            "Cell 13 Offset", "Cell 14 Offset", "Cell 15 Offset",
            "Ext Cell Divider Gain",
            "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4", "V_Cell 5", "V_Cell 6",
            "V_Cell 7", "V_Cell 8", "V_Cell 9", "V_Cell 10", "V_Cell 11", "V_Cell 12",
            "V_Cell 13", "V_Cell 14", "V_Cell 15",
            "V_Ext", "V_Aux", "V_Pack", "V_Bat",
            "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp"
        ]

        def get_param_order(p_name):
            p_clean = p_name.split("(")[0].strip().lower()
            for idx, name in enumerate(param_order_list):
                if p_clean == name.lower() or p_clean.startswith(name.lower()):
                    return idx
            return 999

        def get_category(p_name):
            p = p_name.lower()
            if "temp" in p or "ts" in p: return 1
            if "cc" in p or "capacity" in p or "current" in p or "shunt" in p: return 2
            if "overall" in p: return 3
            return 0
            
        my_cat = get_category(param)
        my_rank = get_param_order(param)
        
        # Check if "Overall Result" row exists
        overall_row = -1
        for r in range(self.table_data.rowCount()):
            item = self.table_data.item(r, 0)
            if item and item.text() == "Overall Result":
                overall_row = r
                break
                
        # Find if param already exists
        param_row = -1
        for r in range(self.table_data.rowCount()):
            item = self.table_data.item(r, 0)
            if item and item.text() == param:
                param_row = r
                break
                
        if param_row != -1:
            item_val = self.table_data.item(param_row, ch)
            if not item_val:
                item_val = QTableWidgetItem()
                item_val.setTextAlignment(Qt.AlignCenter)
                self.table_data.setItem(param_row, ch, item_val)
                
            item_val.setText(value)
            if status == "FAIL":
                item_val.setForeground(Colors.FAIL)
            elif status == "PASS":
                item_val.setForeground(Colors.SUCCESS)
            else:
                item_val.setForeground(Colors.TEXT_ROW)
        else:
            # Find insertion position based on strict param order
            insert_pos = self.table_data.rowCount()
            for r in range(self.table_data.rowCount()):
                r_item = self.table_data.item(r, 0)
                if r_item:
                    if get_param_order(r_item.text()) > my_rank:
                        insert_pos = r
                        break
                        
            if overall_row != -1 and insert_pos <= overall_row:
                overall_row += 1 # it shifts down
                
            self.table_data.insertRow(insert_pos)
            
            item_param = QTableWidgetItem(param)
            item_param.setTextAlignment(Qt.AlignCenter)
            self.table_data.setItem(insert_pos, 0, item_param)
            
            item_val = QTableWidgetItem(value)
            item_val.setTextAlignment(Qt.AlignCenter)
            if status == "FAIL":
                item_val.setForeground(QColor("#FF4444"))
            elif status == "PASS":
                item_val.setForeground(QColor("#00FF00"))
                
            self.table_data.setItem(insert_pos, ch, item_val)
            param_row = insert_pos
            
        # Apply background color to entire row based on category
        bg_colors = {
            0: QColor("#232a35"), # Subtle blue for Voltage
            1: QColor("#352335"), # Subtle purple for Temp
            2: QColor("#353223"), # Subtle yellow/orange for Current
            3: QColor("#2b2b2b")  # Default dark for Overall
        }
        bg = bg_colors.get(my_cat, QColor("#2b2b2b"))
        for c in range(7):
            it = self.table_data.item(param_row, c)
            if not it:
                it = QTableWidgetItem("")
                self.table_data.setItem(param_row, c, it)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(bg)
            
        # Update Overall Result in the fixed bottom table
        for active_ch in range(1, 7):
            ch_status = "PASS"
            has_data = False
            for p, ch_dict in self.param_statuses.items():
                if active_ch in ch_dict:
                    has_data = True
                    if ch_dict[active_ch] == "FAIL":
                        ch_status = "FAIL"
                        break
                        
            if has_data:
                item_overall = self.table_overall.item(0, active_ch)
                if not item_overall:
                    item_overall = QTableWidgetItem()
                    item_overall.setTextAlignment(Qt.AlignCenter)
                    font = QFont()
                    font.setPointSize(14)
                    font.setBold(True)
                    item_overall.setFont(font)
                    self.table_overall.setItem(0, active_ch, item_overall)
                    
                item_overall.setText(ch_status)
                if ch_status == "PASS":
                    item_overall.setForeground(QColor("#00FF00"))
                else:
                    item_overall.setForeground(QColor("#FF4444"))

    def on_open_limits(self):
        ic = self.combo_ic.currentText()
        targets = {}
        # Try to gather current target values to pass as defaults
        for key, line_edit in self.dynamic_inputs.items():
            val = line_edit.text().strip()
            if val:
                try:
                    safe_key = "".join(e for e in key if e.isalnum()).lower()
                    targets[safe_key] = float(val) if '.' in val else int(val)
                except ValueError:
                    pass
                    
        dialog = LimitsDialog(ic, targets, self, settings=self.settings)
        dialog.exec()
