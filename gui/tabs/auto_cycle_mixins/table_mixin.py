"""Table and Status Bit Matrix Mixin for Auto Cycle tab."""

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from gui.styles import Colors
from gui.tabs.auto_cycle_mixins.constants import STATUS_REGISTERS, REGISTER_BIT_NAMES


class TableMixin:
    """Manages the 14-Register x 8-Bit Status Grid Matrix."""

    def _init_status_table(self):
        """Builds the 14-row by 8-col table for bit status monitoring."""
        self.table_bits = QTableWidget(len(STATUS_REGISTERS), 8)
        self.table_bits.setVerticalHeaderLabels(STATUS_REGISTERS)
        self.table_bits.setHorizontalHeaderLabels([f"Bit {7-i}" for i in range(8)])
        
        # Table styles and sizing
        self.table_bits.setStyleSheet("""
            QTableWidget {
                background-color: #1a1a1a;
                gridline-color: #2e2e2e;
                color: #e0e0e0;
                font-size: 11px;
                border: 1px solid #333333;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #252525;
                color: #aaaaaa;
                padding: 3px;
                font-weight: bold;
                border: 1px solid #333333;
                font-size: 10px;
            }
        """)
        
        self.table_bits.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_bits.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_bits.verticalHeader().setDefaultSectionSize(22)
        
        # Populate cells with bit names
        for row_idx, bits in enumerate(REGISTER_BIT_NAMES):
            for col_idx, bit_name in enumerate(bits):
                item = QTableWidgetItem(bit_name)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled)  # Read-only
                
                # Default styling
                if "RSVD" in bit_name:
                    item.setBackground(Colors.BIT_RSVD)
                    item.setForeground(QColor("#888888"))
                else:
                    item.setBackground(Colors.BIT_LOW)
                    item.setForeground(Colors.TEXT_WHITE)
                    
                self.table_bits.setItem(row_idx, col_idx, item)

    def update_status_bits(self, telemetry: dict):
        """Updates color of each bit cell based on telemetry."""
        for row_idx, reg_name in enumerate(STATUS_REGISTERS):
            val = telemetry.get(reg_name, 0)
            if isinstance(val, str) and val.startswith("0x"):
                val = int(val, 16)
            elif not isinstance(val, int):
                val = int(val) if val else 0
                
            bits_list = REGISTER_BIT_NAMES[row_idx]
            for col_idx in range(8):
                bit_pos = 7 - col_idx
                bit_val = (val >> bit_pos) & 0x01
                bit_name = bits_list[col_idx]
                
                item = self.table_bits.item(row_idx, col_idx)
                if not item:
                    continue
                    
                if "RSVD" in bit_name:
                    item.setBackground(Colors.BIT_RSVD)
                    item.setForeground(QColor("#888888"))
                else:
                    if bit_val == 1:
                        item.setBackground(Colors.BIT_HIGH)
                        item.setForeground(Colors.TEXT_WHITE)
                    else:
                        item.setBackground(Colors.BIT_LOW)
                        item.setForeground(Colors.TEXT_WHITE)
