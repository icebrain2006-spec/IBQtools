from PySide6.QtWidgets import QMessageBox
from gui.styles import Colors
from gui.utils import append_work_log, format_sn_value, is_error_status
from gui.updater_thread import UpdaterWorker, SerialCheckWorker, set_led_state, DisconnectionMonitor
from gui.config import config


class BoardWorkerMixin:
    """Mixin for managing background worker threads, serial checks, verification, and logging."""

    def _get_selected_channels(self) -> list:
        """Single Responsibility: Get list of 1-indexed enabled channel numbers."""
        active = []
        for i, chk in enumerate(self.ch_checkboxes):
            if chk.isChecked():
                active.append(i + 1)
        return active

    def _stop_disconnection_monitor(self):
        """Single Responsibility: Safely stop the disconnection monitor thread if running."""
        if self.disconnect_monitor and self.disconnect_monitor.isRunning():
            self.disconnect_monitor.stop()
            self.disconnect_monitor.wait(500)

    def _lock_board_ui_controls(self):
        """Single Responsibility: Disable interactive UI elements during worker execution."""
        for chk in self.ch_checkboxes:
            chk.setEnabled(False)
        self.btn_start_board.setEnabled(False)
        self.combo_port.setEnabled(False)
        self.btn_refresh.setEnabled(False)

    def _restore_board_ui_controls(self):
        """Single Responsibility: Enable interactive UI elements after worker finishes."""
        self.combo_port.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        for chk in self.ch_checkboxes:
            chk.setEnabled(True)

    def _reset_channels_progress_ui(self, active_channels: list, status_text: str = "Status: Starting..."):
        """Single Responsibility: Reset progress bar and status label for all 6 channels."""
        for i in range(6):
            if (i + 1) in active_channels:
                self.ch_progress[i].setValue(0)
                self.ch_status[i].setText(status_text)
                self.ch_status[i].setStyleSheet(f"color: {Colors.HEX_TEXT_MUTED};")
            else:
                self.ch_status[i].setText("Status: Disabled")
                self.ch_status[i].setStyleSheet(f"color: {Colors.HEX_TEXT_DISABLED};")

    def _launch_updater_worker(self, port: str, active_channels: list, loop_count: int, skip_preflight: bool = False):
        """Single Responsibility: Construct and launch UpdaterWorker QThread."""
        self.worker = UpdaterWorker(
            port, active_channels, loop_count=loop_count, 
            get_expected_cb=self._get_sn_for_worker, skip_preflight=skip_preflight
        )
        self.worker.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id}] {msg}"))
        self.worker.progress_updated.connect(self._on_progress_update)
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.verify_updated.connect(self._on_verify_update)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def start_worker(self, loop_count: int, skip_preflight: bool = False) -> bool:
        """Starts batch update worker across all enabled channels."""
        self._stop_disconnection_monitor()
        self.passed_channels.clear()

        active_channels = self._get_selected_channels()
        if not active_channels:
            self.log_callback(f"[Board {self.board_id}] No channels selected. Skipping.")
            return False

        if self.cache_values_cb:
            self.cache_values_cb()

        port = self.combo_port.currentText()
        self._lock_board_ui_controls()
        self._reset_channels_progress_ui(active_channels, "Status: Starting...")

        self.log_callback(f"[Board {self.board_id}] Initializing thread on {port}...")
        self.expected_sn_map.clear()
        self.expected_date_map.clear()

        self._launch_updater_worker(port, active_channels, loop_count, skip_preflight)
        return True

    def start_single_channel(self, ch_idx: int):
        """Starts update worker for a single targeted channel."""
        if self.worker and self.worker.isRunning():
            self.log_callback(f"[Board {self.board_id}] Worker is already running. Please stop it first.")
            return

        if self.passed_channels and ch_idx in self.passed_channels:
            self.log_callback(f"[Board {self.board_id} CH {ch_idx}] Channel is in PASS state. Swap to unlock.")
            return

        self._stop_disconnection_monitor()
        self.passed_channels.discard(ch_idx)

        self.refresh_info()
        if "Unknown" in self.lbl_slfs_info.text() or "Error" in self.lbl_slfs_info.text():
            QMessageBox.warning(self, "SLFS Check", f"Board {self.board_id}: SLFS file not found! Please check the connection or upload the SLFS file first.")
            return

        if self.cache_values_cb:
            self.cache_values_cb()

        port = self.combo_port.currentText()
        self._lock_board_ui_controls()

        self.ch_progress[ch_idx - 1].setValue(0)
        self.ch_status[ch_idx - 1].setText("Status: Starting...")

        self.log_callback(f"[Board {self.board_id}] Initializing SINGLE update for CH {ch_idx} on {port}...")
        self.expected_sn_map.clear()
        self.expected_date_map.clear()

        self._launch_updater_worker(port, [ch_idx], loop_count=1, skip_preflight=False)

    def stop_worker(self):
        """Stops the active worker thread if running."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()

    def check_serial(self):
        """Starts Serial Check worker to read serial numbers without flashing."""
        if self.worker and self.worker.isRunning():
            self.log_callback(f"[Board {self.board_id}] Worker is running. Please stop it first.")
            return

        if self.cache_values_cb:
            self.cache_values_cb()

        active_channels = self._get_selected_channels()
        if not active_channels:
            self.log_callback(f"[Board {self.board_id}] No channels selected. Skipping.")
            return

        port = self.combo_port.currentText()
        self._lock_board_ui_controls()
        self._reset_channels_progress_ui(active_channels, "Status: Starting Read...")

        _, _, fmt, _, _ = self.get_expected_cb(False)
        self.worker = SerialCheckWorker(port, active_channels, fmt=fmt)
        self.worker.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id}] {msg}"))
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _get_sn_for_worker(self, ch_idx: int):
        """Provides target expected SN and Date for worker callbacks."""
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

    def _on_progress_update(self, ch_idx: int, percent: int):
        if 1 <= ch_idx <= 6:
            self.ch_progress[ch_idx - 1].setValue(percent)

    def _on_status_update(self, ch_idx: int, status_text: str):
        if 1 <= ch_idx <= 6:
            if is_error_status(status_text):
                from gui.config import log_error
                log_error(f"[Board {self.board_id} Ch{ch_idx}] {status_text}")
                self.ch_status[ch_idx - 1].setText(f'Status: <span style="color: {Colors.HEX_FAIL};">{status_text}</span>')
            else:
                self.ch_status[ch_idx - 1].setText(f"Status: {status_text}")
            self.ch_status[ch_idx - 1].setStyleSheet("")

    def _resolve_expected_targets(self, ch_idx: int):
        if ch_idx in self.expected_sn_map:
            exp_date = self.expected_date_map[ch_idx]
            exp_sn_int = self.expected_sn_map[ch_idx]
            sn_fmt = self.expected_fmt
            _, _, _, should_write_sn, should_write_date = self.get_expected_cb(False)
        else:
            exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date = self.get_expected_cb(False)
        return exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date

    def _evaluate_verification(self, exp_date: str, exp_sn_int: int, sn_fmt: str, date_str: str, sn_int: int, should_write_date: bool, should_write_sn: bool):
        if not date_str or sn_int < 0:
            return "ERROR", "N/A"

        actual_sn_int, sn_str = format_sn_value(sn_int, sn_fmt)
        date_match = (date_str == exp_date) if should_write_date else True
        sn_match = (actual_sn_int == exp_sn_int) if should_write_sn else True
        result_str = "PASS" if (date_match and sn_match) else "FAIL"
        return result_str, sn_str

    def _update_channel_verify_ui(self, ch_idx: int, result_str: str, date_str: str, sn_str: str):
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

    def _on_verify_update(self, ch_idx: int, date_str: str, sn_int: int):
        if not (1 <= ch_idx <= 6):
            return

        exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date = self._resolve_expected_targets(ch_idx)
        should_write = should_write_sn or should_write_date

        result_str, sn_str = self._evaluate_verification(
            exp_date, exp_sn_int, sn_fmt, date_str, sn_int, should_write_date, should_write_sn
        )

        self._update_channel_verify_ui(ch_idx, result_str, date_str, sn_str)

        slfs_file = self.lbl_slfs_info.text().replace("SLFS: ", "")
        wrote_sn = "Yes" if should_write else "No"
        ch_sn_str = f"0x{sn_int:04X}" if sn_fmt == "HEX" else str(sn_int) if sn_int >= 0 else "N/A"

        append_work_log(config.get_work_log_path(), self.board_id, ch_idx, slfs_file, wrote_sn, date_str, ch_sn_str, result_str)

    def _apply_finish_notifications(self, success: bool, port: str):
        if success:
            set_led_state(port, self.led_color, 0, 0)
        else:
            set_led_state(port, self.led_color, 1, 10)
            self.start_blink(10)

    def _start_disconnection_monitor_if_needed(self, port: str):
        if self.passed_channels:
            self.btn_start_board.setEnabled(False)
            self.disconnect_monitor = DisconnectionMonitor(port, self.passed_channels)
            self.disconnect_monitor.channel_disconnected.connect(self._on_channel_disconnected)
            self.disconnect_monitor.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id} MON] {msg}"))
            self.disconnect_monitor.start()
        else:
            self.btn_start_board.setEnabled(True)

    def _on_worker_finished(self, success: bool):
        self._restore_board_ui_controls()
        port = self.combo_port.currentText().strip()
        self._apply_finish_notifications(success, port)

        self.log_callback(f"[Board {self.board_id}] Thread finished.")
        self.board_finished.emit()
        self._start_disconnection_monitor_if_needed(port)

    def _on_channel_disconnected(self, ch_idx: int):
        if 1 <= ch_idx <= 6:
            self.ch_progress[ch_idx - 1].setValue(0)
            self.ch_status[ch_idx - 1].setText("Status: Waiting (Swapped)")
            self.ch_status[ch_idx - 1].setStyleSheet(f"color: {Colors.HEX_TEXT_MUTED};")
            self.passed_channels.discard(ch_idx)

            if not self.passed_channels:
                self.btn_start_board.setEnabled(True)
