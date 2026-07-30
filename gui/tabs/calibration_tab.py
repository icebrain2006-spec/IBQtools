import time
import os
import sys
import serial.tools.list_ports
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QTextEdit, QSplitter, QGridLayout,
    QHeaderView, QScrollArea, QCheckBox, QMenu
)
from PySide6.QtCore import Qt, Signal, Slot, QSettings
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtCore import Qt, QSettings, Slot

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calibrators.calib_runner import CalibrationThread
from dialogs.limit_dialog import LimitsDialog
from updater_thread import make_packet, CMD_RELAY_SET
import serial

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "calib_config.json")

IC_CONFIGS = {
    "BQ40Z50": {
        "voltage": {
            "Cell 1 (mV)": "3200",
            "PACK (mV)": "12780", 
            "BAT (mV)": "12780"
        },
        "current": {
            "Current (mA)": "-1000",
            "Shunt Resistor (mOhm)": "1.0"
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
            "Current (mA)": "-1000",
            "Shunt Resistor (mOhm)": "1.0"
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
            painter.fillRect(rect, QColor("#1e1e1e"))
        elif logicalIndex in self.active_cols:
            painter.fillRect(rect, QColor("#2d5a2d")) # Active Green
        else:
            painter.fillRect(rect, QColor("#222222")) # Inactive Gray
            
        # Border
        painter.setPen(QColor("#3a3a3a"))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        
        # Text
        if logicalIndex == 0 or logicalIndex in self.active_cols:
            painter.setPen(QColor("white"))
        else:
            painter.setPen(QColor("#888888"))
            
        text = self.model().headerData(logicalIndex, Qt.Horizontal, Qt.DisplayRole)
        if text:
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, str(text))
            
        painter.restore()

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
        self.selected_channels = set()
        for i in range(1, 7):
            if self.settings.value(f"calib_ch_{i}_en", "true") == "true":
                self.selected_channels.add(i)
                
        # We removed the top layout checkboxes here.
            
        top_layout.addStretch()
        main_layout.addLayout(top_layout)
        
        # --- Splitter for Left/Right Panels ---
        splitter = QSplitter(Qt.Horizontal)
        
        # --- Left Panel: Container for Scroll Controls + Logs ---
        left_container = QWidget()
        left_container_layout = QVBoxLayout(left_container)
        left_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)
        self.left_layout.setContentsMargins(10, 10, 10, 10)
        
        self.left_scroll.setWidget(self.left_widget)
        
        # Logs
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #1E1E1E; color: #00FF00; font-family: Consolas;")
        
        left_container_layout.addWidget(self.left_scroll, stretch=3)
        left_container_layout.addWidget(self.log_console, stretch=2)
        
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
        note_label = QLabel("Note: Click on a table header (CH1~CH6) to activate/deactivate channels.")
        note_label.setStyleSheet("color: #AAAAAA; font-style: italic;")
        header_layout.addWidget(note_label)
        header_layout.addStretch()
        self.btn_limits = QPushButton("Set Limits")
        self.btn_limits.setStyleSheet("background-color: #333333; color: white; padding: 5px 15px;")
        self.btn_limits.clicked.connect(self.on_open_limits)
        header_layout.addWidget(self.btn_limits)
        right_layout.addLayout(header_layout)
        
        # Table
        self.table_data = QTableWidget(0, 7)
        self.custom_header = CustomHeader(self.table_data)
        self.table_data.setHorizontalHeader(self.custom_header)
        
        self._update_headers() # Set initial header texts
        self.table_data.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, 7):
            self.table_data.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
        self.table_data.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table_data.verticalHeader().setDefaultSectionSize(22) # Compress row height
        self.table_data.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_data.setAlternatingRowColors(True)
        self.table_data.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                gridline-color: #3a3a3a;
                border: 1px solid #3a3a3a;
            }
            QHeaderView::section:vertical {
                background-color: #1e1e1e;
                color: white;
                font-weight: bold;
            }
        """)
        self.table_data.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_data.horizontalHeader().customContextMenuRequested.connect(self._on_header_context_menu)
        self.table_data.horizontalHeader().sectionClicked.connect(self._on_header_left_clicked)
        
        right_layout.addWidget(self.table_data, stretch=1)
        
        # Add to splitter
        splitter.addWidget(left_container)
        splitter.addWidget(self.right_widget)
        splitter.setSizes([400, 600]) # Initial sizes
        
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
        
    def _on_header_context_menu(self, pos):
        logical_index = self.table_data.horizontalHeader().logicalIndexAt(pos)
        if 1 <= logical_index <= 6:
            ch = logical_index
            menu = QMenu(self)
            action_on = menu.addAction(f"Turn Relay ON for CH{ch}")
            action_off = menu.addAction(f"Turn Relay OFF for CH{ch}")
            
            action_on.triggered.connect(lambda: self._toggle_manual_relay(ch, True))
            action_off.triggered.connect(lambda: self._toggle_manual_relay(ch, False))
            
            menu.exec(self.table_data.horizontalHeader().mapToGlobal(pos))
            
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
        
    def _toggle_manual_relay(self, ch, on):
        port = self.combo_port.currentText()
        if not port or "Select" in port:
            self.log("Error: Please select a COM port first to toggle relay.")
            return
            
        try:
            ser = serial.Serial(port, 115200, timeout=1.0)
            mask = (1 << (ch - 1)) if on else 0
            packet = make_packet(CMD_RELAY_SET, bytes([mask]))
            ser.reset_input_buffer()
            ser.write(packet)
            
            # Read response to prevent buffer accumulation on device
            rx = bytearray()
            while True:
                b = ser.read(1)
                if not b: break
                if b[0] == 0x02:
                    rx.extend(b)
                    break
            if rx:
                len_bytes = ser.read(2)
                rx.extend(len_bytes)
                if len(len_bytes) >= 2:
                    import struct
                    length = struct.unpack(">H", len_bytes)[0]
                    rx.extend(ser.read(length + 3))
                    
            ser.close()
            self.log(f"Manual Relay {'ON' if on else 'OFF'} executed for CH{ch}.")
        except Exception as e:
            self.log(f"Error toggling relay: {e}")

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
        
        def get_category(p_name):
            p = p_name.lower()
            if "temp" in p or "ts" in p: return 1
            if "cc" in p or "capacity" in p or "current" in p or "shunt" in p: return 2
            if "overall" in p: return 3
            return 0
            
        my_cat = get_category(param)
        
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
            # Find insertion position based on category to group them
            insert_pos = self.table_data.rowCount()
            for r in range(self.table_data.rowCount()):
                r_item = self.table_data.item(r, 0)
                if r_item:
                    if get_category(r_item.text()) > my_cat:
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
            1: QColor("#352323"), # Subtle red for Temp
            2: QColor("#353223"), # Subtle yellow/orange for Current
            3: QColor("#2b2b2b")  # Default dark for Overall
        }
        bg = bg_colors.get(my_cat, QColor("#2b2b2b"))
        for c in range(7):
            it = self.table_data.item(param_row, c)
            if not it:
                it = QTableWidgetItem("")
                self.table_data.setItem(param_row, c, it)
            it.setBackground(bg)
            
        # Update Overall Result
        if overall_row == -1:
            overall_row = self.table_data.rowCount()
            self.table_data.insertRow(overall_row)
            item_param = QTableWidgetItem("Overall Result")
            item_param.setTextAlignment(Qt.AlignCenter)
            from PySide6.QtGui import QFont
            font = QFont()
            font.setBold(True)
            font.setPointSize(14)
            item_param.setFont(font)
            self.table_data.setItem(overall_row, 0, item_param)
            
        self.table_data.setRowHeight(overall_row, 40)
            
        # For each channel, evaluate overall status
        from PySide6.QtGui import QFont
        font = QFont()
        font.setBold(True)
        font.setPointSize(14)
        
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
        
        selected_channels = sorted(list(self.selected_channels))
                
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
            "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4",
            "V_Bat", "V_Pack",
            "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp",
            "Shunt Resistor"
        ]
        for key in limit_keys:
            default_min = ""
            default_max = ""
            base_target = 0
            is_offset = False
            
            if key in ["Cell 1 Gain", "Pack Gain", "Bat Gain"]:
                default_min = "0"
                default_max = "65535"
            else:
                is_offset = True
                target_key = key.lower().replace(" ", "").replace("_", "")
                if "shunt" in target_key:
                    base_target = float(targets.get("shuntresistormohm", 1.0))
                    default_min = "-0.05"
                    default_max = "0.05"
                elif "vcell" in target_key or "vpack" in target_key or "vbat" in target_key:
                    default_min = "-20"
                    default_max = "20"
                    if "cell" in target_key:
                        base_target = float(targets.get("cell1mv", 3200))
                    elif "pack" in target_key:
                        base_target = float(targets.get("packmv", 12780))
                    elif "bat" in target_key:
                        base_target = float(targets.get("batmv", 12780))
                elif "temp" in target_key:
                    default_min = "-1.0"
                    default_max = "1.0"
                    if "int" in target_key:
                        base_target = float(targets.get("inttempc", 25.0))
                    elif "ts1" in target_key:
                        base_target = float(targets.get("ts1tempc", 25.0))
                    elif "ts2" in target_key:
                        base_target = float(targets.get("ts2tempc", 25.0))
                    elif "ts3" in target_key:
                        base_target = float(targets.get("ts3tempc", 25.0))
                    elif "ts4" in target_key:
                        base_target = float(targets.get("ts4tempc", 25.0))

            l_min = self.settings.value(f"limit_{ic}_{key}_min", default_min)
            l_max = self.settings.value(f"limit_{ic}_{key}_max", default_max)
            
            if l_min != "" and l_max != "":
                try:
                    v_min = float(l_min)
                    v_max = float(l_max)
                    if is_offset:
                        if key == "Shunt Resistor":
                            limits["CC Gain"] = (base_target + v_min, base_target + v_max)
                            limits["Capacity Gain"] = (base_target + v_min, base_target + v_max)
                        else:
                            limits[key] = (base_target + v_min, base_target + v_max)
                    else:
                        limits[key] = (v_min, v_max)
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
