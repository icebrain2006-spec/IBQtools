"""State Machine & Key Flags Mixin for Auto Cycle tab."""

from PySide6.QtGui import QColor
from gui.styles import Colors


class StateMachineMixin:
    """Manages cycle status banner and key learning/safety flag indicators."""

    def update_cycle_display(self, step_name: str, cycle_count: int, elapsed_sec: int):
        """Updates large step indicator, cycle count, and step timer."""
        self.lbl_step_name.setText(step_name)
        
        # Dynamic color coding for steps
        if "CHARGING" in step_name:
            self.lbl_step_name.setStyleSheet("font-size: 16px; font-weight: bold; color: #40c4ff; background-color: #002b4d; border-radius: 4px; padding: 4px 10px;")
        elif "CHARGED" in step_name:
            self.lbl_step_name.setStyleSheet("font-size: 16px; font-weight: bold; color: #69f0ae; background-color: #003314; border-radius: 4px; padding: 4px 10px;")
        elif "DISCHARGING" in step_name:
            self.lbl_step_name.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffab40; background-color: #4a2800; border-radius: 4px; padding: 4px 10px;")
        elif "DISCHARGED" in step_name:
            self.lbl_step_name.setStyleSheet("font-size: 16px; font-weight: bold; color: #e040fb; background-color: #380036; border-radius: 4px; padding: 4px 10px;")
            
        hrs = elapsed_sec // 3600
        mins = (elapsed_sec % 3600) // 60
        secs = elapsed_sec % 60
        self.lbl_step_time.setText(f"{hrs:02d}:{mins:02d}:{secs:02d}")
        self.lbl_cycle_count.setText(str(cycle_count))

    def update_key_flags(self, telemetry: dict):
        """Updates highlight badges for key learning/safety flags."""
        flags = [
            ("VCT", self.badge_vct),
            ("REST", self.badge_rest),
            ("FD", self.badge_fd),
            ("FC", self.badge_fc),
            ("CUV", self.badge_cuv)
        ]
        for key, badge in flags:
            is_on = bool(telemetry.get(key, False))
            if is_on:
                badge.setStyleSheet("background-color: #cd5c5c; color: white; font-weight: bold; border-radius: 3px; padding: 2px 6px;")
            else:
                badge.setStyleSheet("background-color: #32cd32; color: white; font-weight: bold; border-radius: 3px; padding: 2px 6px;")

        # Update Lstatus badge
        lstat = telemetry.get("Lstatus", 0)
        self.badge_lstatus.setText(f"Lstatus: 0x{lstat:02X}")
        if lstat in [0x05, 0x06, 0x0E]:
            self.badge_lstatus.setStyleSheet("background-color: #00bcd4; color: white; font-weight: bold; border-radius: 3px; padding: 2px 6px;")
        else:
            self.badge_lstatus.setStyleSheet("background-color: #424242; color: #ccc; font-weight: bold; border-radius: 3px; padding: 2px 6px;")

    def check_rsoc_alarms(self, telemetry: dict):
        """Checks RSOC threshold alarms during cycle."""
        rsoc = telemetry.get("RSOC")
        curr = telemetry.get("Current", 0)
        if rsoc is None:
            return

        if hasattr(self, 'chk_charge_alarm') and self.chk_charge_alarm.isChecked():
            if curr > 50 and rsoc >= self.spn_charge_limit.value():
                self.append_log(f"[ALARM] High RSOC limit reached: {rsoc}% (Target: {self.spn_charge_limit.value()}%)")

        if hasattr(self, 'chk_discharge_alarm') and self.chk_discharge_alarm.isChecked():
            if curr < -50 and rsoc <= self.spn_discharge_limit.value():
                self.append_log(f"[ALARM] Low RSOC limit reached: {rsoc}% (Target: {self.spn_discharge_limit.value()}%)")
