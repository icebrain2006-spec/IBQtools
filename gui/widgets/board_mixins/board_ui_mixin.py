from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QGroupBox, QCheckBox
)
from PySide6.QtCore import Qt, QTimer

from gui.widgets.port_combo import PortComboBox
from gui.widgets.clickable_progress_bar import ClickableProgressBar
from gui.styles import Colors, Styles
from gui.strings import UIStrings
from gui.utils import get_active_usb_ports
from gui.protocol import get_file_info, get_fw_version
from gui.workers.monitor_worker import set_led_state


class BoardUiMixin:
    """Mixin for managing RP2040 Board Widget UI elements, themes, and blink timers."""

    def _setup_board_styles(self):
        """Initializes board theme colors and styles based on board ID."""
        self.led_color = Colors.BOARD_LED_COLORS[(self.board_id - 1) % 4]
        self.bg_color = Colors.BOARD_BG_COLORS[(self.board_id - 1) % 4]
        self.border_color = Colors.BOARD_BORDER_COLORS[(self.board_id - 1) % 4]

        self.setObjectName(f"board_group_{self.board_id}")
        self.default_style = Styles.get_board_group_style(self.board_id, self.bg_color, self.border_color)
        self.setStyleSheet(self.default_style)

    def _init_ui(self):
        """Constructs the Board Widget UI by assembling header and channel grid."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        lbl_title = QLabel(f"RP2040 Board {self.board_id}")
        lbl_title.setStyleSheet(Styles.BOARD_TITLE_LABEL)
        layout.addWidget(lbl_title)

        self._setup_board_styles()

        # Setup Blink Timer
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._toggle_blink)
        self.is_blink_on = False
        self.blink_duration_left = 0

        # Sub-layout assembly
        layout.addLayout(self._setup_com_header_ui())
        layout.addLayout(self._setup_channels_grid_ui())

    def _setup_com_header_ui(self) -> QHBoxLayout:
        """Single Responsibility: Construct top COM port and board control header bar."""
        com_layout = QHBoxLayout()
        com_layout.setContentsMargins(5, 0, 5, 0)

        self.btn_start_board = QPushButton("▶ " + UIStrings.get("BTN_QUICK_START", "Start"))
        self.btn_start_board.setStyleSheet(Styles.get_board_start_btn_style(self.border_color))
        self.btn_start_board.clicked.connect(lambda: self.request_start.emit(self))
        com_layout.addWidget(self.btn_start_board)

        lbl_port = QLabel(UIStrings.get("LBL_COM_PORT"))
        lbl_port.setStyleSheet(Styles.BOARD_LABEL)
        com_layout.addWidget(lbl_port)

        self.combo_port = PortComboBox()
        active_ports = get_active_usb_ports()
        self.combo_port.addItems(active_ports)

        default_port = f"COM{5 + self.board_id}"
        if default_port in active_ports:
            self.combo_port.setCurrentText(default_port)
        else:
            self.combo_port.setCurrentText("None")
        self.combo_port.currentTextChanged.connect(lambda t: self.refresh_info() if t and t != "None" else None)
        com_layout.addWidget(self.combo_port)

        self.btn_refresh = QPushButton(UIStrings.get("BTN_REFRESH"))
        self.btn_refresh.setStyleSheet(Styles.BOARD_REFRESH_BTN)
        self.btn_refresh.clicked.connect(self.refresh_info)
        com_layout.addWidget(self.btn_refresh)

        self.lbl_fw_ver = QLabel("FW: -")
        self.lbl_fw_ver.setStyleSheet(Styles.BOARD_FW_LABEL)
        com_layout.addWidget(self.lbl_fw_ver)

        self.lbl_slfs_info = QLabel("SLFS: Unknown")
        self.lbl_slfs_info.setStyleSheet(Styles.BOARD_SLFS_LABEL)
        com_layout.addWidget(self.lbl_slfs_info)

        com_layout.addStretch()
        return com_layout

    def _setup_channels_grid_ui(self) -> QGridLayout:
        """Single Responsibility: Construct the 6-channel grid UI layout."""
        channels_layout = QGridLayout()
        channels_layout.setContentsMargins(5, 0, 5, 5)
        channels_layout.setVerticalSpacing(5)
        channels_layout.setHorizontalSpacing(10)

        self.ch_checkboxes = []
        self.ch_progress = []
        self.ch_status = []

        for i in range(6):
            ch_idx = i + 1
            box = QGroupBox("")
            box.setStyleSheet(Styles.BOARD_CH_BOX)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(5, 5, 5, 5)
            box_layout.setSpacing(2)

            lbl_ch = QLabel(f"CH {ch_idx}")
            lbl_ch.setStyleSheet(Styles.BOARD_CH_TITLE)
            box_layout.addWidget(lbl_ch)

            chk = QCheckBox("Enable")
            chk.setStyleSheet("background: transparent;")
            chk.setChecked(True)
            chk.toggled.connect(lambda checked, idx=i: self._on_ch_toggled(idx, checked))
            box_layout.addWidget(chk)
            self.ch_checkboxes.append(chk)

            prog = ClickableProgressBar(ch_idx)
            prog.setValue(0)
            prog.clicked.connect(self.start_single_channel)
            box_layout.addWidget(prog)
            self.ch_progress.append(prog)

            stat = QLabel("Status: Waiting")
            stat.setStyleSheet("background: transparent;")
            stat.setWordWrap(True)
            stat.setMinimumHeight(35)
            stat.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            box_layout.addWidget(stat)
            self.ch_status.append(stat)

            row, col = divmod(i, 6)
            channels_layout.addWidget(box, row, col)

        return channels_layout

    def _on_ch_toggled(self, idx: int, checked: bool):
        """Single Responsibility: Handle channel checkbox toggle UI event."""
        if not checked:
            self.ch_progress[idx].setValue(0)
            self.ch_status[idx].setText("Status: Disabled")
            self.ch_status[idx].setStyleSheet("color: #555555;")
        else:
            self.ch_status[idx].setText("Status: Waiting")
            self.ch_status[idx].setStyleSheet("color: #AAAAAA;")

    def refresh_info(self):
        """Single Responsibility: Refresh connected board FW version and SLFS metadata."""
        port = self.combo_port.currentText().strip()
        if not port or port == "None":
            self.lbl_slfs_info.setText("SLFS: Unknown")
            self.lbl_fw_ver.setText("FW: -")
            return

        was_monitoring = False
        if hasattr(self, 'disconnect_monitor') and self.disconnect_monitor and self.disconnect_monitor.isRunning():
            was_monitoring = True
            self.disconnect_monitor.stop()
            self.disconnect_monitor.wait(800)

        file_info = get_file_info(port)

        fname = None
        ic_type = ""
        version = ""

        if file_info:
            if isinstance(file_info, tuple) and len(file_info) == 3:
                fname, ic_type, version = file_info
            else:
                fname = file_info
            self.lbl_slfs_info.setText(f"SLFS: {fname}")
        else:
            self.lbl_slfs_info.setText("SLFS: Not Connected / Error")

        fw_ver = get_fw_version(port)
        if fw_ver:
            if ic_type and version:
                self.lbl_fw_ver.setText(f"FW: {fw_ver}   (IC: {ic_type} | Ver: {version})")
            else:
                self.lbl_fw_ver.setText(f"FW: {fw_ver}")
        else:
            self.lbl_fw_ver.setText("FW: -")

        if fname and fw_ver:
            set_led_state(port, self.led_color, 0, 0)

        if was_monitoring and hasattr(self, 'passed_channels') and self.passed_channels:
            if hasattr(self, '_start_disconnection_monitor_if_needed'):
                self._start_disconnection_monitor_if_needed(port)

    def start_blink(self, duration_sec: int):
        """Triggers UI groupbox blinking animation."""
        self.blink_duration_left = duration_sec * 2
        self.is_blink_on = False
        self.blink_timer.start(500)

    def _toggle_blink(self):
        """Toggles border style during blink animation."""
        if self.blink_duration_left <= 0:
            self.blink_timer.stop()
            self.setStyleSheet(self.default_style)
            return

        self.blink_duration_left -= 1
        self.is_blink_on = not self.is_blink_on

        if self.is_blink_on:
            self.setStyleSheet(f"QGroupBox#board_group_{self.board_id} {{ background-color: transparent; border: 1px solid {Colors.HEX_BORDER_LIGHT}; border-radius: 5px; margin-top: 2px; }}")
        else:
            self.setStyleSheet(self.default_style)
