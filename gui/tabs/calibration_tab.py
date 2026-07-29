import time
import os
import sys
import serial.tools.list_ports
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QTextEdit, QSplitter, QGridLayout,
    QHeaderView, QScrollArea, QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot, QSettings
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt, QSettings, Slot

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calibrators.calib_runner import CalibrationThread
from dialogs.limit_dialog import LimitsDialog

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "calib_config.json")

IC_CONFIGS = {
    "BQ40Z50": {
        "voltage": {
            "Cell 1 (mV)": "3200",
            "PACK (mV)": "12780", 
            "BAT (mV)": "12780"
        },
        "current": {
            "Current (mA)": "-1000"
        },
        "temperature": {
            "Int Temp (°C)": {"val": "25.0", "check": True}, 
            "TS1 Temp (°C)": {"val": "25.0", "check": True},
            "TS2 Temp (°C)": {"val": "25.0", "check": True}, 
            "TS3 Temp (°C)": {"val": "25.0", "check": True},
            "TS4 Temp (°C)": {"val": "25.0", "check": True}
        },
        "script": "bq40z50" # runner will append _voltage.calib, _temp.calib, _current.calib
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
        "script": "bq4050"
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
        "script": "bq34z100"
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
        "script": "bq78350"
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
        "script": "bq40z80"
    }
}

class CalibrationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Use explicitly named QSettings to match LimitsDialog and the rest of the application
        self.settings = QSettings("IBQ", "IBQtools")
        # Define script directory and base name for calibration scripts
        import os
        self.script_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calibrators", "scripts")
        # Use the script base defined in IC_CONFIGS for the selected IC (default to first key)
        self.script_base = "bq40z50"  # fallback; will be overridden when IC selected
        self.dynamic_inputs = {}
        self.dynamic_checks = {}

        self._init_ui()
        self.refresh_ports()
        
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- Top: Port & Channel Selection ---
        top_layout = QHBoxLayout()
        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(120)
        self.combo_port.currentTextChanged.connect(lambda t: self.settings.setValue("calib_last_port", t))
        
        self.btn_refresh_ports = QPushButton("Refresh")
        self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        
        self.combo_ic = QComboBox()
        self.combo_ic.addItems(list(IC_CONFIGS.keys()))
        last_ic = self.settings.value("calib_last_ic", "")
        if last_ic in IC_CONFIGS:
            self.combo_ic.setCurrentText(last_ic)
        self.combo_ic.currentTextChanged.connect(self._build_dynamic_ui)
        self.combo_ic.currentTextChanged.connect(lambda t: self.settings.setValue("calib_last_ic", t))
        
        top_layout.addWidget(QLabel("Target IC:"))
        top_layout.addWidget(self.combo_ic)
        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel("Channels:"))
        
        self.ch_checkboxes = []
        for i in range(1, 7):
            cb = QCheckBox(f"CH{i}")
            cb.setChecked(self.settings.value(f"calib_ch_{i}_en", "true") == "true")
            cb.toggled.connect(lambda checked, idx=i: self.settings.setValue(f"calib_ch_{idx}_en", "true" if checked else "false"))
            top_layout.addWidget(cb)
            self.ch_checkboxes.append(cb)
            
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
        # --- Right Panel: Console and Results Table ---
        self.right_widget = QWidget()
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        # Limit Button Header
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        self.btn_limits = QPushButton("Set Limits")
        self.btn_limits.setStyleSheet("background-color: #333333; color: white; padding: 5px 15px;")
        self.btn_limits.clicked.connect(self.on_open_limits)
        header_layout.addWidget(self.btn_limits)
        right_layout.addLayout(header_layout)
        
        # Table
        self.table_data = QTableWidget(0, 7)
        self.table_data.setHorizontalHeaderLabels(["Parameter", "CH1", "CH2", "CH3", "CH4", "CH5", "CH6"])
        self.table_data.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_data.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table_data.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_data.setAlternatingRowColors(True)
        self.table_data.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                gridline-color: #3a3a3a;
                border: 1px solid #3a3a3a;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                color: white;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #3a3a3a;
            }
        """)
        
        right_layout.addWidget(self.table_data, stretch=2)
        
        # Logs
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #1E1E1E; color: #00FF00; font-family: Consolas;")
        right_layout.addWidget(self.log_console, stretch=1)
        
        # Add to splitter
        splitter.addWidget(self.left_scroll)
        splitter.addWidget(self.right_widget)
        splitter.setSizes([450, 550]) # Initial sizes
        
        main_layout.addWidget(splitter)
        
    def _build_dynamic_ui(self, ic_name):
        # Clear existing dynamic widgets
        while self.left_layout.count():
            item = self.left_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # also need to clear layouts if they were added
                while item.layout().count():
                    sub_item = item.layout().takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()
                item.layout().deleteLater()
        
        if ic_name not in IC_CONFIGS:
            return
            
        config = IC_CONFIGS[ic_name]
        self.dynamic_inputs.clear()
        self.dynamic_checks.clear()
        
        # 1. Voltage Group
        if "voltage" in config and config["voltage"]:
            group_vt = QGroupBox("Voltage Calibration")
            grid_vt = QGridLayout()
            for i, (label_text, default_data) in enumerate(config["voltage"].items()):
                row = i // 2
                col = (i % 2) * 2
                val = default_data["val"] if isinstance(default_data, dict) else default_data
                saved_val = self.settings.value(f"calib_{ic_name}_{label_text}_val", val)
                
                grid_vt.addWidget(QLabel(label_text), row, col)
                line_edit = QLineEdit(str(saved_val))
                line_edit.textChanged.connect(lambda t, k=f"calib_{ic_name}_{label_text}_val": self.settings.setValue(k, t))
                self.dynamic_inputs[label_text] = line_edit
                grid_vt.addWidget(line_edit, row, col + 1)
            
            layout_vt = QVBoxLayout()
            layout_vt.addLayout(grid_vt)
            group_vt.setLayout(layout_vt)
            self.left_layout.addWidget(group_vt)
            
        # 2. Temperature Group
        if "temperature" in config and config["temperature"]:
            group_temp = QGroupBox("Temperature Calibration")
            grid_temp = QGridLayout()
            for i, (label_text, default_data) in enumerate(config["temperature"].items()):
                row = i // 2
                col = (i % 2) * 3
                val = default_data["val"] if isinstance(default_data, dict) else default_data
                saved_val = self.settings.value(f"calib_{ic_name}_{label_text}_val", val)
                
                # Checkbox
                if isinstance(default_data, dict) and default_data.get("check"):
                    chk = QCheckBox(label_text)
                    saved_check = self.settings.value(f"calib_{ic_name}_{label_text}_chk", "true")
                    # handle string/bool conversion for settings
                    is_checked = True if str(saved_check).lower() == "true" else False
                    chk.setChecked(is_checked)
                    chk.toggled.connect(lambda checked, k=f"calib_{ic_name}_{label_text}_chk": self.settings.setValue(k, checked))
                    
                    self.dynamic_checks[label_text] = chk
                    grid_temp.addWidget(chk, row, col)
                else:
                    grid_temp.addWidget(QLabel(label_text), row, col)
                    
                line_edit = QLineEdit(str(saved_val))
                line_edit.textChanged.connect(lambda t, k=f"calib_{ic_name}_{label_text}_val": self.settings.setValue(k, t))
                self.dynamic_inputs[label_text] = line_edit
                grid_temp.addWidget(line_edit, row, col + 1)
                
            layout_temp = QVBoxLayout()
            layout_temp.addLayout(grid_temp)
            group_temp.setLayout(layout_temp)
            self.left_layout.addWidget(group_temp)
            
        # 3. Current Group
        if "current" in config and config["current"]:
            group_c = QGroupBox("Current Calibration")
            grid_c = QGridLayout()
            for i, (label_text, default_data) in enumerate(config["current"].items()):
                row = i // 2
                col = (i % 2) * 2
                val = default_data["val"] if isinstance(default_data, dict) else default_data
                saved_val = self.settings.value(f"calib_{ic_name}_{label_text}_val", val)
                
                grid_c.addWidget(QLabel(label_text), row, col)
                line_edit = QLineEdit(str(saved_val))
                line_edit.textChanged.connect(lambda t, k=f"calib_{ic_name}_{label_text}_val": self.settings.setValue(k, t))
                self.dynamic_inputs[label_text] = line_edit
                grid_c.addWidget(line_edit, row, col + 1)
                
            layout_c = QVBoxLayout()
            layout_c.addLayout(grid_c)
            group_c.setLayout(layout_c)
            self.left_layout.addWidget(group_c)
            
        # Add 4 Buttons
        btn_layout = QHBoxLayout()
        self.btn_cal_v = QPushButton("Start Voltage")
        self.btn_cal_v.setStyleSheet("font-weight: bold; background-color: #2E8B57; color: white;")
        
        self.btn_cal_t = QPushButton("Start Temp")
        self.btn_cal_t.setStyleSheet("font-weight: bold; background-color: #2E8B57; color: white;")
        
        self.btn_cal_c = QPushButton("Start Current")
        self.btn_cal_c.setStyleSheet("font-weight: bold; background-color: #B22222; color: white;")
        
        self.btn_cal_all = QPushButton("Start All")
        self.btn_cal_all.setStyleSheet("font-weight: bold; background-color: #4169E1; color: white;")
        
        self.btn_cal_v.clicked.connect(lambda: self.on_start_calib("voltage"))
        self.btn_cal_t.clicked.connect(lambda: self.on_start_calib("temp"))
        self.btn_cal_c.clicked.connect(lambda: self.on_start_calib("current"))
        self.btn_cal_all.clicked.connect(lambda: self.on_start_calib("all"))
        
        btn_layout.addWidget(self.btn_cal_v)
        btn_layout.addWidget(self.btn_cal_t)
        btn_layout.addWidget(self.btn_cal_c)
        btn_layout.addWidget(self.btn_cal_all)
        
        self.left_layout.addLayout(btn_layout)
        self.left_layout.addStretch()
        
    def log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.log_console.append(f"[{timestamp}] {msg}")
        
    @Slot(str, int, str, str)
    def update_or_add_table_row(self, param, ch, value, status):
        if not hasattr(self, 'param_statuses'):
            self.param_statuses = {}
            
        if param not in self.param_statuses:
            self.param_statuses[param] = {}
        self.param_statuses[param][ch] = status
        
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
                item_val.setForeground(QColor("#FF4444"))
            elif status == "PASS":
                item_val.setForeground(QColor("#00FF00"))
            else:
                item_val.setForeground(QColor("#E0E0E0"))
        else:
            # Insert before Overall Result if it exists, else at bottom
            if overall_row != -1:
                insert_pos = overall_row
                overall_row += 1 # it shifts down
            else:
                insert_pos = self.table_data.rowCount()
                
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
            
        # Update Overall Result
        if overall_row == -1:
            overall_row = self.table_data.rowCount()
            self.table_data.insertRow(overall_row)
            item_param = QTableWidgetItem("Overall Result")
            item_param.setTextAlignment(Qt.AlignCenter)
            from PySide6.QtGui import QFont
            font = QFont()
            font.setBold(True)
            item_param.setFont(font)
            self.table_data.setItem(overall_row, 0, item_param)
            
        # For each channel, evaluate overall status
        from PySide6.QtGui import QFont
        font = QFont()
        font.setBold(True)
        
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
                item_overall = self.table_data.item(overall_row, active_ch)
                if not item_overall:
                    item_overall = QTableWidgetItem()
                    item_overall.setTextAlignment(Qt.AlignCenter)
                    item_overall.setFont(font)
                    self.table_data.setItem(overall_row, active_ch, item_overall)
                    
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
        # The LimitsDialog itself will now update the thread and settings when Save is clicked.
                
    @Slot(str)
    def on_start_calib(self, mode):
        # Prevent multiple threads from running simultaneously (ghost threads)
        if hasattr(self, 'cal_thread') and self.cal_thread and self.cal_thread.isRunning():
            self.cal_thread.stop()
            self.cal_thread.wait() # Wait for it to gracefully exit
            
        port = self.combo_port.currentText()
        if not port or "Select" in port:
            self.log("Error: Please select a valid COM port.")
            return
            
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
                    safe_key = "".join(e for e in key if e.isalnum()).lower()
                    targets[safe_key] = float(val) if '.' in val else int(val)
                    targets[key] = targets[safe_key]
                except ValueError:
                    self.log(f"Error: Invalid numeric value for {key}.")
                    return
        
        # Parse checkboxes
        for key, chk in self.dynamic_checks.items():
            safe_key = "".join(e for e in key if e.isalnum()).lower() + "_en"
            targets[safe_key] = chk.isChecked()
            
        # Modes requested
        targets["run_mode"] = mode
        
        selected_channels = []
        for i, cb in enumerate(self.ch_checkboxes):
            if cb.isChecked():
                selected_channels.append(i + 1)
                
        if not selected_channels:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Channels", "Please select at least one channel to calibrate.")
            return
            
        if not port:
            self.log("Error: No COM port selected.")
            return
            
        self.log_console.clear()
        ch_text = ", ".join([f"CH{ch}" for ch in selected_channels])
        self.log(f"Starting {ic} calibration ({mode} mode) on {port}, Channels: {ch_text}...")
        self.table_data.setRowCount(0)
        self.param_statuses = {}
        
        # Sync QSettings to clear cache before reading limits
        self.settings.sync()
        
        # Extract limits from settings
        limits = {}
        limit_keys = [
            "Cell 1 Gain", "Pack Gain", "Bat Gain",
            "Temp Gain", "Current Gain",
            "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4",
            "V_Bat", "V_Pack",
            "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp",
            "CC Current"
        ]
        for key in limit_keys:
            default_min = ""
            default_max = ""
            if "Gain" in key:
                default_min = "0"
                default_max = "65535"
            else:
                target_key = key.lower().replace(" ", "").replace("_", "")
                if "vcell" in target_key or "vpack" in target_key or "vbat" in target_key:
                    if "cell" in target_key:
                        default_min = str(targets.get("cell1mv", 3200))
                        default_max = default_min
                    elif "pack" in target_key:
                        default_min = str(targets.get("packmv", 12780))
                        default_max = default_min
                    elif "bat" in target_key:
                        default_min = str(targets.get("batmv", 12780))
                        default_max = default_min

            l_min = self.settings.value(f"limit_{ic}_{key}_min", default_min)
            l_max = self.settings.value(f"limit_{ic}_{key}_max", default_max)
            
            # If default target was used before save, might be empty, we handle that in runner
            if l_min != "" and l_max != "":
                try:
                    limits[key] = (float(l_min), float(l_max))
                except ValueError:
                    pass
                    
        self.log(f"DEBUG Extracted Limits for Thread: V_Bat={limits.get('V_Bat')} V_Cell3={limits.get('V_Cell 3')}")
        # Determine script base for the selected IC (fallback to default if missing)
        script_base = IC_CONFIGS.get(ic, {}).get("script", "bq40z50")
        try:
            self.cal_thread = CalibrationThread(port, selected_channels, self.script_dir, script_base, targets, ic, limits)
        except Exception as e:
            self.log(f"Error initializing CalibrationThread: {e}")
            return
        self.cal_thread.log_signal.connect(self.log)
        self.cal_thread.row_signal.connect(self.update_or_add_table_row)
        self.cal_thread.finished_signal.connect(self.on_calib_finished)
        self.cal_thread.start()

    @Slot(bool)
    def on_calib_finished(self, success):
        self.btn_cal_v.setEnabled(True)
        self.btn_cal_t.setEnabled(True)
        self.btn_cal_c.setEnabled(True)
        self.btn_cal_all.setEnabled(True)
        if success:
            self.log("Calibration finished successfully!")
        else:
            self.log("Calibration failed or was aborted.")

    def refresh_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.combo_port.addItem("Select Port")
        else:
            for p in ports:
                self.combo_port.addItem(p.device)
                
            last_port = self.settings.value("calib_last_port", "")
            if last_port:
                # Find index of last_port
                idx = self.combo_port.findText(last_port)
                if idx >= 0:
                    self.combo_port.setCurrentIndex(idx)
