import os
import logging
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, 
                               QLabel, QPushButton, QMessageBox)
from PySide6.QtCore import Qt, Signal, QTimer

from widgets.port_combobox import PortComboBox
from widgets.clickable_progress_bar import ClickableProgressBar
from styles import Colors, Styles
from utils import append_work_log, get_active_usb_ports, format_sn_value, is_error_status
from updater_thread import UpdaterWorker, SerialCheckWorker, get_file_info, get_fw_version, set_led_state, DisconnectionMonitor
from config import config

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
        active_ports = get_active_usb_ports()
        self.combo_port.addItems(active_ports)
            
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
        
        from PySide6.QtWidgets import QCheckBox
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
            set_led_state(port, self.led_color, 0, 0)

    def start_blink(self, duration_sec):
        self.blink_duration_left = duration_sec * 2
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
            if is_error_status(status_text):
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

        actual_sn_int, sn_str = format_sn_value(sn_int, sn_fmt)

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

        # File I/O via isolated utility
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
            set_led_state(port, self.led_color, 0, 0)
        else:
            set_led_state(port, self.led_color, 1, 10)
            self.start_blink(10)

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
        if 1 <= ch_idx <= 6:
            self.ch_progress[ch_idx - 1].setValue(0)
            self.ch_status[ch_idx - 1].setText("Status: Waiting (Swapped)")
            self.ch_status[ch_idx - 1].setStyleSheet(f"color: {Colors.HEX_TEXT_MUTED};")
            self.passed_channels.discard(ch_idx)

            if not self.passed_channels:
                self.btn_start_board.setEnabled(True)
