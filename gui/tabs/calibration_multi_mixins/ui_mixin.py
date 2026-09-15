from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QTextEdit, QSplitter, QGridLayout,
    QHeaderView, QScrollArea, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QFont

from gui.models import IC_CONFIGS
from gui.styles import Styles, Colors
from gui.strings import UIStrings
from gui.widgets import PortComboBox
from .table_mixin import CustomHeader


class MultiCalibrationUIMixin:
    """Mixin for building the 18-Channel multi-board calibration tab layout with Compact Horizontal Alignment."""

    def refresh_ports(self):
        from gui.widgets.port_combo import get_available_ports
        sorted_ports, _ = get_available_ports(include_none=False)
        physical_ports = [p for p in sorted_ports if p and p not in ("Select COM", "None")]

        for idx in range(1, 4):
            combo = getattr(self, f"combo_port_{idx}", None)
            if combo:
                combo.blockSignals(True)
                current = combo.currentText()
                combo.clear()
                combo_items = ["None"] + physical_ports
                combo.addItems(combo_items)
                if current in combo_items:
                    combo.setCurrentText(current)
                combo.blockSignals(False)

        self._smart_distribute_ports(physical_ports)

    def _smart_distribute_ports(self, physical_ports):
        """Assigns available physical ports across Boards 1..3 avoiding duplicate COM assignments."""
        combos = [getattr(self, f"combo_port_{idx}", None) for idx in range(1, 4)]
        if any(c is None for c in combos):
            return

        current_choices = [c.currentText() for c in combos]
        used_ports = set()
        needs_reassign = False

        for p in current_choices:
            if p and p not in ("None", "Select COM"):
                if p not in physical_ports or p in used_ports:
                    needs_reassign = True
                    break
                used_ports.add(p)

        if needs_reassign or (not used_ports and physical_ports):
            for idx, combo in enumerate(combos, 1):
                assigned = physical_ports[idx - 1] if idx - 1 < len(physical_ports) else "None"
                combo.blockSignals(True)
                combo.setCurrentText(assigned)
                self.settings.setValue(f"calib_multi_port_{idx}", assigned)
                combo.blockSignals(False)

    def _on_board_port_changed(self, board_idx, new_port):
        if not new_port or new_port in ("Select COM", "None"):
            self.settings.setValue(f"calib_multi_port_{board_idx}", "None")
            return

        self.settings.setValue(f"calib_multi_port_{board_idx}", new_port)

        for other_idx in range(1, 4):
            if other_idx == board_idx:
                continue
            other_combo = getattr(self, f"combo_port_{other_idx}", None)
            if other_combo and other_combo.currentText() == new_port:
                other_combo.blockSignals(True)
                other_combo.setCurrentText("None")
                self.settings.setValue(f"calib_multi_port_{other_idx}", "None")
                other_combo.blockSignals(False)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- Top Section: Global IC Bar + 3 Board Boxes + Action Buttons + Logs ---
        top_container = QWidget()
        top_container_layout = QVBoxLayout(top_container)
        top_container_layout.setContentsMargins(0, 0, 0, 0)
        top_container_layout.setSpacing(4)
        
        # 1. Global Bar: Target IC, Refresh Ports & Header Instruction Note
        global_bar = QHBoxLayout()
        global_bar.setContentsMargins(5, 2, 5, 2)
        
        self.btn_refresh_ports = QPushButton(UIStrings.get("BTN_REFRESH"))
        self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        
        self.combo_ic = QComboBox()
        self.combo_ic.addItems(list(IC_CONFIGS.keys()))
        last_ic = self.settings.value("calib_last_ic", "BQ40Z50")
        if last_ic not in IC_CONFIGS and "BQ40Z50" in IC_CONFIGS:
            last_ic = "BQ40Z50"
        if last_ic in IC_CONFIGS:
            self.combo_ic.setCurrentText(last_ic)
        self.combo_ic.currentTextChanged.connect(self._build_dynamic_ui)
        self.combo_ic.currentTextChanged.connect(lambda t: self.settings.setValue("calib_last_ic", t))
        
        global_bar.addWidget(QLabel(UIStrings.get("LBL_TARGET_IC")))
        global_bar.addWidget(self.combo_ic)
        global_bar.addSpacing(15)
        global_bar.addWidget(self.btn_refresh_ports)
        global_bar.addSpacing(15)

        note_label = QLabel("Click headers (B1-CH1..B3-CH6) to toggle active channel. Right-click for relay.")
        note_label.setStyleSheet("color: #888888; font-style: italic; font-size: 11px;")
        global_bar.addWidget(note_label)
        global_bar.addStretch()
        
        top_container_layout.addLayout(global_bar)
        
        # 2. Main Middle Row: [Board #1] [Board #2] [Board #3] | [Buttons] | [Log Console]
        middle_controls_layout = QHBoxLayout()
        middle_controls_layout.setContentsMargins(0, 0, 0, 0)
        middle_controls_layout.setSpacing(6)
        
        self.top_controls_widget = QWidget()
        self.left_layout = QHBoxLayout(self.top_controls_widget)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(6)
        
        # Action Buttons Column (Vertical)
        self.btn_widget = QWidget()
        btn_vlayout = QVBoxLayout(self.btn_widget)
        btn_vlayout.setContentsMargins(0, 5, 0, 0)
        btn_vlayout.setSpacing(3)
        
        def get_btn_style(bg_col, border_col):
            return f"""
                QPushButton {{
                    background-color: {bg_col};
                    color: white;
                    border: 1px solid {border_col};
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: 11px;
                    font-weight: bold;
                    min-width: 85px;
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
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                font-weight: bold;
                min-width: 85px;
            }
            QPushButton:checked {
                background-color: #004d40;
                color: white;
                border: 1px solid #00e676;
            }
        """)

        self.btn_limits = QPushButton(UIStrings.get("BTN_SET_LIMITS"))
        self.btn_limits.setStyleSheet(get_btn_style("#333333", "#555555"))
        self.btn_limits.clicked.connect(self.on_open_limits)
        
        self.btn_cal_v.clicked.connect(lambda: self.on_start_calib("voltage"))
        self.btn_cal_t.clicked.connect(lambda: self.on_start_calib("temp"))
        self.btn_cal_c.clicked.connect(lambda: self.on_start_calib("current"))
        self.btn_cal_all.clicked.connect(lambda: self.on_start_calib("all"))
        
        action_btns = [
            self.btn_cal_v,
            self.btn_cal_t,
            self.btn_cal_c,
            self.btn_cal_all,
            self.btn_quick_start,
            self.btn_limits
        ]
        for btn in action_btns:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn_vlayout.addWidget(btn, 1)
        
        # Log Console Container with Title Header
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(2)
        
        lbl_log_title = QLabel("Execution Log Console")
        lbl_log_title.setStyleSheet("font-weight: bold; color: #888888; font-size: 11px;")
        log_layout.addWidget(lbl_log_title)
        
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #1E1E1E; color: #00FF00; font-family: Consolas;")
        self.log_console.setMinimumWidth(200)
        log_layout.addWidget(self.log_console)
        
        middle_controls_layout.addWidget(self.top_controls_widget, stretch=0)
        middle_controls_layout.addWidget(self.btn_widget, stretch=0)
        middle_controls_layout.addWidget(log_container, stretch=1)
        
        top_container_layout.addLayout(middle_controls_layout)
        
        self.selected_channels = set()
        for i in range(1, 19):
            if self.settings.value(f"calib_multi_ch_{i}_en", "true") == "true":
                self.selected_channels.add(i)

        # Build dynamic UI for input controls
        self._build_dynamic_ui(self.combo_ic.currentText())
        
        # --- Splitter Vertical: Top (3 Board Boxes + Logs) / Bottom (18-CH Table) ---
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #3a3a3a; height: 2px; }")
        
        # --- Bottom Section: Single 18-Channel Table ---
        self.right_container = QWidget()
        right_container_layout = QVBoxLayout(self.right_container)
        right_container_layout.setContentsMargins(0, 0, 0, 0)
        right_container_layout.setSpacing(2)
        
        # Table with 19 columns (1 param + 18 channels)
        self.table_data = QTableWidget(0, 19)
        self.custom_header = CustomHeader(self.table_data)
        self.table_data.setHorizontalHeader(self.custom_header)
        
        self.table_data.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, 19):
            self.table_data.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
        self.table_data.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table_data.verticalHeader().setMinimumSectionSize(20)
        self.table_data.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
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
        
        right_container_layout.addWidget(self.table_data, stretch=1)
        
        # Overall Result Table
        self.table_overall = QTableWidget(1, 19)
        self.table_overall.horizontalHeader().hide()
        self.table_overall.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table_overall.verticalHeader().setDefaultSectionSize(28)
        self.table_overall.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_overall.setStyleSheet(self.table_data.styleSheet())
        self.table_overall.setFixedHeight(30)
        self.table_overall.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_overall.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        item_param = QTableWidgetItem(UIStrings.get("LBL_OVERALL_RESULT"))
        item_param.setTextAlignment(Qt.AlignCenter)
        font = QFont()
        font.setBold(True)
        item_param.setFont(font)
        self.table_overall.setItem(0, 0, item_param)
        
        for i in range(19):
            self.table_overall.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
            
        self.table_data.horizontalHeader().sectionResized.connect(self._sync_overall_widths)
        self.table_data.horizontalHeader().geometriesChanged.connect(self._sync_overall_widths)
        self.table_data.horizontalScrollBar().valueChanged.connect(self.table_overall.horizontalScrollBar().setValue)
        self.table_data.installEventFilter(self)
        
        right_container_layout.addWidget(self.table_overall)
        
        self._update_headers()
        
        splitter.addWidget(top_container)
        splitter.addWidget(self.right_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        self._build_dynamic_ui(self.combo_ic.currentText())
        self.refresh_ports()
        self._sync_overall_widths()

    def eventFilter(self, watched, event):
        if hasattr(self, 'table_data') and watched == self.table_data and event.type() == QEvent.Resize:
            self._sync_overall_widths()
        return super().eventFilter(watched, event) if hasattr(super(), 'eventFilter') else False

    def _sync_overall_widths(self, *args):
        if not hasattr(self, 'table_data') or not hasattr(self, 'table_overall'):
            return
        vh_width = self.table_data.verticalHeader().width()
        self.table_overall.verticalHeader().setFixedWidth(vh_width)
        for i in range(19):
            w = self.table_data.columnWidth(i)
            self.table_overall.setColumnWidth(i, w)

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
        self.dynamic_inputs = {1: {}, 2: {}, 3: {}}
        self.dynamic_checks = {1: {}, 2: {}, 3: {}}
        self.board_current_ch = {1: 1, 2: 7, 3: 13}
        
        board_themes = {
            1: {"title": "Board #1 (CH 1~6)", "color": "#006666"},
            2: {"title": "Board #2 (CH 7~12)", "color": "#2d662d"},
            3: {"title": "Board #3 (CH 13~18)", "color": "#660066"}
        }

        for b in range(1, 4):
            theme = board_themes[b]
            group_b = QGroupBox(theme["title"])
            group_b.setMaximumWidth(285)
            group_b.setStyleSheet(f"""
                QGroupBox {{
                    background-color: #1e1e1e;
                    border: 1px solid {theme['color']};
                    border-radius: 4px;
                    margin-top: 18px;
                    padding-top: 4px;
                    font-weight: bold;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 1px 6px;
                    color: white;
                    background-color: {theme['color']};
                    border-radius: 2px;
                }}
            """)
            
            b_layout = QVBoxLayout(group_b)
            b_layout.setContentsMargins(6, 4, 6, 6)
            b_layout.setSpacing(4)

            # --- Row 1: COM Port Combo + Target CH Selector ---
            hdr_box = QHBoxLayout()
            hdr_box.setContentsMargins(0, 0, 0, 0)
            hdr_box.setSpacing(3)

            combo_port = PortComboBox(include_none=True)
            combo_port.setMinimumWidth(85)
            combo_port.setStyleSheet("""
                QComboBox {
                    font-size: 11px;
                    padding: 1px 4px;
                    border: 1px solid #444;
                    border-radius: 3px;
                    background-color: #262626;
                    color: #EEE;
                }
                QComboBox QAbstractItemView {
                    font-size: 11px;
                    background-color: #262626;
                    color: #EEE;
                }
            """)
            combo_port.currentTextChanged.connect(
                lambda t, b_idx=b: self._on_board_port_changed(b_idx, t)
            )
            setattr(self, f"combo_port_{b}", combo_port)
            last_p = self.settings.value(f"calib_multi_port_{b}", "")
            if last_p and last_p in [combo_port.itemText(i) for i in range(combo_port.count())]:
                combo_port.setCurrentText(last_p)

            lbl_port = QLabel("Port:")
            lbl_port.setStyleSheet("font-size: 11px; color: #CCC;")
            hdr_box.addWidget(lbl_port)
            hdr_box.addWidget(combo_port)
            
            # Stretch pushes channel navigation right-aligned!
            hdr_box.addStretch(1)

            nav_btn_style = """
                QPushButton {
                    background-color: #2b2b2b;
                    color: #00E676;
                    border: 1px solid #444;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #383838;
                    color: #69F0AE;
                }
            """

            btn_prev = QPushButton("◀")
            btn_prev.setFixedWidth(22)
            btn_prev.setFixedHeight(22)
            btn_prev.setStyleSheet(nav_btn_style)
            btn_prev.clicked.connect(lambda _, board=b: self._on_prev_board_ch(board))

            lbl_ch = QLabel()
            lbl_ch.setStyleSheet("font-size: 11px; font-weight: bold; color: #69F0AE; padding: 0 4px;")
            lbl_ch.setAlignment(Qt.AlignCenter)
            setattr(self, f"lbl_ch_board_{b}", lbl_ch)

            btn_next = QPushButton("▶")
            btn_next.setFixedWidth(22)
            btn_next.setFixedHeight(22)
            btn_next.setStyleSheet(nav_btn_style)
            btn_next.clicked.connect(lambda _, board=b: self._on_next_board_ch(board))

            hdr_box.addWidget(btn_prev)
            hdr_box.addWidget(lbl_ch)
            hdr_box.addWidget(btn_next)

            b_layout.addLayout(hdr_box)

            line_edit_style = "QLineEdit { padding: 1px 3px; font-size: 11px; border: 1px solid #444; border-radius: 3px; background-color: #262626; color: #EEE; }"
            chk_style = "QCheckBox { spacing: 2px; font-size: 11px; color: #DDD; } QCheckBox::indicator { width: 13px; height: 13px; }"

            def clean_label(text):
                res = text.replace(" (mV)", "").replace(" (mA)", "").replace(" (mOhm)", "")
                res = res.replace(" Temp (°C)", "").replace(" (°C)", "").replace(" Resistor", "")
                return res

            # --- Row 2: Voltage & Current Inputs (Side-by-Side, Top-Aligned) ---
            vc_layout = QHBoxLayout()
            vc_layout.setContentsMargins(0, 0, 0, 0)
            vc_layout.setSpacing(8)
            vc_layout.setAlignment(Qt.AlignTop)

            if "voltage" in config and config["voltage"]:
                v_box = QVBoxLayout()
                v_box.setContentsMargins(0, 0, 0, 0)
                v_box.setSpacing(2)
                v_box.setAlignment(Qt.AlignTop)

                lbl_v = QLabel("Voltage (mV)")
                lbl_v.setStyleSheet("font-weight: bold; color: #81D4FA; font-size: 10px; padding: 0px; margin: 0px;")
                v_box.addWidget(lbl_v)

                v_grid = QGridLayout()
                v_grid.setContentsMargins(0, 0, 0, 0)
                v_grid.setHorizontalSpacing(4)
                v_grid.setVerticalSpacing(2)

                for i, (label_text, default_data) in enumerate(config["voltage"].items()):
                    r, c = i // 2, (i % 2) * 2
                    lbl_item = QLabel(clean_label(label_text))
                    lbl_item.setStyleSheet("font-size: 11px;")
                    v_grid.addWidget(lbl_item, r, c)

                    line_edit = QLineEdit()
                    line_edit.setFixedWidth(50)
                    line_edit.setFixedHeight(22)
                    line_edit.setStyleSheet(line_edit_style)
                    line_edit.textChanged.connect(
                        lambda t, board=b, k=label_text: self.settings.setValue(f"calib_multi_ch{self.board_current_ch[board]}_{ic_name}_{k}_val", t)
                    )
                    self.dynamic_inputs[b][label_text] = line_edit
                    v_grid.addWidget(line_edit, r, c + 1)

                v_box.addLayout(v_grid)
                vc_layout.addLayout(v_box)

            if "current" in config and config["current"]:
                c_box = QVBoxLayout()
                c_box.setContentsMargins(0, 0, 0, 0)
                c_box.setSpacing(2)
                c_box.setAlignment(Qt.AlignTop)

                lbl_c = QLabel("Current (mA / mOhm)")
                lbl_c.setStyleSheet("font-weight: bold; color: #FFE082; font-size: 10px; padding: 0px; margin: 0px;")
                c_box.addWidget(lbl_c)

                c_vlayout = QVBoxLayout()
                c_vlayout.setContentsMargins(0, 0, 0, 0)
                c_vlayout.setSpacing(2)

                for i, (label_text, default_data) in enumerate(config["current"].items()):
                    c_row = QHBoxLayout()
                    c_row.setContentsMargins(0, 0, 0, 0)
                    c_row.setSpacing(4)
                    
                    lbl_item = QLabel(clean_label(label_text))
                    lbl_item.setFixedWidth(44)  # Fixed width ensures textboxes align vertically!
                    lbl_item.setStyleSheet("font-size: 11px;")
                    c_row.addWidget(lbl_item)

                    line_edit = QLineEdit()
                    line_edit.setFixedWidth(50)
                    line_edit.setFixedHeight(22)
                    line_edit.setStyleSheet(line_edit_style)
                    line_edit.textChanged.connect(
                        lambda t, board=b, k=label_text: self.settings.setValue(f"calib_multi_ch{self.board_current_ch[board]}_{ic_name}_{k}_val", t)
                    )
                    self.dynamic_inputs[b][label_text] = line_edit
                    c_row.addWidget(line_edit)
                    c_row.addStretch(1)

                    c_vlayout.addLayout(c_row)

                c_box.addLayout(c_vlayout)
                vc_layout.addLayout(c_box)

            b_layout.addLayout(vc_layout)

            # --- Row 3: Temp Inputs ---
            if "temperature" in config and config["temperature"]:
                t_box = QVBoxLayout()
                t_box.setContentsMargins(0, 2, 0, 0)
                t_box.setSpacing(2)
                t_box.setAlignment(Qt.AlignTop)

                lbl_t = QLabel("Temp (°C)")
                lbl_t.setStyleSheet("font-weight: bold; color: #E1BEE7; font-size: 10px; margin-top: 4px; margin-bottom: 0px; padding: 0px;")
                t_box.addWidget(lbl_t)

                t_grid = QGridLayout()
                t_grid.setContentsMargins(0, 0, 0, 0)
                t_grid.setHorizontalSpacing(4)
                t_grid.setVerticalSpacing(2)

                for i, (label_text, default_data) in enumerate(config["temperature"].items()):
                    r = i // 3
                    c = i % 3
                    
                    pair_widget = QWidget()
                    pair_layout = QHBoxLayout(pair_widget)
                    pair_layout.setContentsMargins(0, 0, 0, 0)
                    pair_layout.setSpacing(3)

                    display_name = clean_label(label_text)
                    if isinstance(default_data, dict) and default_data.get("check"):
                        chk = QCheckBox(display_name)
                        chk.setMinimumWidth(38)
                        chk.setStyleSheet(chk_style)
                        chk.toggled.connect(
                            lambda checked, board=b, k=label_text: self.settings.setValue(f"calib_multi_ch{self.board_current_ch[board]}_{ic_name}_{k}_chk", checked)
                        )
                        self.dynamic_checks[b][label_text] = chk
                        pair_layout.addWidget(chk)
                    else:
                        lbl_item = QLabel(display_name)
                        lbl_item.setMinimumWidth(38)
                        lbl_item.setStyleSheet("font-size: 11px;")
                        pair_layout.addWidget(lbl_item)

                    line_edit = QLineEdit()
                    line_edit.setFixedWidth(42)
                    line_edit.setFixedHeight(22)
                    line_edit.setStyleSheet(line_edit_style)
                    line_edit.textChanged.connect(
                        lambda t, board=b, k=label_text: self.settings.setValue(f"calib_multi_ch{self.board_current_ch[board]}_{ic_name}_{k}_val", t)
                    )
                    self.dynamic_inputs[b][label_text] = line_edit
                    pair_layout.addWidget(line_edit)

                    t_grid.addWidget(pair_widget, r, c)

                t_box.addLayout(t_grid)
                b_layout.addLayout(t_box)

            self.left_layout.addWidget(group_b, stretch=0)

            # Initial load of values for board b
            self._load_board_inputs(b, self.board_current_ch[b])
