import time
import os
import sys
import serial.tools.list_ports
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QTextEdit, QSplitter, QGridLayout,
    QHeaderView, QScrollArea
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor

# Ensure calibrators is in path if needed, but we can import directly
from calibrators.calib_runner import CalibrationThread

IC_CONFIGS = {
    "BQ40Z50": {
        "voltage": {
            "Cell 1 (mV)": "3200", "Cell 2 (mV)": "3200", 
            "Cell 3 (mV)": "3200", "Cell 4 (mV)": "3200",
            "PACK (mV)": "12780", "BAT (mV)": "12780"
        },
        "current": {
            "Current (mA)": "-1000"
        },
        "temperature": {
            "Int Temp (°C)": "25.0", "TS1 Temp (°C)": "25.0",
            "TS2 Temp (°C)": "25.0", "TS3 Temp (°C)": "25.0",
            "TS4 Temp (°C)": "25.0"
        },
        "script": "bq40z50_voltage.calib"
    },
    "BQ4050": {
        "voltage": {
            "Cell 1 (mV)": "3200", "BAT (mV)": "12780", "PACK (mV)": "12780"
        },
        "current": {
            "Current (mA)": "-1000"
        },
        "temperature": {
            "Internal (°C)": "25.0", "External 1 (°C)": "25.0",
            "External 2 (°C)": "25.0", "External 3 (°C)": "25.0",
            "External 4 (°C)": "25.0"
        },
        "script": "bq4050_voltage.calib"
    },
    "BQ34Z100": {
        "voltage": {
            "Voltage (mV)": "37888"
        },
        "current": {
            "Current (mA)": "-2000",
            "CC Offset": ""
        },
        "temperature": {
            "Temperature (°C)": "25.0"
        },
        "script": "bq34z100_voltage.calib"
    },
    "BQ78350": {
        "voltage": {
            "Cell 1 (mV)": "3200", "Cell 2 (mV)": "3200", "Cell 3 (mV)": "3200", "Cell 4 (mV)": "3200",
            "Cell 5 (mV)": "3200", "Cell 6 (mV)": "3200", "Cell 7 (mV)": "3200", "Cell 8 (mV)": "3200",
            "Cell 9 (mV)": "3200", "Cell 10 (mV)": "3200", "Cell 11 (mV)": "3200", "Cell 12 (mV)": "3200",
            "Cell 13 (mV)": "3200", "Cell 14 (mV)": "3200", "Cell 15 (mV)": "3200",
            "Ext Average Cell (mV)": "3200", "VAUX (mV)": "3200"
        },
        "current": {
            "Current Gain (mA)": "-2000", "CC Offset": ""
        },
        "temperature": {
            "Sensor 1 (°C)": "25.0", "Sensor 2 (°C)": "25.0", "Sensor 3 (°C)": "25.0", "Internal Sensor (°C)": "25.0"
        },
        "script": "bq78350_voltage.calib"
    },
    "BQ40Z80": {
        "voltage": {
            "Cell 1 (mV)": "3200", "VC6-VSS (mV)": "3200", "Cell-7 Positive (mV)": "3200", "PACK (mV)": "12780"
        },
        "current": {
            "Current (mA)": "-1000"
        },
        "temperature": {
            "Internal (°C)": "25.0", "External 1 (°C)": "25.0",
            "External 2 (°C)": "25.0", "External 3 (°C)": "25.0",
            "External 4 (°C)": "25.0"
        },
        "script": "bq40z80_voltage.calib"
    }
}

class CalibrationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dynamic_inputs = {}
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
        self.combo_ic.addItems(list(IC_CONFIGS.keys()))
        self.combo_ic.currentTextChanged.connect(self._build_dynamic_ui)
        
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
        
        # --- Left Panel: Scrollable Dynamic Controls ---
        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)
        self.left_layout.setContentsMargins(10, 10, 10, 10)
        
        self.left_scroll.setWidget(self.left_widget)
        
        # Build initial UI
        self._build_dynamic_ui(self.combo_ic.currentText())
        
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
        splitter.addWidget(self.left_scroll)
        splitter.addWidget(right_widget)
        splitter.setSizes([450, 550]) # Initial sizes
        
        main_layout.addWidget(splitter)
        
    def _build_dynamic_ui(self, ic_name):
        # Clear existing dynamic widgets
        while self.left_layout.count():
            item = self.left_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if ic_name not in IC_CONFIGS:
            return
            
        config = IC_CONFIGS[ic_name]
        self.dynamic_inputs.clear()
        
        # 1. Voltage Group
        if "voltage" in config and config["voltage"]:
            group_vt = QGroupBox("Voltage Calibration (Sequence A)")
            grid_vt = QGridLayout()
            for i, (label_text, default_val) in enumerate(config["voltage"].items()):
                row = i // 2
                col = (i % 2) * 2
                grid_vt.addWidget(QLabel(label_text), row, col)
                line_edit = QLineEdit(default_val)
                self.dynamic_inputs[label_text] = line_edit
                grid_vt.addWidget(line_edit, row, col + 1)
            
            layout_vt = QVBoxLayout()
            layout_vt.addLayout(grid_vt)
            group_vt.setLayout(layout_vt)
            self.left_layout.addWidget(group_vt)
            
        # 2. Temperature Group
        if "temperature" in config and config["temperature"]:
            group_temp = QGroupBox("Temperature Calibration (Sequence B)")
            grid_temp = QGridLayout()
            for i, (label_text, default_val) in enumerate(config["temperature"].items()):
                row = i // 2
                col = (i % 2) * 2
                grid_temp.addWidget(QLabel(label_text), row, col)
                line_edit = QLineEdit(default_val)
                self.dynamic_inputs[label_text] = line_edit
                grid_temp.addWidget(line_edit, row, col + 1)
                
            layout_temp = QVBoxLayout()
            layout_temp.addLayout(grid_temp)
            group_temp.setLayout(layout_temp)
            self.left_layout.addWidget(group_temp)
            
        # 3. Current Group
        if "current" in config and config["current"]:
            group_c = QGroupBox("Current Calibration (Sequence C)")
            grid_c = QGridLayout()
            for i, (label_text, default_val) in enumerate(config["current"].items()):
                row = i // 2
                col = (i % 2) * 2
                grid_c.addWidget(QLabel(label_text), row, col)
                line_edit = QLineEdit(default_val)
                self.dynamic_inputs[label_text] = line_edit
                grid_c.addWidget(line_edit, row, col + 1)
                
            layout_c = QVBoxLayout()
            layout_c.addLayout(grid_c)
            group_c.setLayout(layout_c)
            self.left_layout.addWidget(group_c)
            
        # Add Global Start Button
        self.btn_cal_start = QPushButton(f"Start Calibration for {ic_name}")
        self.btn_cal_start.setMinimumHeight(40)
        self.btn_cal_start.setStyleSheet("font-weight: bold; background-color: #2E8B57; color: white;")
        self.btn_cal_start.clicked.connect(self.on_start_calib)
        self.left_layout.addWidget(self.btn_cal_start)
        
        self.left_layout.addStretch()
        
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
    def on_start_calib(self):
        port = self.combo_port.currentText()
        if not port or "Select" in port:
            self.log("Error: Please select a valid COM port.")
            return
            
        ch_text = self.combo_ch.currentText()
        ch = int(ch_text.split()[-1]) # e.g. "CH 6" -> 6
        ic = self.combo_ic.currentText()
        
        if ic not in IC_CONFIGS:
            self.log("Error: IC configuration not found.")
            return
            
        config = IC_CONFIGS[ic]
        
        # Parse all dynamic targets
        targets = {}
        for key, line_edit in self.dynamic_inputs.items():
            val = line_edit.text().strip()
            if val:
                try:
                    # Remove non-alphanumeric for safe target keys
                    safe_key = "".join(e for e in key if e.isalnum()).lower()
                    targets[safe_key] = int(val)
                    # Also keep the original key for display logic
                    targets[key] = int(val)
                except ValueError:
                    self.log(f"Error: Invalid numeric value for {key}.")
                    return
            
        # Construct path to the calib script
        script_name = config["script"]
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "calibrators", "scripts", script_name)
        if not os.path.exists(script_path):
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "calibrators", "scripts", script_name)
            
        if not os.path.exists(script_path):
            self.log(f"Error: Script file not found: {script_name}")
            return
            
        self.btn_cal_start.setEnabled(False)
        self.log(f"Starting {ic} calibration on {port}, {ch_text}...")
        self.table_data.setRowCount(0)
        
        self.cal_thread = CalibrationThread(port, ch, script_path, targets)
        self.cal_thread.log_signal.connect(self.log)
        self.cal_thread.row_signal.connect(self.add_table_row)
        self.cal_thread.finished_signal.connect(self.on_calib_finished)
        self.cal_thread.start()

    @Slot(bool)
    def on_calib_finished(self, success):
        self.btn_cal_start.setEnabled(True)
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
