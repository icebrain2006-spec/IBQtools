"""Runner and Worker connection Mixin for Auto Cycle tab."""

import os
from PySide6.QtCore import Signal
from gui.strings import UIStrings


class RunnerMixin:
    """Manages worker lifecycle, relay states, and safety tab locking."""

    def start_process(self, auto_cycle: bool = True):
        """Starts either Auto Cycle or Logging Only worker."""
        from gui.workers.auto_cycle_worker import AutoCycleWorker
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            return

        port = self.combo_port.currentText()
        if not port or port == "Select COM":
            self.append_log("Error: Please select a valid COM port first.")
            return

        # Prepare CSV
        csv_path = self.txt_file_path.text().strip()
        if not csv_path:
            csv_path = os.path.join(os.getcwd(), f"auto_cycle_log_{port}.csv")
            self.txt_file_path.setText(csv_path)
            
        self.init_csv_logging(csv_path)

        poll_sec = self.spn_poll_interval.value()
        target_cycles = self.spn_target_cycles.value() if auto_cycle else 0

        self.worker = AutoCycleWorker(
            port_name=port,
            poll_interval=poll_sec,
            auto_cycle=auto_cycle,
            target_cycles=target_cycles,
            parent=self
        )

        # Wire signals
        self.worker.data_updated.connect(self.on_telemetry_received)
        self.worker.step_changed.connect(self.update_cycle_display)
        self.worker.relay_state_changed.connect(self.update_relay_indicators)
        self.worker.log_message.connect(self.append_log)
        self.worker.finished_cycle.connect(self.on_worker_finished)

        # Lock UI & lock other tabs!
        self._set_ui_running(True)
        if hasattr(self, 'lock_tabs_requested'):
            self.lock_tabs_requested.emit(True)

        self.worker.start()

    def stop_process(self):
        """Stops running worker and unlocks tabs."""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.append_log("Stopping process, please wait...")
            self.worker.stop()
            self.worker.wait(1500)

        self._set_ui_running(False)
        if hasattr(self, 'lock_tabs_requested'):
            self.lock_tabs_requested.emit(False)

    def on_worker_finished(self, msg: str):
        """Called when worker exits naturally or by error."""
        self.append_log(msg)
        self._set_ui_running(False)
        if hasattr(self, 'lock_tabs_requested'):
            self.lock_tabs_requested.emit(False)

    def on_telemetry_received(self, telemetry: dict):
        """Updates all UI panels with latest telemetry."""
        # 1. Update Grid
        self.update_status_bits(telemetry)

        # 2. Update Highlight Badges & RSOC
        self.update_key_flags(telemetry)
        self.check_rsoc_alarms(telemetry)

        # 3. Append to CSV
        curr_step = getattr(self, 'lbl_step_name', None)
        step_text = curr_step.text() if curr_step else ""
        self.log_telemetry_to_csv(telemetry, step_text)

        # 4. Update Quick Cards
        self.val_vpack.setText(f"{telemetry.get('Voltage', 0)} mV")
        self.val_current.setText(f"{telemetry.get('Current', 0)} mA")
        self.val_rsoc.setText(f"{telemetry.get('RSOC', 0)} %")
        self.val_temp.setText(f"{telemetry.get('Temperature', 0.0)} °C")
        
        c1 = telemetry.get('Cell1', 0)
        c2 = telemetry.get('Cell2', 0)
        c3 = telemetry.get('Cell3', 0)
        c4 = telemetry.get('Cell4', 0)
        self.val_cells.setText(f"{c1} | {c2} | {c3} | {c4} mV")

    def update_relay_indicators(self, power_on: bool, load_on: bool):
        """Updates relay On/Off visual indicators in header banner."""
        if power_on:
            self.badge_power.setText("CH1 Power: ON")
            self.badge_power.setStyleSheet("background-color: #00e676; color: black; font-weight: bold; padding: 3px 8px; border-radius: 3px;")
        else:
            self.badge_power.setText("CH1 Power: OFF")
            self.badge_power.setStyleSheet("background-color: #333333; color: #888888; font-weight: bold; padding: 3px 8px; border-radius: 3px;")

        if load_on:
            self.badge_load.setText("CH2 Load: ON")
            self.badge_load.setStyleSheet("background-color: #ff5252; color: white; font-weight: bold; padding: 3px 8px; border-radius: 3px;")
        else:
            self.badge_load.setText("CH2 Load: OFF")
            self.badge_load.setStyleSheet("background-color: #333333; color: #888888; font-weight: bold; padding: 3px 8px; border-radius: 3px;")

    def _set_ui_running(self, running: bool):
        """Toggles button and control enabled states."""
        self.btn_auto_start.setEnabled(not running)
        self.btn_log_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.combo_port.setEnabled(not running)
        self.combo_ic.setEnabled(not running)
        self.spn_poll_interval.setEnabled(not running)
        self.spn_target_cycles.setEnabled(not running)
        self.txt_file_path.setEnabled(not running)
        self.btn_browse.setEnabled(not running)
