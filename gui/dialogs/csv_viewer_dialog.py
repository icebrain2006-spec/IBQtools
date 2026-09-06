import csv
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QTableWidget, QTableWidgetItem, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt
from gui.styles import Colors


class CsvViewerDialog(QDialog):
    """Dialog for viewing and searching CSV log files."""

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"CSV Viewer - {os.path.basename(file_path)}")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Search Bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to filter logs by date, SN, result, etc...")
        self.search_input.textChanged.connect(self._filter_table)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Table Widget
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Colors.HEX_BG_DARK};
                color: {Colors.TEXT_ROW.name()};
                gridline-color: {Colors.HEX_BORDER_LIGHT};
            }}
            QHeaderView::section {{
                background-color: {Colors.HEX_BG_PANEL};
                color: {Colors.HEX_WHITE};
                padding: 4px;
                border: 1px solid {Colors.HEX_BORDER_LIGHT};
            }}
        """)
        layout.addWidget(self.table)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)
        
        self._load_csv(file_path)
        
    def _load_csv(self, file_path):
        try:
            with open(file_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                data = list(reader)
                
            if not data:
                return
                
            self.table.setRowCount(len(data))
            self.table.setColumnCount(max(len(row) for row in data))
            
            for row_idx, row_data in enumerate(data):
                for col_idx, col_data in enumerate(row_data):
                    if " - " in col_data:
                        col_data = col_data.replace(" - ", "\n~\n")
                        
                    item = QTableWidgetItem(col_data)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row_idx, col_idx, item)
            
            self.table.resizeColumnsToContents()
            for col in range(self.table.columnCount()):
                if self.table.columnWidth(col) > 150:
                    self.table.setColumnWidth(col, 150)
            self.table.resizeRowsToContents()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load CSV: {e}")
            
    def _filter_table(self, text):
        search_text = text.lower()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)
