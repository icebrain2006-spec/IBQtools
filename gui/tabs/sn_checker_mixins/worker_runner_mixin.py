import time
from gui.styles import Colors
from gui.utils import play_sound_effect, is_error_status
from gui.updater_thread import set_led_state, GlobalPreflightWorker

class WorkerRunnerMixin:
    """Mixin class for controlling multi-board worker execution, logging, and preflight checks."""

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

    def _log_to_console(self, msg):
        is_error = is_error_status(msg)
        lower_msg = msg.lower()
        
        from gui.config import config, log_error
        if is_error:
            log_error(f"[SN Checker] {msg}")

        if config.settings.value("global_debug_log_en", "false") != "true":
            if not is_error and "[sys]" not in lower_msg and "finished" not in lower_msg:
                return
                
        safe_msg = msg.replace("<", "&lt;").replace(">", "&gt;")
        if is_error:
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
                set_led_state(port, board.led_color, 1, 10)
                board.start_blink(10)
            else:
                set_led_state(port, board.led_color, 0, 0)

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

    def _check_any_board_has_error(self) -> bool:
        """Iterates over all boards and channels to check if any channel has a failure/error status."""
        for board in self.boards:
            for stat in board.ch_status:
                if is_error_status(stat.text()):
                    return True
        return False

    def _play_completion_sound(self, is_error: bool):
        """Launches a daemon thread to play completion/failure sound or fallback beeps via utils."""
        play_sound_effect(is_error)

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
