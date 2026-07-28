import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QTextEdit, QSplitter, QGridLayout,
    QHeaderView
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
import os
import sys
import serial.tools.list_ports

# Ensure calibrators is in path if needed, but we can import directly
from calibrators.calib_runner import CalibrationThread

class CalibrationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.refresh_ports()
        
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- Top: Port & Channel Selection ---
        top_layout = QHBoxLayout()
        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(120)
        
        self.btn_refresh_ports = QPushButton("Refresh")
        self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        
        self.combo_ic = QComboBox()
        self.combo_ic.addItems(["BQ40Z50", "BQ78350 (Coming Soon)"])
        
        self.combo_ch = QComboBox()
        self.combo_ch.addItems([f"CH {i}" for i in range(1, 7)])
        
        top_layout.addWidget(QLabel("Port:"))
        top_layout.addWidget(self.combo_port)
        top_layout.addWidget(self.btn_refresh_ports)
        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel("Target IC:"))
        top_layout.addWidget(self.combo_ic)
        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel("Channel:"))
        top_layout.addWidget(self.combo_ch)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)
        
        # --- Splitter for Left/Right Panels ---
        splitter = QSplitter(Qt.Horizontal)
        
        # --- Left Panel: Controls ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Voltage & Temp Group
        group_vt = QGroupBox("Voltage & Temperature Calibration (Sequence A)")
        grid_vt = QGridLayout()
        
        self.inputs_vt = {}
        vt_labels = [
            ("Cell 1 (mV)", "3200"), ("Cell 2 (mV)", "3200"), 
            ("Cell 3 (mV)", "3200"), ("Cell 4 (mV)", "3200"),
            ("PACK (mV)", "12780"), ("BAT (mV)", "12780"),
            ("Int Temp (°C)", "25.0"), ("TS1 Temp (°C)", "25.0"),
            ("TS2 Temp (°C)", "25.0"), ("TS3 Temp (°C)", "25.0"),
            ("TS4 Temp (°C)", "25.0")
        ]
        
        for i, (label_text, default_val) in enumerate(vt_labels):
            row = i // 2
            col = (i % 2) * 2
            grid_vt.addWidget(QLabel(label_text), row, col)
            line_edit = QLineEdit(default_val)
            self.inputs_vt[label_text] = line_edit
            grid_vt.addWidget(line_edit, row, col + 1)
            
        self.btn_cal_vt = QPushButton("Start Voltage & Temp Calibration")
        self.btn_cal_vt.setMinimumHeight(40)
        self.btn_cal_vt.setStyleSheet("font-weight: bold; background-color: #2E8B57; color: white;")
        self.btn_cal_vt.clicked.connect(self.on_start_vt_calib)
        
        layout_vt = QVBoxLayout()
        layout_vt.addLayout(grid_vt)
        layout_vt.addWidget(self.btn_cal_vt)
        group_vt.setLayout(layout_vt)
        left_layout.addWidget(group_vt)
        
        # 2. Current Group
        group_current = QGroupBox("Current Calibration (Sequence B)")
        grid_c = QGridLayout()
        
        self.inputs_c = {}
        grid_c.addWidget(QLabel("Discharge Current (mA)"), 0, 0)
        self.inputs_c["Current (mA)"] = QLineEdit("-1000")
        grid_c.addWidget(self.inputs_c["Current (mA)"], 0, 1)
        
        self.btn_cal_c = QPushButton("Start Current Calibration (Auto Relay ON)")
        self.btn_cal_c.setMinimumHeight(40)
        self.btn_cal_c.setStyleSheet("font-weight: bold; background-color: #B22222; color: white;")
        
        layout_c = QVBoxLayout()
        layout_c.addLayout(grid_c)
        
        warning_lbl = QLabel("⚠️ Warning: This will turn on the load relay automatically.")
        warning_lbl.setStyleSheet("color: #FF8C00;")
        layout_c.addWidget(warning_lbl)
        
        layout_c.addWidget(self.btn_cal_c)
        group_current.setLayout(layout_c)
        left_layout.addWidget(group_current)
        
        left_layout.addStretch()
        
        # --- Right Panel: Realtime & Logs ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Table
        self.table_data = QTableWidget(0, 4)
        self.table_data.setHorizontalHeaderLabels(["Parameter", "Raw ADC", "Measured", "Status"])
        self.table_data.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.table_data, stretch=2)
        
        # Logs
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #1E1E1E; color: #00FF00; font-family: Consolas;")
        right_layout.addWidget(self.log_console, stretch=1)
        
        # Add to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 600]) # Initial sizes
        
        main_layout.addWidget(splitter)
        
    def log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.log_console.append(f"[{timestamp}] {msg}")
        
    def add_table_row(self, param, raw, measured, status):
        row = self.table_data.rowCount()
        self.table_data.insertRow(row)
        
        self.table_data.setItem(row, 0, QTableWidgetItem(param))
        self.table_data.setItem(row, 1, QTableWidgetItem(str(raw)))
        self.table_data.setItem(row, 2, QTableWidgetItem(str(measured)))
        
        item_status = QTableWidgetItem(status)
        if status == "PASS":
            item_status.setForeground(QColor("green"))
        elif status == "FAIL":
            item_status.setForeground(QColor("red"))
            
        self.table_data.setItem(row, 3, item_status)

    @Slot()
    def on_start_vt_calib(self):
        port = self.combo_port.currentText()
        if not port or "Select" in port:
            self.log("Error: Please select a valid COM port.")
            return
            
        ch_text = self.combo_ch.currentText()
        ch = int(ch_text.split()[-1]) # e.g. "CH 6" -> 6
        
        ic = self.combo_ic.currentText()
        if "BQ40Z50" not in ic:
            self.log("Error: Only BQ40Z50 is currently supported.")
            return
            
        # Parse targets
        try:
            targets = {
                'cell1': int(self.inputs_vt["Cell 1 (mV)"].text()),
                'pack': int(self.inputs_vt["PACK (mV)"].text()),
                'batt': int(self.inputs_vt["BAT (mV)"].text())
            }
        except ValueError:
            self.log("Error: Invalid numeric value in target fields.")
            return
            
        # Construct path to the calib script
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "calibrators", "scripts", "bq40z50_voltage.calib")
        if not os.path.exists(script_path):
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "calibrators", "scripts", "bq40z50_voltage.calib")
            
        self.btn_cal_vt.setEnabled(False)
        self.log(f"Starting calibration on {port}, {ch_text}...")
        self.table_data.setRowCount(0)
        
        self.cal_thread = CalibrationThread(port, ch, script_path, targets)
        self.cal_thread.log_signal.connect(self.log)
        self.cal_thread.row_signal.connect(self.add_table_row)
        self.cal_thread.finished_signal.connect(self.on_calib_finished)
        self.cal_thread.start()

    @Slot(bool)
    def on_calib_finished(self, success):
        self.btn_cal_vt.setEnabled(True)
        if success:
            self.log("Calibration finished successfully!")
        else:
            self.log("Calibration failed or was aborted.")

    def refresh_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.combo_port.addItem("Select Port")
        for p in ports:
            self.combo_port.addItem(p.device)


