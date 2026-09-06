from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QTextEdit, QSplitter, QGridLayout,
    QHeaderView, QScrollArea, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from gui.models import IC_CONFIGS
from gui.styles import Styles, Colors
from gui.strings import UIStrings
from gui.widgets import PortComboBox
from .table_mixin import CustomHeader


class CalibrationUIMixin:
    """Mixin for building the calibration tab layout and dynamic IC input controls."""

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- Top: Port & Channel Selection ---
        top_layout = QHBoxLayout()
        self.combo_port = PortComboBox()
        self.combo_port.setMinimumWidth(120)
        self.combo_port.currentTextChanged.connect(lambda t: self.settings.setValue("calib_last_port", t) if t and t != "Select COM" else None)
        
        self.btn_refresh_ports = QPushButton(UIStrings.get("BTN_REFRESH"))
        self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        
        self.combo_ic = QComboBox()
        self.combo_ic.addItems(list(IC_CONFIGS.keys()))
        last_ic = self.settings.value("calib_last_ic", "")
        if last_ic in IC_CONFIGS:
            self.combo_ic.setCurrentText(last_ic)
        self.combo_ic.currentTextChanged.connect(self._build_dynamic_ui)
        self.combo_ic.currentTextChanged.connect(lambda t: self.settings.setValue("calib_last_ic", t))
        
        top_layout.addWidget(QLabel(UIStrings.get("LBL_COM_PORT")))
        top_layout.addWidget(self.combo_port)
        top_layout.addWidget(self.btn_refresh_ports)
        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel(UIStrings.get("LBL_TARGET_IC")))
        top_layout.addWidget(self.combo_ic)
        top_layout.addSpacing(20)
        self.selected_channels = set()
        for i in range(1, 7):
            if self.settings.value(f"calib_ch_{i}_en", "true") == "true":
                self.selected_channels.add(i)
                
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
        self.log_console.setMaximumHeight(180)
        
        left_container_layout.addWidget(self.left_scroll, stretch=5)
        left_container_layout.addWidget(self.log_console, stretch=1)
        
        # Build initial UI
        self._build_dynamic_ui(self.combo_ic.currentText())
        
        # --- Right Panel: Console and Results Table ---
        self.right_widget = QWidget()
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        # Limit Button Header
        header_layout = QHBoxLayout()
        note_label = QLabel(UIStrings.get("NOTE_CHANNEL_TOGGLE"))
        note_label.setStyleSheet("color: #AAAAAA; font-style: italic;")
        header_layout.addWidget(note_label)
        header_layout.addStretch()
        self.btn_limits = QPushButton(UIStrings.get("BTN_SET_LIMITS"))
        self.btn_limits.setStyleSheet("background-color: #333333; color: white; padding: 5px 15px;")
        self.btn_limits.clicked.connect(self.on_open_limits)
        header_layout.addWidget(self.btn_limits)
        right_layout.addLayout(header_layout)
        
        # Table
        self.table_data = QTableWidget(0, 7)
        self.custom_header = CustomHeader(self.table_data)
        self.table_data.setHorizontalHeader(self.custom_header)
        
        self._update_headers()
        self.table_data.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, 7):
            self.table_data.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
        self.table_data.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table_data.verticalHeader().setDefaultSectionSize(22)
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
        
        # Overall Result Table
        self.table_overall = QTableWidget(1, 7)
        self.table_overall.horizontalHeader().hide()
        self.table_overall.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table_overall.verticalHeader().setDefaultSectionSize(30)
        self.table_overall.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_overall.setStyleSheet(self.table_data.styleSheet())
        self.table_overall.setMaximumHeight(35)
        self.table_overall.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        item_param = QTableWidgetItem(UIStrings.get("LBL_OVERALL_RESULT"))
        item_param.setTextAlignment(Qt.AlignCenter)
        font = QFont()
        font.setBold(True)
        item_param.setFont(font)
        self.table_overall.setItem(0, 0, item_param)
        
        for i in range(7):
            self.table_overall.horizontalHeader().setSectionResizeMode(i, self.table_data.horizontalHeader().sectionResizeMode(i))
            
        def sync_widths():
            self.table_overall.verticalHeader().setFixedWidth(self.table_data.verticalHeader().width())
            for i in range(7):
                self.table_overall.setColumnWidth(i, self.table_data.columnWidth(i))
                
        self.table_data.horizontalHeader().sectionResized.connect(sync_widths)
        
        right_layout.addWidget(self.table_overall)
        
        splitter.addWidget(left_container)
        splitter.addWidget(self.right_widget)
        splitter.setSizes([400, 600])
        
        main_layout.addWidget(splitter)
        self.refresh_ports()

    def _build_dynamic_ui(self, ic_name):
        while self.left_layout.count():
            item = self.left_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
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
        
        # 0. Channel Selection Header Bar
        ch_bar_box = QGroupBox()
        ch_bar_box.setStyleSheet(Styles.CH_BAR_BOX)
        ch_bar_layout = QHBoxLayout(ch_bar_box)
        ch_bar_layout.setContentsMargins(8, 4, 8, 4)
        
        btn_prev = QPushButton("◀")
        btn_prev.setFixedWidth(36)
        btn_prev.setStyleSheet(Styles.CH_NAV_BTN)
        btn_prev.clicked.connect(self._on_prev_ch)
        
        self.lbl_current_ch = QLabel(f"CH {self.current_channel}")
        self.lbl_current_ch.setStyleSheet(Styles.CH_LABEL)
        self.lbl_current_ch.setAlignment(Qt.AlignCenter)
        
        btn_next = QPushButton("▶")
        btn_next.setFixedWidth(36)
        btn_next.setStyleSheet(Styles.CH_NAV_BTN)
        btn_next.clicked.connect(self._on_next_ch)
        
        ch_label = QLabel(UIStrings.get("LBL_TARGET_CH"))
        ch_label.setStyleSheet(Styles.CH_TITLE)
        
        ch_bar_layout.addStretch()
        ch_bar_layout.addWidget(ch_label)
        ch_bar_layout.addWidget(btn_prev)
        ch_bar_layout.addWidget(self.lbl_current_ch)
        ch_bar_layout.addWidget(btn_next)
        ch_bar_layout.addStretch()
        
        self.left_layout.addWidget(ch_bar_box)
        
        # 1. Voltage Group
        if "voltage" in config and config["voltage"]:
            group_vt = QGroupBox(UIStrings.get("GRP_VOLTAGE_CALIB"))
            grid_vt = QGridLayout()
            
            v_cols = 3 if len(config["voltage"]) > 10 else 2
            
            for i, (label_text, default_data) in enumerate(config["voltage"].items()):
                row = i // v_cols
                col = (i % v_cols) * 2
                val = default_data["val"] if isinstance(default_data, dict) else default_data
                global_fallback = self.settings.value(f"calib_{ic_name}_{label_text}_val", val)
                saved_val = self.settings.value(f"calib_ch{self.current_channel}_{ic_name}_{label_text}_val", global_fallback)
                
                grid_vt.addWidget(QLabel(label_text), row, col)
                line_edit = QLineEdit(str(saved_val))
                line_edit.textChanged.connect(lambda t, k=label_text: self.settings.setValue(f"calib_ch{self.current_channel}_{ic_name}_{k}_val", t))
                self.dynamic_inputs[label_text] = line_edit
                grid_vt.addWidget(line_edit, row, col + 1)
            
            layout_vt = QVBoxLayout()
            layout_vt.addLayout(grid_vt)
            group_vt.setLayout(layout_vt)
            self.left_layout.addWidget(group_vt)
            
        # 2. Temperature Group
        if "temperature" in config and config["temperature"]:
            group_temp = QGroupBox(UIStrings.get("GRP_TEMP_CALIB"))
            grid_temp = QGridLayout()
            for i, (label_text, default_data) in enumerate(config["temperature"].items()):
                row = i // 2
                col = (i % 2) * 3
                val = default_data["val"] if isinstance(default_data, dict) else default_data
                global_fallback = self.settings.value(f"calib_{ic_name}_{label_text}_val", val)
                saved_val = self.settings.value(f"calib_ch{self.current_channel}_{ic_name}_{label_text}_val", global_fallback)
                
                if isinstance(default_data, dict) and default_data.get("check"):
                    chk = QCheckBox(label_text)
                    global_chk_fallback = self.settings.value(f"calib_{ic_name}_{label_text}_chk", "true")
                    saved_check = self.settings.value(f"calib_ch{self.current_channel}_{ic_name}_{label_text}_chk", global_chk_fallback)
                    is_checked = True if str(saved_check).lower() == "true" else False
                    chk.setChecked(is_checked)
                    chk.toggled.connect(lambda checked, k=label_text: self.settings.setValue(f"calib_ch{self.current_channel}_{ic_name}_{k}_chk", checked))
                    
                    self.dynamic_checks[label_text] = chk
                    grid_temp.addWidget(chk, row, col)
                else:
                    grid_temp.addWidget(QLabel(label_text), row, col)
                    
                line_edit = QLineEdit(str(saved_val))
                line_edit.textChanged.connect(lambda t, k=label_text: self.settings.setValue(f"calib_ch{self.current_channel}_{ic_name}_{k}_val", t))
                self.dynamic_inputs[label_text] = line_edit
                grid_temp.addWidget(line_edit, row, col + 1)
                
            layout_temp = QVBoxLayout()
            layout_temp.addLayout(grid_temp)
            group_temp.setLayout(layout_temp)
            self.left_layout.addWidget(group_temp)
            
        # 3. Current Group
        if "current" in config and config["current"]:
            group_c = QGroupBox(UIStrings.get("GRP_CURRENT_CALIB"))
            grid_c = QGridLayout()
            for i, (label_text, default_data) in enumerate(config["current"].items()):
                row = i // 2
                col = (i % 2) * 2
                val = default_data["val"] if isinstance(default_data, dict) else default_data
                global_fallback = self.settings.value(f"calib_{ic_name}_{label_text}_val", val)
                saved_val = self.settings.value(f"calib_ch{self.current_channel}_{ic_name}_{label_text}_val", global_fallback)
                
                grid_c.addWidget(QLabel(label_text), row, col)
                line_edit = QLineEdit(str(saved_val))
                line_edit.textChanged.connect(lambda t, k=label_text: self.settings.setValue(f"calib_ch{self.current_channel}_{ic_name}_{k}_val", t))
                self.dynamic_inputs[label_text] = line_edit
                grid_c.addWidget(line_edit, row, col + 1)
                
            layout_c = QVBoxLayout()
            layout_c.addLayout(grid_c)
            group_c.setLayout(layout_c)
            self.left_layout.addWidget(group_c)
            
        # Buttons
        btn_layout = QHBoxLayout()
        
        def get_btn_style(bg_col, border_col):
            return f"""
                QPushButton {{
                    background-color: {bg_col};
                    color: white;
                    border: 1px solid {border_col};
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {border_col};
                }}
            """
            
        self.btn_cal_v = QPushButton(UIStrings.get("BTN_START_VOLTAGE"))
        self.btn_cal_v.setStyleSheet(get_btn_style("#232a35", "#3a5070"))
        
        self.btn_cal_t = QPushButton(UIStrings.get("BTN_START_TEMP"))
        self.btn_cal_t.setStyleSheet(get_btn_style("#352335", "#703a70"))
        
        self.btn_cal_c = QPushButton(UIStrings.get("BTN_START_CURRENT"))
        self.btn_cal_c.setStyleSheet(get_btn_style("#353223", "#70663a"))
        
        self.btn_cal_all = QPushButton(UIStrings.get("BTN_START_ALL"))
        self.btn_cal_all.setStyleSheet(get_btn_style("#2b2b2b", "#555555"))
        
        self.btn_quick_start = QPushButton(UIStrings.get("BTN_QUICK_START"))
        self.btn_quick_start.setCheckable(True)
        self.btn_quick_start.setStyleSheet("""
            QPushButton {
                background-color: #222222;
                color: #AAAAAA;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #004d40;
                color: white;
                border: 1px solid #00e676;
            }
        """)
        self.btn_quick_start.setToolTip(UIStrings.get("TOOLTIP_QUICK_START"))
        
        self.btn_cal_v.clicked.connect(lambda: self.on_start_calib("voltage"))
        self.btn_cal_t.clicked.connect(lambda: self.on_start_calib("temp"))
        self.btn_cal_c.clicked.connect(lambda: self.on_start_calib("current"))
        self.btn_cal_all.clicked.connect(lambda: self.on_start_calib("all"))
        
        btn_layout.addWidget(self.btn_cal_v)
        btn_layout.addWidget(self.btn_cal_t)
        btn_layout.addWidget(self.btn_cal_c)
        btn_layout.addWidget(self.btn_cal_all)
        btn_layout.addWidget(self.btn_quick_start)
        
        self.left_layout.addLayout(btn_layout)
        self.left_layout.addStretch()

    def is_hotkey_ready(self):
        return hasattr(self, 'btn_quick_start') and self.btn_quick_start.isChecked()
        
    def trigger_start_all(self):
        if hasattr(self, 'btn_cal_all') and self.btn_cal_all.isEnabled():
            self.btn_cal_all.click()
