"""UI layout mixin for Auto Cycle & BQ Logger tab."""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QFileDialog, QSplitter,
    QFrame, QWidget, QTextEdit, QCheckBox, QGroupBox
)
from PySide6.QtCore import Qt
from gui.widgets.port_combo import PortComboBox
from gui.strings import UIStrings


class UiMixin:
    """Builds the comprehensive UI layout for Auto Cycle & BQ Logger."""

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Wiring Guide & Relay Status Banner
        main_layout.addWidget(self._build_wiring_banner())

        # 2. Control Toolbar
        main_layout.addWidget(self._build_control_toolbar())

        # 3. Main Splitter (Left: Status Matrix, Right: Telemetry & Log)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter, 1)

    def _build_wiring_banner(self) -> QFrame:
        banner = QFrame()
        banner.setStyleSheet("background-color: #1a2332; border: 1px solid #1976d2; border-radius: 4px; padding: 4px;")
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(8, 2, 8, 2)

        lbl_guide = QLabel("⚡ <b>RP2040 Wiring:</b> CH1 = Power Supply (Charger) | CH2 = Electronic Load (Discharge) | 🔌 SMBus = CH1")
        lbl_guide.setStyleSheet("color: #90caf9; font-size: 11px;")
        layout.addWidget(lbl_guide)
        layout.addStretch(1)

        self.badge_power = QLabel("CH1 Power: OFF")
        self.badge_power.setStyleSheet("background-color: #333333; color: #888888; font-weight: bold; padding: 3px 8px; border-radius: 3px; font-size: 10px;")
        layout.addWidget(self.badge_power)

        self.badge_load = QLabel("CH2 Load: OFF")
        self.badge_load.setStyleSheet("background-color: #333333; color: #888888; font-weight: bold; padding: 3px 8px; border-radius: 3px; font-size: 10px;")
        layout.addWidget(self.badge_load)
        return banner

    def _build_control_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("background-color: #222222; border: 1px solid #333333; border-radius: 4px;")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Port & Target IC
        layout.addWidget(QLabel("Port:"))
        self.combo_port = PortComboBox()
        self.combo_port.setMinimumWidth(85)
        layout.addWidget(self.combo_port)

        self.btn_refresh = QPushButton(UIStrings.get("BTN_REFRESH"))
        self.btn_refresh.clicked.connect(self.combo_port.refresh_ports)
        layout.addWidget(self.btn_refresh)

        layout.addWidget(QLabel("Target IC:"))
        self.combo_ic = QComboBox()
        self.combo_ic.addItems(["BQ40Z50", "BQ4050", "BQ78350"])
        layout.addWidget(self.combo_ic)

        # File path
        layout.addWidget(QLabel("CSV:"))
        self.txt_file_path = QLineEdit()
        self.txt_file_path.setPlaceholderText("Select CSV destination...")
        layout.addWidget(self.txt_file_path, 1)

        self.btn_browse = QPushButton("...")
        self.btn_browse.setMaximumWidth(28)
        self.btn_browse.clicked.connect(self._on_browse_file)
        layout.addWidget(self.btn_browse)

        # Poll & Cycles
        layout.addWidget(QLabel("Interval(s):"))
        self.spn_poll_interval = QDoubleSpinBox()
        self.spn_poll_interval.setRange(0.5, 10.0)
        self.spn_poll_interval.setValue(1.0)
        self.spn_poll_interval.setSingleStep(0.5)
        layout.addWidget(self.spn_poll_interval)

        layout.addWidget(QLabel("Target Cycles:"))
        self.spn_target_cycles = QSpinBox()
        self.spn_target_cycles.setRange(1, 999)
        self.spn_target_cycles.setValue(1)
        layout.addWidget(self.spn_target_cycles)

        # Action Buttons
        self.btn_auto_start = QPushButton(UIStrings.get("BTN_START_AUTO"))
        self.btn_auto_start.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 4px 12px;")
        self.btn_auto_start.clicked.connect(lambda: self.start_process(auto_cycle=True))
        layout.addWidget(self.btn_auto_start)

        self.btn_log_start = QPushButton(UIStrings.get("BTN_START_LOG"))
        self.btn_log_start.setStyleSheet("background-color: #00695c; color: white; font-weight: bold; padding: 4px 10px;")
        self.btn_log_start.clicked.connect(lambda: self.start_process(auto_cycle=False))
        layout.addWidget(self.btn_log_start)

        self.btn_stop = QPushButton(UIStrings.get("BTN_STOP"))
        self.btn_stop.setStyleSheet("background-color: #c62828; color: white; font-weight: bold; padding: 4px 12px;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_process)
        layout.addWidget(self.btn_stop)

        return frame

    def _build_left_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(6)

        # 1. Big Step Indicator Banner
        step_box = QFrame()
        step_box.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333; border-radius: 4px; padding: 6px;")
        s_layout = QHBoxLayout(step_box)
        s_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_step_name = QLabel("IDLE")
        self.lbl_step_name.setStyleSheet("font-size: 16px; font-weight: bold; color: #888888; padding: 4px 10px; background-color: #2a2a2a; border-radius: 4px;")
        s_layout.addWidget(self.lbl_step_name)

        s_layout.addStretch(1)
        s_layout.addWidget(QLabel("Step Time:"))
        self.lbl_step_time = QLabel("00:00:00")
        self.lbl_step_time.setStyleSheet("font-size: 14px; font-weight: bold; color: #00e5ff;")
        s_layout.addWidget(self.lbl_step_time)

        s_layout.addSpacing(16)
        s_layout.addWidget(QLabel("Completed Cycles:"))
        self.lbl_cycle_count = QLabel("0")
        self.lbl_cycle_count.setStyleSheet("font-size: 14px; font-weight: bold; color: #69f0ae;")
        s_layout.addWidget(self.lbl_cycle_count)
        layout.addWidget(step_box)

        # 2. Highlight Badges Bar
        flag_box = QHBoxLayout()
        flag_box.setSpacing(6)
        flag_box.addWidget(QLabel("Key Flags:"))

        self.badge_vct = QLabel("VCT")
        self.badge_rest = QLabel("REST")
        self.badge_fd = QLabel("FD")
        self.badge_fc = QLabel("FC")
        self.badge_cuv = QLabel("CUV")
        self.badge_lstatus = QLabel("Lstatus: 0x00")

        for b in [self.badge_vct, self.badge_rest, self.badge_fd, self.badge_fc, self.badge_cuv]:
            b.setStyleSheet("background-color: #32cd32; color: white; font-weight: bold; padding: 2px 6px; border-radius: 3px; font-size: 10px;")
            flag_box.addWidget(b)

        self.badge_lstatus.setStyleSheet("background-color: #424242; color: #ccc; font-weight: bold; padding: 2px 6px; border-radius: 3px; font-size: 10px;")
        flag_box.addWidget(self.badge_lstatus)
        flag_box.addStretch(1)
        layout.addLayout(flag_box)

        # 3. 14-Register Matrix Table
        self._init_status_table()
        layout.addWidget(self.table_bits, 1)

        return widget

    def _build_right_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(6)

        # Telemetry Quick Cards
        cards_box = QGroupBox("Live BQ Telemetry")
        cards_box.setStyleSheet("QGroupBox { font-weight: bold; color: #00e5ff; border: 1px solid #333333; border-radius: 4px; margin-top: 10px; padding-top: 8px; }")
        c_layout = QVBoxLayout(cards_box)

        r1 = QHBoxLayout()
        self.val_vpack = QLabel("0 mV")
        self.val_current = QLabel("0 mA")
        self.val_rsoc = QLabel("0 %")
        self.val_temp = QLabel("0.0 °C")

        for name, lbl in [("Pack Volt:", self.val_vpack), ("Current:", self.val_current), ("RSOC:", self.val_rsoc), ("Temp:", self.val_temp)]:
            sub = QVBoxLayout()
            sub.addWidget(QLabel(f"<span style='color:#888; font-size:10px;'>{name}</span>"))
            lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff;")
            sub.addWidget(lbl)
            r1.addLayout(sub)
        c_layout.addLayout(r1)

        r2 = QHBoxLayout()
        self.val_cells = QLabel("0 | 0 | 0 | 0 mV")
        self.val_cells.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffd54f;")
        r2.addWidget(QLabel("<span style='color:#888; font-size:10px;'>Cells 1~4:</span>"))
        r2.addWidget(self.val_cells)
        r2.addStretch(1)
        c_layout.addLayout(r2)
        layout.addWidget(cards_box)

        # Alarms Config Box
        alarm_box = QHBoxLayout()
        self.chk_charge_alarm = QCheckBox("Charge RSOC Max:")
        self.spn_charge_limit = QSpinBox()
        self.spn_charge_limit.setRange(1, 100)
        self.spn_charge_limit.setValue(95)

        self.chk_discharge_alarm = QCheckBox("Discharge RSOC Min:")
        self.spn_discharge_limit = QSpinBox()
        self.spn_discharge_limit.setRange(0, 99)
        self.spn_discharge_limit.setValue(5)

        alarm_box.addWidget(self.chk_charge_alarm)
        alarm_box.addWidget(self.spn_charge_limit)
        alarm_box.addSpacing(10)
        alarm_box.addWidget(self.chk_discharge_alarm)
        alarm_box.addWidget(self.spn_discharge_limit)
        alarm_box.addStretch(1)
        layout.addLayout(alarm_box)

        # Live Log Viewer
        layout.addWidget(QLabel("Activity & Event Log:"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #151515; color: #00e676; font-family: monospace; font-size: 10px; border: 1px solid #333; border-radius: 4px;")
        layout.addWidget(self.txt_log, 1)

        return widget

    def _on_browse_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select CSV Log File", "", "CSV Files (*.csv)")
        if path:
            self.txt_file_path.setText(path)

    def append_log(self, text: str):
        if hasattr(self, 'txt_log'):
            self.txt_log.append(text)
