import os
import csv
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QPushButton, QLabel, QLineEdit, QTableWidget, 
    QTableWidgetItem, QFileDialog, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt

from gui.styles import Colors
from gui.strings import UIStrings


class CsvTab(QWidget):
    """CSV Log File Viewer and Data Exporter Tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_csv_path = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Control Panel
        group_control = QGroupBox(UIStrings.get("GRP_CSV_VIEWER"))
        layout_control = QVBoxLayout(group_control)

        top_bar = QHBoxLayout()
        self.btn_open = QPushButton(UIStrings.get("BTN_OPEN_CSV"))
        self.btn_open.clicked.connect(self._open_csv_dialog)
        top_bar.addWidget(self.btn_open)

        self.lbl_file_info = QLabel("No file loaded.")
        self.lbl_file_info.setStyleSheet(f"color: {Colors.HEX_TEXT_MUTED}; font-style: italic;")
        top_bar.addWidget(self.lbl_file_info, stretch=1)
        layout_control.addLayout(top_bar)

        # Search / Filter Bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel(UIStrings.get("LBL_SEARCH")))
        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText(UIStrings.get("PH_CSV_SEARCH"))
        self.input_search.textChanged.connect(self._filter_table)
        search_layout.addWidget(self.input_search)

        self.btn_export = QPushButton(UIStrings.get("BTN_EXPORT_LOG"))
        self.btn_export.clicked.connect(self._export_filtered_csv)
        search_layout.addWidget(self.btn_export)
        layout_control.addLayout(search_layout)

        layout.addWidget(group_control)

        # Table Display
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
        layout.addWidget(self.table, stretch=1)

    def load_csv_file(self, file_path: str):
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Error", f"File not found: {file_path}")
            return

        try:
            with open(file_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                data = list(reader)

            if not data:
                QMessageBox.information(self, "Info", "The selected CSV file is empty.")
                return

            self.current_csv_path = file_path
            self.lbl_file_info.setText(f"File: {os.path.basename(file_path)} ({len(data)} rows)")

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
                if self.table.columnWidth(col) > 160:
                    self.table.setColumnWidth(col, 160)
            self.table.resizeRowsToContents()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read CSV file:\n{e}")

    def _open_csv_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Log CSV", "", "CSV Files (*.csv);;All Files (*)")
        if file_path:
            self.load_csv_file(file_path)

    def _filter_table(self, text: str):
        search_text = text.lower()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    def _export_filtered_csv(self):
        if not self.current_csv_path or self.table.rowCount() == 0:
            QMessageBox.warning(self, "Warning", "No active CSV data to export.")
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Export Filtered Log", "filtered_log.csv", "CSV Files (*.csv)")
        if not save_path:
            return

        try:
            with open(save_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for row in range(self.table.rowCount()):
                    if not self.table.isRowHidden(row):
                        row_data = [
                            self.table.item(row, col).text() if self.table.item(row, col) else ""
                            for col in range(self.table.columnCount())
                        ]
                        writer.writerow(row_data)
            QMessageBox.information(self, "Success", f"Filtered log successfully saved to:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export CSV:\n{e}")
