import os
import csv
import datetime
import threading
import logging
import time
import winsound
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QGridLayout, QLabel, QComboBox, QLineEdit, 
                               QPushButton, QTextBrowser, QCheckBox, QSpinBox, 
                               QProgressBar, QFormLayout, QMessageBox, QScrollArea)
from PySide6.QtCore import Qt, Signal, QRegularExpression, QTimer
from PySide6.QtGui import QRegularExpressionValidator

from updater_thread import UpdaterWorker, SerialCheckWorker, get_file_info, get_fw_version, set_led_state, DisconnectionMonitor
from config import config

class ClickableProgressBar(QProgressBar):
    clicked = Signal(int)
    
    def __init__(self, ch_idx, parent=None):
        super().__init__(parent)
        self.ch_idx = ch_idx
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ch_idx)
        super().mousePressEvent(event)

from widgets import PortComboBox
from styles import Colors, Styles
from utils import append_work_log


class RP2040BoardWidget(QGroupBox):
    board_finished = Signal()
    request_start = Signal(object) # Emit self when clicked
    
    def __init__(self, board_id, log_callback, get_expected_cb, cache_values_cb, parent=None):
        super().__init__("", parent)
        self.board_id = board_id
        self.log_callback = log_callback # Function to send logs to central console
        self.get_expected_cb = get_expected_cb
        self.cache_values_cb = cache_values_cb
        self.worker = None
        self.disconnect_monitor = None
        self.passed_channels = set()
        self.expected_sn_map = {}
        self.expected_date_map = {}
        self.expected_fmt = "DEC"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        lbl_title = QLabel(f"RP2040 Board {board_id}")
        lbl_title.setStyleSheet(Styles.BOARD_TITLE_LABEL)
        layout.addWidget(lbl_title)
        
        # Board LED Colors: Cyan(1), Green(2), Magenta(3), Yellow(4)
        self.led_color = Colors.BOARD_LED_COLORS[(self.board_id - 1) % 4]
        self.bg_color = Colors.BOARD_BG_COLORS[(self.board_id - 1) % 4]
        self.border_color = Colors.BOARD_BORDER_COLORS[(self.board_id - 1) % 4]
        
        self.setObjectName(f"board_group_{self.board_id}")
        self.default_style = Styles.get_board_group_style(self.board_id, self.bg_color, self.border_color)
        self.setStyleSheet(self.default_style)
        
        # Blink Timer for UI
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._toggle_blink)
        self.is_blink_on = False
        self.blink_duration_left = 0
        
        # COM Port Selection Row
        com_layout = QHBoxLayout()
        com_layout.setContentsMargins(5, 0, 5, 0)
        
        self.btn_start_board = QPushButton("▶ Start")
        self.btn_start_board.setStyleSheet(Styles.get_board_start_btn_style(self.border_color))
        self.btn_start_board.clicked.connect(lambda: self.request_start.emit(self))
        com_layout.addWidget(self.btn_start_board)
        
        lbl_port = QLabel("COM Port:")
        lbl_port.setStyleSheet(Styles.BOARD_LABEL)
        com_layout.addWidget(lbl_port)
        
        self.combo_port = PortComboBox()
        # Initial population of ports
        import serial.tools.list_ports
        active_ports = ["None"]
        for p in serial.tools.list_ports.comports():
            hwid = str(p.hwid).upper()
            desc = str(p.description).upper()
            if "BTHENUM" in hwid or "BLUETOOTH" in desc or "BTHENUM" in desc: continue
            if "USB" not in hwid and "USB" not in desc: continue
            active_ports.append(p.device)
            
        self.combo_port.addItems(active_ports)
            
        # Try to select the default based on board_id if it exists, otherwise just pick the first one
        default_port = f"COM{5 + board_id}"
        if default_port in active_ports:
            self.combo_port.setCurrentText(default_port)
        else:
            self.combo_port.setCurrentText("None")
            
        com_layout.addWidget(self.combo_port)
        
        self.btn_refresh = QPushButton("Refresh")
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
        layout.addLayout(com_layout)
        
        # 6 Channels Grid
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
            self.ch_checkboxes.append(chk)
            
            prog = ClickableProgressBar(ch_idx)
            prog.setValue(0)
            prog.clicked.connect(self.start_single_channel)
            self.ch_progress.append(prog)
            
            stat = QLabel("Status: Waiting")
            stat.setStyleSheet("background: transparent;")
            stat.setWordWrap(True)
            stat.setMinimumHeight(35)
            stat.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.ch_status.append(stat)
            
            box_layout.addWidget(chk)
            box_layout.addWidget(prog)
            box_layout.addWidget(stat)
            
            row, col = divmod(i, 6)
            channels_layout.addWidget(box, row, col)
            
        layout.addLayout(channels_layout)

    def _on_ch_toggled(self, idx, checked):
        if not checked:
            self.ch_progress[idx].setValue(0)
            self.ch_status[idx].setText("Status: Disabled")
            self.ch_status[idx].setStyleSheet(f"color: {Colors.HEX_TEXT_DISABLED};")
        else:
            self.ch_status[idx].setText("Status: Waiting")
            self.ch_status[idx].setStyleSheet(f"color: {Colors.HEX_TEXT_MUTED};")


    def refresh_info(self):
        port = self.combo_port.currentText()
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
            # Set LED to normal state (Solid)
            set_led_state(port, self.led_color, 0, 0)

    def start_blink(self, duration_sec):
        self.blink_duration_left = duration_sec * 2 # 500ms intervals
        self.is_blink_on = False
        self.blink_timer.start(500)
        
    def _toggle_blink(self):
        if self.blink_duration_left <= 0:
            self.blink_timer.stop()
            self.setStyleSheet(self.default_style)
            return
            
        self.blink_duration_left -= 1
        self.is_blink_on = not self.is_blink_on
        
        if self.is_blink_on:
            self.setStyleSheet(f"QGroupBox#board_group_{self.board_id} {{ background-color: transparent; border: 1px solid #444; border-radius: 5px; margin-top: 2px; }}")
        else:
            self.setStyleSheet(self.default_style)

    def start_worker(self, loop_count, skip_preflight=False):
        if self.disconnect_monitor and self.disconnect_monitor.isRunning():
            self.disconnect_monitor.stop()
            self.disconnect_monitor.wait(500)
        self.passed_channels.clear()
            
        active_channels = []
        for i, chk in enumerate(self.ch_checkboxes):
            if chk.isChecked():
                active_channels.append(i + 1)
                
        if not active_channels:
            self.log_callback(f"[Board {self.board_id}] No channels selected. Skipping.")
            return False
            
        if self.cache_values_cb:
            self.cache_values_cb()
            
        port = self.combo_port.currentText()
        
        for chk in self.ch_checkboxes:
            chk.setEnabled(False)
            
        for i in range(6):
            if (i+1) in active_channels:
                self.ch_progress[i].setValue(0)
                self.ch_status[i].setText("Status: Starting...")
                self.ch_status[i].setStyleSheet("color: #AAAAAA;")
            else:
                self.ch_status[i].setText("Status: Disabled")
                self.ch_status[i].setStyleSheet("color: #555555;")
                
        self.btn_start_board.setEnabled(False)
        self.combo_port.setEnabled(False)
        self.btn_refresh.setEnabled(False)
        
        self.log_callback(f"[Board {self.board_id}] Initializing thread on {port}...")
        self.expected_sn_map.clear()
        self.expected_date_map.clear()
        
        self.worker = UpdaterWorker(port, active_channels, loop_count=loop_count, get_expected_cb=self._get_sn_for_worker, skip_preflight=skip_preflight)
        self.worker.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id}] {msg}"))
        self.worker.progress_updated.connect(self._on_progress_update)
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.verify_updated.connect(self._on_verify_update)
        self.worker.finished.connect(self._on_worker_finished)
        
        self.worker.start()
        return True

    def start_single_channel(self, ch_idx):
        if self.worker and self.worker.isRunning():
            self.log_callback(f"[Board {self.board_id}] Worker is already running. Please stop it first.")
            return
            
        if self.passed_channels and ch_idx in self.passed_channels:
            self.log_callback(f"[Board {self.board_id} CH {ch_idx}] Channel is in PASS state. Swap to unlock.")
            return

        if self.disconnect_monitor and self.disconnect_monitor.isRunning():
            # 특정 채널만 다시 시작할 때 모니터가 돌고 있으면 충돌 방지를 위해 모니터 중지
            self.disconnect_monitor.stop()
            self.disconnect_monitor.wait(500)
        self.passed_channels.discard(ch_idx)
            
        self.refresh_info()
        if "Unknown" in self.lbl_slfs_info.text() or "Error" in self.lbl_slfs_info.text():
            QMessageBox.warning(self, "SLFS Check", f"Board {self.board_id}: SLFS file not found! Please check the connection or upload the SLFS file first.")
            return
            
        if self.cache_values_cb:
            self.cache_values_cb()
            
        port = self.combo_port.currentText()
        
        for chk in self.ch_checkboxes:
            chk.setEnabled(False)
            
        self.ch_progress[ch_idx - 1].setValue(0)
        self.ch_status[ch_idx - 1].setText("Status: Starting...")
        
        self.btn_start_board.setEnabled(False)
        self.combo_port.setEnabled(False)
        self.btn_refresh.setEnabled(False)
        
        self.log_callback(f"[Board {self.board_id}] Initializing SINGLE update for CH {ch_idx} on {port}...")
        self.expected_sn_map.clear()
        self.expected_date_map.clear()
        
        self.worker = UpdaterWorker(port, [ch_idx], loop_count=1, get_expected_cb=self._get_sn_for_worker, skip_preflight=False)
        self.worker.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id}] {msg}"))
        self.worker.progress_updated.connect(self._on_progress_update)
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.verify_updated.connect(self._on_verify_update)
        self.worker.finished.connect(self._on_worker_finished)
        
        self.worker.start()

    def stop_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()

    def check_serial(self):
        if self.worker and self.worker.isRunning():
            self.log_callback(f"[Board {self.board_id}] Worker is running. Please stop it first.")
            return

        if self.cache_values_cb:
            self.cache_values_cb()

        active_channels = []
        for i, chk in enumerate(self.ch_checkboxes):
            if chk.isChecked():
                active_channels.append(i + 1)
                
        if not active_channels:
            self.log_callback(f"[Board {self.board_id}] No channels selected. Skipping.")
            return
            
        port = self.combo_port.currentText()
        
        for chk in self.ch_checkboxes:
            chk.setEnabled(False)
            
        for i in range(6):
            if (i+1) in active_channels:
                self.ch_progress[i].setValue(0)
                self.ch_status[i].setText("Status: Starting Read...")
                self.ch_status[i].setStyleSheet("color: #AAAAAA;")
            else:
                self.ch_status[i].setText("Status: Disabled")
                self.ch_status[i].setStyleSheet("color: #555555;")
                
        _, _, fmt, _, _ = self.get_expected_cb(False)
        self.worker = SerialCheckWorker(port, active_channels, fmt=fmt)
        self.worker.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id}] {msg}"))
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _get_sn_for_worker(self, ch_idx):
        exp_date, sn_int, fmt, should_write_sn, should_write_date = self.get_expected_cb(True)
        if should_write_sn or should_write_date:
            self.expected_date_map[ch_idx] = exp_date
            self.expected_sn_map[ch_idx] = sn_int
            self.expected_fmt = fmt
            return exp_date, sn_int, fmt, should_write_sn, should_write_date
        else:
            if ch_idx in self.expected_sn_map:
                exp_date = self.expected_date_map[ch_idx]
                exp_sn_int = self.expected_sn_map[ch_idx]
                sn_fmt = self.expected_fmt
                _, _, _, should_write_sn, should_write_date = self.get_expected_cb(False)
            else:
                exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date = self.get_expected_cb(False)
            
            return exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date

    def _on_progress_update(self, ch_idx, percent):
        if 1 <= ch_idx <= 6:
            self.ch_progress[ch_idx - 1].setValue(percent)
            
    def _on_status_update(self, ch_idx, status_text):
        if 1 <= ch_idx <= 6:
            lower_text = status_text.lower()
            if "error" in lower_text or "fail" in lower_text or "오류" in lower_text:
                self.ch_status[ch_idx - 1].setText(f'Status: <span style="color: {Colors.HEX_FAIL};">{status_text}</span>')
            else:
                self.ch_status[ch_idx - 1].setText(f"Status: {status_text}")
            self.ch_status[ch_idx - 1].setStyleSheet("") # Reset style

    def _resolve_expected_targets(self, ch_idx: int):
        """Resolves target expected values for a given channel."""
        if ch_idx in self.expected_sn_map:
            exp_date = self.expected_date_map[ch_idx]
            exp_sn_int = self.expected_sn_map[ch_idx]
            sn_fmt = self.expected_fmt
            _, _, _, should_write_sn, should_write_date = self.get_expected_cb(False)
        else:
            exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date = self.get_expected_cb(False)
        return exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date

    def _evaluate_verification(self, exp_date: str, exp_sn_int: int, sn_fmt: str, date_str: str, sn_int: int, should_write_date: bool, should_write_sn: bool):
        """Evaluates verification logic (Pure Logic) and returns (result_str, formatted_sn_str)."""
        if not date_str or sn_int < 0:
            return "ERROR", "N/A"

        if sn_fmt == "HEX":
            sn_str = f"0x{sn_int:04X}"
            actual_sn_int = sn_int
        else:
            try:
                actual_sn_int = int(f"{sn_int:X}", 10)
                sn_str = str(actual_sn_int)
            except ValueError:
                actual_sn_int = sn_int
                sn_str = f"INVALID_BCD_0x{sn_int:04X}"

        date_match = (date_str == exp_date) if should_write_date else True
        sn_match = (actual_sn_int == exp_sn_int) if should_write_sn else True

        result_str = "PASS" if (date_match and sn_match) else "FAIL"
        return result_str, sn_str

    def _update_channel_verify_ui(self, ch_idx: int, result_str: str, date_str: str, sn_str: str):
        """Updates the status label and QSS stylesheet for the specified channel."""
        if result_str == "ERROR":
            current_text = self.ch_status[ch_idx - 1].text().lower()
            if not ("error" in current_text or "fail" in current_text or "오류" in current_text):
                self.ch_status[ch_idx - 1].setText("Verify: ERROR")
                self.ch_status[ch_idx - 1].setStyleSheet(f"color: {Colors.HEX_FAIL}; font-weight: bold;")
        elif result_str == "PASS":
            self.ch_status[ch_idx - 1].setText(f"PASS (M:{date_str} SN:{sn_str})")
            self.ch_status[ch_idx - 1].setStyleSheet(f"color: {Colors.HEX_PASS_GREEN}; font-weight: bold;")
            self.passed_channels.add(ch_idx)
        else:
            self.ch_status[ch_idx - 1].setText(f"FAIL (M:{date_str} SN:{sn_str})")
            self.ch_status[ch_idx - 1].setStyleSheet(f"color: {Colors.HEX_FAIL}; font-weight: bold;")

    def _on_verify_update(self, ch_idx, date_str, sn_int):
        """Orchestrates verification update: target resolution, evaluation, UI update, and CSV logging."""
        if not (1 <= ch_idx <= 6):
            return

        exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date = self._resolve_expected_targets(ch_idx)
        should_write = should_write_sn or should_write_date

        result_str, sn_str = self._evaluate_verification(
            exp_date, exp_sn_int, sn_fmt, date_str, sn_int, should_write_date, should_write_sn
        )

        self._update_channel_verify_ui(ch_idx, result_str, date_str, sn_str)

        # File I/O via isolated utility (AGENTS.md Compliance)
        slfs_file = self.lbl_slfs_info.text().replace("SLFS: ", "")
        wrote_sn = "Yes" if should_write else "No"
        if sn_int >= 0:
            ch_sn_str = f"0x{sn_int:04X}" if sn_fmt == "HEX" else str(sn_int)
        else:
            ch_sn_str = "N/A"

        append_work_log(config.get_work_log_path(), self.board_id, ch_idx, slfs_file, wrote_sn, date_str, ch_sn_str, result_str)

    def _restore_board_ui_controls(self):
        """Restores interactive UI controls after worker thread finishes."""
        self.combo_port.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        for chk in self.ch_checkboxes:
            chk.setEnabled(True)

    def _apply_finish_notifications(self, success: bool, port: str):
        """Applies hardware LED states and GUI blink notifications based on worker outcome."""
        if success:
            set_led_state(port, self.led_color, 0, 0)  # Normal Solid
        else:
            set_led_state(port, self.led_color, 1, 10)  # Error Blink for 10s
            self.start_blink(10)  # Blink GUI background as well

    def _start_disconnection_monitor_if_needed(self, port: str):
        """Launches the DisconnectionMonitor if passed channels exist; enables start button otherwise."""
        if self.passed_channels:
            self.btn_start_board.setEnabled(False)
            self.disconnect_monitor = DisconnectionMonitor(port, self.passed_channels)
            self.disconnect_monitor.channel_disconnected.connect(self._on_channel_disconnected)
            self.disconnect_monitor.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id} MON] {msg}"))
            self.disconnect_monitor.start()
        else:
            self.btn_start_board.setEnabled(True)

    def _on_worker_finished(self, success):
        """Orchestrates worker finish logic: UI restoration, LED notification, signals, and disconnection monitoring."""
        self._restore_board_ui_controls()

        port = self.combo_port.currentText().strip()
        self._apply_finish_notifications(success, port)

        self.log_callback(f"[Board {self.board_id}] Thread finished.")
        self.board_finished.emit()

        self._start_disconnection_monitor_if_needed(port)


    def _on_channel_disconnected(self, ch_idx):
        # UI 상태를 대기(Waiting)로 초기화
        if 1 <= ch_idx <= 6:
            self.ch_progress[ch_idx - 1].setValue(0)
            self.ch_status[ch_idx - 1].setText("Status: Waiting (Swapped)")
            self.ch_status[ch_idx - 1].setStyleSheet(f"color: {Colors.HEX_TEXT_MUTED};")
            self.passed_channels.discard(ch_idx)

            
            # 모든 채널이 교체 완료되면 시작 버튼 다시 활성화
            if not self.passed_channels:
                self.btn_start_board.setEnabled(True)


class SNCheckerTab(QWidget):
    update_sn_ui_signal = Signal(str)


    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.boards = []
        self.active_workers = 0
        self.sn_lock = threading.Lock()
        
        self.cached_exp_date = ""
        self.cached_fmt = "DEC"
        self.cached_should_write = False
        self.cached_should_inc = False
        self.cached_sn_int = 0
        
        self.update_sn_ui_signal.connect(self._safe_update_sn_ui)
        self._init_ui()
        
    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        # --- LEFT PANEL (Master Control & Log) ---
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0,0,0,0)
        
        master_group = QGroupBox("Master Configuration")
        mlayout = QGridLayout(master_group)
        
        mlayout.addWidget(QLabel("Number of Boards (1-4):"), 0, 0)
        self.spin_boards = QSpinBox()
        self.spin_boards.setRange(1, 4)
        self.spin_boards.setValue(1)
        self.spin_boards.valueChanged.connect(self._update_board_count)
        mlayout.addWidget(self.spin_boards, 0, 1)
        
        mlayout.addWidget(QLabel("Loop Count:"), 1, 0)
        self.loop_count = QLineEdit("1")
        mlayout.addWidget(self.loop_count, 1, 1)
        
        verify_group = QGroupBox("Verification Targets")
        verify_form = QFormLayout(verify_group)
        self.input_exp_date = QLineEdit("2024-03-05")
        self.input_exp_date.setInputMask("9999-99-99")
        
        self.chk_write_date = QCheckBox("Write Date to Chip")
        
        date_layout = QHBoxLayout()
        date_layout.addWidget(self.input_exp_date)
        date_layout.addWidget(self.chk_write_date)
        
        chk_layout = QHBoxLayout()
        self.chk_write_sn = QCheckBox("Write SN to Chip")
        self.chk_auto_inc = QCheckBox("Auto Increment (+1)")
        self.chk_auto_inc.setEnabled(False)
        self.chk_write_sn.toggled.connect(self.chk_auto_inc.setEnabled)
        chk_layout.addWidget(self.chk_write_sn)
        chk_layout.addWidget(self.chk_auto_inc)
        verify_form.addRow("SN Options:", chk_layout)
        
        sn_layout = QHBoxLayout()
        self.combo_sn_fmt = QComboBox()
        self.combo_sn_fmt.addItems(["DEC", "HEX"])
        self.input_exp_sn = QLineEdit("1")
        
        self.val_dec = QRegularExpressionValidator(QRegularExpression(r"^[0-9]{1,4}$"))
        self.val_hex = QRegularExpressionValidator(QRegularExpression(r"^[0-9A-Fa-f]{1,4}$"))
        self.input_exp_sn.setValidator(self.val_dec)
        
        def _on_sn_fmt_changed(fmt):
            if fmt == "DEC":
                self.input_exp_sn.setValidator(self.val_dec)
                try:
                    val = int(self.input_exp_sn.text() or "0", 16)
                    if val > 9999: val = 9999
                    self.input_exp_sn.setText(str(val))
                except ValueError:
                    self.input_exp_sn.setText("0")
            else:
                self.input_exp_sn.setValidator(self.val_hex)
                try:
                    val = int(self.input_exp_sn.text() or "0")
                    self.input_exp_sn.setText(f"{val:X}")
                except ValueError:
                    self.input_exp_sn.setText("0")
                    
        self.combo_sn_fmt.currentTextChanged.connect(_on_sn_fmt_changed)
        
        sn_layout.addWidget(self.combo_sn_fmt)
        sn_layout.addWidget(self.input_exp_sn)
        
        verify_form.addRow("Expected Date:", date_layout)
        verify_form.addRow("Start SN:", sn_layout)
        left_layout.addWidget(master_group)
        left_layout.addWidget(verify_group)
        
        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_start = QPushButton("START ALL")
        self.btn_start.setObjectName("startBtn")
        self.btn_stop = QPushButton("STOP ALL")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setEnabled(False)
        
        self.btn_quick_start = QPushButton("Quick Start")
        self.btn_quick_start.setCheckable(True)
        self.btn_quick_start.setStyleSheet(Styles.QUICK_START_BTN)
        self.btn_quick_start.setToolTip("Enable this to trigger 'START ALL' using the configured hotkey")
        
        self.btn_start.clicked.connect(self._start_all)
        self.btn_stop.clicked.connect(self._stop_all)
        
        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_stop)
        action_layout.addWidget(self.btn_quick_start)
        
        left_layout.addLayout(action_layout)
        
        self.btn_check_all = QPushButton("SERIAL CHECK")
        self.btn_check_all.setObjectName("checkBtn")
        self.btn_check_all.clicked.connect(self._check_all)
        left_layout.addWidget(self.btn_check_all)
        
        # Log Console
        self.log_console = QTextBrowser()
        self.log_console.setStyleSheet(Styles.LOG_CONSOLE)
        self.log_console.append("Welcome to Multi-Board BQ40Z50 Updater GUI.")

        left_layout.addWidget(self.log_console, stretch=1)
        
        layout.addWidget(left_panel)
        
        # --- RIGHT PANEL (Scroll Area with Boards) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("boardScroll")
        
        self.scroll_content = QWidget()
        self.boards_layout = QVBoxLayout(self.scroll_content)
        self.boards_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        
        layout.addWidget(self.scroll_area, stretch=1)
        
        # Initialize board widgets
        self._update_board_count(1)

    def is_hotkey_ready(self):
        return hasattr(self, 'btn_quick_start') and self.btn_quick_start.isChecked()
        
    def trigger_start_all(self):
        if self.btn_start.isEnabled():
            self.btn_start.click()

    def _update_board_count(self, count):
        for board in self.boards:
            self.boards_layout.removeWidget(board)
            board.deleteLater()
        self.boards.clear()
        
        for i in range(count):
            board = RP2040BoardWidget(i + 1, self._log_to_console, self._get_expected_values, self._cache_values_if_needed)
            board.board_finished.connect(self._on_board_finished_callback)
            board.request_start.connect(self._start_single_board)
            board.combo_port.currentTextChanged.connect(self._on_port_changed)
            self.boards_layout.addWidget(board)
            self.boards.append(board)

    def _on_port_changed(self, text):
        if text == "None":
            return
            
        sender_combo = self.sender()
        if not sender_combo: return
        
        for board in self.boards:
            if board.combo_port != sender_combo and board.combo_port.currentText() == text:
                board.combo_port.blockSignals(True)
                board.combo_port.setCurrentText("None")
                board.combo_port.blockSignals(False)

    def _start_single_board(self, board_widget):
        if board_widget.worker and board_widget.worker.isRunning():
            self._log_to_console(f"Board {board_widget.board_id} is already running.")
            return
            
        try:
            loops = int(self.loop_count.text())
        except ValueError:
            loops = 1
            
        if self.active_workers == 0:
            self.start_time = time.time()
            self._cache_values_if_needed()
            self.log_console.append(f"\n[SYS] STARTING BOARD {board_widget.board_id}...")
        else:
            self.log_console.append(f"[SYS] STARTING BOARD {board_widget.board_id} (Parallel)...")
            
        if board_widget.start_worker(loops):
            self.active_workers += 1
            self._set_master_ui_enabled(False)

    def _safe_update_sn_ui(self, sn_str):
        self.input_exp_sn.setText(sn_str)

    def _cache_values_if_needed(self):
        with self.sn_lock:
            if self.active_workers == 0:
                self.cached_exp_date = self.input_exp_date.text().strip()
                self.cached_should_write_date = self.chk_write_date.isChecked()
                self.cached_fmt = self.combo_sn_fmt.currentText()
                self.cached_should_write = self.chk_write_sn.isChecked()
                self.cached_should_inc = self.chk_auto_inc.isChecked()
                sn_text = self.input_exp_sn.text().strip() or "0"
                self.cached_sn_int = int(sn_text, 16) if self.cached_fmt == "HEX" else int(sn_text)

    def _increment_and_format_sn(self, fmt: str) -> tuple[int, str]:
        """Increments cached SN, applies format overflow boundary checks, and returns updated int and formatted string."""
        self.cached_sn_int += 1
        if fmt == "DEC" and self.cached_sn_int > 9999:
            self.cached_sn_int = 0
        elif fmt == "HEX" and self.cached_sn_int > 65535:
            self.cached_sn_int = 0

        formatted_sn = f"{self.cached_sn_int:X}" if fmt == "HEX" else str(self.cached_sn_int)
        return self.cached_sn_int, formatted_sn

    def _get_expected_values(self, is_writing=False):
        """Resolves cached target expected values and increments SN if writing with auto-increment enabled."""
        with self.sn_lock:
            exp_date = self.cached_exp_date
            fmt = self.cached_fmt
            should_write_sn = self.cached_should_write
            should_write_date = getattr(self, 'cached_should_write_date', False)
            should_inc = self.cached_should_inc
            chip_sn_int = self.cached_sn_int

            if is_writing and should_write_sn and should_inc:
                _, formatted_sn_str = self._increment_and_format_sn(fmt)
                self.update_sn_ui_signal.emit(formatted_sn_str)

            return exp_date, chip_sn_int, fmt, should_write_sn, should_write_date


    def _check_any_board_has_error(self) -> bool:
        """Iterates over all boards and channels to check if any channel has a failure/error status."""
        for board in self.boards:
            for stat in board.ch_status:
                text = stat.text().lower()
                if "fail" in text or "error" in text or "오류" in text:
                    return True
        return False

    def _play_completion_sound(self, is_error: bool):
        """Launches a daemon thread to play completion/failure sound or fallback beeps."""
        def _play_sound(is_err):
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                ref_dir = os.path.join(base_dir, "assets", "wav")
                wav_name = "testFail.wav" if is_err else "testComplete.wav"
                wav_path = os.path.join(ref_dir, wav_name)

                if os.path.exists(wav_path):
                    winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                else:
                    if is_err:
                        winsound.Beep(350, 80)
                        time.sleep(0.03)
                        winsound.Beep(350, 80)
                    else:
                        winsound.Beep(880, 80)
                        winsound.Beep(1046, 80)
                        winsound.Beep(1318, 150)
            except Exception:
                pass

        threading.Thread(target=_play_sound, args=(is_error,), daemon=True).start()

    def _on_board_finished_callback(self):
        """Orchestrates board completion: worker counting, error checking, sound playback, and UI restoration."""
        self.active_workers -= 1
        if self.active_workers > 0:
            return

        self.active_workers = 0
        has_error = self._check_any_board_has_error()
        self._play_completion_sound(has_error)

        if hasattr(self, 'start_time'):
            elapsed = time.time() - self.start_time
            self._log_to_console(f"\n[SYS] ALL BOARDS FINISHED. Total Time: {elapsed:.2f} seconds")

        self._set_master_ui_enabled(True)


    def _log_to_console(self, msg):
        lower_msg = msg.lower()
        is_error = "error" in lower_msg or "fail" in lower_msg or "오류" in lower_msg
        
        from config import config
        if config.settings.value("global_debug_log_en", "false") != "true":
            # If debug log is off, allow error, system, finished messages
            if not is_error and "[sys]" not in lower_msg and "finished" not in lower_msg:
                return
                
        # To prevent Qt from bleeding the HTML span color into subsequent plain-text lines,
        # we explicitly set the color for normal messages as well.
        safe_msg = msg.replace("<", "&lt;").replace(">", "&gt;")
        if is_error:
            # Wrap with red span for errors
            self.log_console.append(f'<span style="color: {Colors.HEX_FAIL};">{safe_msg}</span>')
        else:
            self.log_console.append(f'<span style="color: {Colors.HEX_PASS_GREEN};">{safe_msg}</span>')

    def _check_all(self):
        if self.active_workers > 0:
            self._log_to_console("Workers are already running. Stop them first.")
            return
            
        self.cached_fmt = self.combo_sn_fmt.currentText()
            
        started = 0
        for board in self.boards:
            if board.disconnect_monitor and board.disconnect_monitor.isRunning():
                board.disconnect_monitor.stop()
                board.disconnect_monitor.wait(500)
            board.passed_channels.clear()
            board.check_serial()
            if hasattr(board, 'worker') and board.worker and board.worker.isRunning():
                started += 1
                
        self.active_workers = started
        if started == 0:
            self._log_to_console("No boards were started for check.")

    def _start_all(self):
        try:
            self.loops = int(self.loop_count.text())
        except ValueError:
            self.loops = 1
            
        self._set_master_ui_enabled(False)
        
        self.log_console.append(f"\n[SYS] STARTING ALL {len(self.boards)} BOARDS...")
        
        board_configs = []
        for board in self.boards:
            if board.disconnect_monitor and board.disconnect_monitor.isRunning():
                board.disconnect_monitor.stop()
                board.disconnect_monitor.wait(500)
            board.passed_channels.clear()

            port = board.combo_port.currentText().strip()
            channels = [i + 1 for i, chk in enumerate(board.ch_checkboxes) if chk.isChecked()]
            if channels:
                board_configs.append({
                    'board_id': board.board_id,
                    'port': port,
                    'channels': channels
                })
                
        if not board_configs:
            self.log_console.append("[SYS] No channels were enabled across any boards.")
            self._set_master_ui_enabled(True)
            return
            
        from updater_thread import GlobalPreflightWorker
        self.preflight_worker = GlobalPreflightWorker(board_configs)
        self.preflight_worker.log_msg.connect(self._log_to_console)
        self.preflight_worker.finished_check.connect(self._on_global_preflight_finished)
        self.preflight_worker.start()

    def _handle_preflight_failure_ui(self, all_errors: dict):
        """Updates board UI labels, stylesheets, and hardware LED states when preflight check fails."""
        for board in self.boards:
            b_id = board.board_id
            error_channels = all_errors.get(b_id, [])

            has_error = False
            for i, stat in enumerate(board.ch_status):
                if not board.ch_checkboxes[i].isChecked():
                    continue

                ch_idx = i + 1
                if ch_idx in error_channels:
                    stat.setText("SMBus Error")
                    stat.setStyleSheet(f"color: {Colors.HEX_FAIL}; font-weight: bold;")
                    has_error = True
                else:
                    stat.setText("Preflight OK (Aborted)")
                    stat.setStyleSheet(f"color: {Colors.HEX_WARN_CYAN}; font-weight: bold;")

            port = board.combo_port.currentText().strip()
            if has_error:
                set_led_state(port, board.led_color, 1, 10)  # Error Blink for 10s
                board.start_blink(10)
            else:
                set_led_state(port, board.led_color, 0, 0)  # Normal Solid

    def _launch_all_board_workers(self) -> int:
        """Launches main workers across all boards with skip_preflight=True and returns launched worker count."""
        active_count = 0
        self.start_time = time.time()
        for board in self.boards:
            if board.start_worker(self.loops, skip_preflight=True):
                active_count += 1
        return active_count

    def _on_global_preflight_finished(self, success, all_errors):
        """Orchestrates preflight outcome: failure handling or launching board workers."""
        if not success:
            self.log_console.append(f'<span style="color: {Colors.HEX_FAIL};">[SYS] START ALL Aborted due to pre-flight failure.</span>')
            self._handle_preflight_failure_ui(all_errors)
            self._set_master_ui_enabled(True)
            self._play_completion_sound(is_error=True)
            return

        try:
            self.active_workers = self._launch_all_board_workers()
            if self.active_workers == 0:
                self._log_to_console("[SYS] Failed to launch workers.")
                self._set_master_ui_enabled(True)
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            self.log_console.append(f'<span style="color: {Colors.HEX_FAIL};">[EXCEPTION] {err_str}</span>')



    def _stop_all(self):
        self.log_console.append("\n[SYS] STOP ALL REQUESTED...")
        for board in self.boards:
            board.stop_worker()
        self._set_master_ui_enabled(True)

    def _set_master_ui_enabled(self, enabled):
        self.btn_start.setEnabled(enabled)
        self.btn_stop.setEnabled(not enabled)
        self.spin_boards.setEnabled(enabled)
        self.loop_count.setEnabled(enabled)
        self.input_exp_date.setEnabled(enabled)
        self.chk_write_date.setEnabled(enabled)
        self.combo_sn_fmt.setEnabled(enabled)
        self.input_exp_sn.setEnabled(enabled)
        self.chk_write_sn.setEnabled(enabled)
        self.btn_check_all.setEnabled(enabled)
        self.btn_quick_start.setEnabled(enabled)
        
        if enabled:
            self.chk_auto_inc.setEnabled(self.chk_write_sn.isChecked())
        else:
            self.chk_auto_inc.setEnabled(False)

    def save_ui_states(self):
        settings = config.settings
        settings.setValue("ui_boards", self.spin_boards.value())
        settings.setValue("ui_loop_count", self.loop_count.text())
        settings.setValue("ui_exp_date", self.input_exp_date.text())
        settings.setValue("ui_write_date", self.chk_write_date.isChecked())
        settings.setValue("ui_sn_fmt", self.combo_sn_fmt.currentText())
        settings.setValue("ui_exp_sn", self.input_exp_sn.text())
        settings.setValue("ui_write_sn", self.chk_write_sn.isChecked())
        settings.setValue("ui_auto_inc", self.chk_auto_inc.isChecked())
        
        for board in self.boards:
            bid = board.board_id
            settings.setValue(f"ui_board_{bid}_port", board.combo_port.currentText())
            for i, chk in enumerate(board.ch_checkboxes):
                settings.setValue(f"ui_board_{bid}_ch_{i+1}", chk.isChecked())
                
    def load_ui_states(self):
        settings = config.settings
        try:
            boards_count = int(settings.value("ui_boards", 1))
            self.spin_boards.setValue(boards_count)
            self.loop_count.setText(str(settings.value("ui_loop_count", "1")))
            self.input_exp_date.setText(str(settings.value("ui_exp_date", "2024-03-05")))
            self.chk_write_date.setChecked(str(settings.value("ui_write_date", "false")).lower() == "true")
            self.combo_sn_fmt.setCurrentText(str(settings.value("ui_sn_fmt", "DEC")))
            self.input_exp_sn.setText(str(settings.value("ui_exp_sn", "1")))
            
            write_sn_str = str(settings.value("ui_write_sn", "False")).lower()
            auto_inc_str = str(settings.value("ui_auto_inc", "False")).lower()
            self.chk_write_sn.setChecked(write_sn_str == "true")
            self.chk_auto_inc.setChecked(auto_inc_str == "true")
            
            used_ports = set()
            for board in self.boards:
                bid = board.board_id
                port = str(settings.value(f"ui_board_{bid}_port", f"COM{5 + bid}"))
                if port != "None" and port in used_ports:
                    port = "None"
                
                board.combo_port.setCurrentText(port)
                if port != "None":
                    used_ports.add(port)
                
                for i, chk in enumerate(board.ch_checkboxes):
                    ch_str = str(settings.value(f"ui_board_{bid}_ch_{i+1}", "True")).lower()
                    chk.setChecked(ch_str == "true")
        except Exception as e:
            logging.getLogger('IBQtools').error(f"Failed to load UI states: {e}")

# Backwards compatibility alias
UpdaterTab = SNCheckerTab

