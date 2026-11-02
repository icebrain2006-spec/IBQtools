import os
from PySide6.QtWidgets import QMessageBox
from gui.gdrive_utils import get_default_log_dir, migrate_all_local_logs
from gui.config import config, setup_error_logging
from gui.strings import UIStrings
from gui.styles import Colors


class OptionsGDriveSyncMixin:
    """Mixin providing Google Drive log sync and migration features for OptionsTab."""

    def _update_gdrive_status_label(self):
        detected = get_default_log_dir()
        if os.path.exists(detected) or "Google" in detected or "drive" in detected.lower():
            self.lbl_gdrive_path.setText(
                f'<span style="color: {Colors.HEX_SUCCESS}; font-weight: bold;">● Active:</span> {detected}'
            )
        else:
            self.lbl_gdrive_path.setText(
                f'<span style="color: {Colors.HEX_WARN_CYAN};">Fallback:</span> {detected}'
            )

    def _on_set_gdrive_paths(self):
        target_dir = get_default_log_dir()
        work_path = os.path.join(target_dir, "work_log.csv")
        cal_path = os.path.join(target_dir, "cal_log.csv")
        error_path = os.path.join(target_dir, "error_log.txt")

        self.input_work_log.setText(work_path)
        self.input_cal_log.setText(cal_path)
        self.input_error_log.setText(error_path)

        # Automatically save to config
        config.set_work_log_path(work_path)
        config.set_cal_log_path(cal_path)
        config.set_error_log_path(error_path)
        config.settings.sync()

        setup_error_logging(error_path, self.cb_save_error_log.isChecked())
        self._update_gdrive_status_label()

        msg = f"{UIStrings.get('MSG_GDRIVE_APPLIED')}\n\n• Work Log: {work_path}\n• Cal Log: {cal_path}\n• Error Log: {error_path}"
        QMessageBox.information(self, "Google Drive Storage Applied", msg)

    def _on_migrate_local_logs(self):
        target_dir = os.path.dirname(self.input_work_log.text().strip())
        if not target_dir or not os.path.isabs(target_dir):
            target_dir = get_default_log_dir()

        results = migrate_all_local_logs(target_dir)
        if not results:
            QMessageBox.information(
                self,
                "Migration",
                "No local log files (work_log.csv, cal_log.csv) found in the project root."
            )
            return

        detail_lines = []
        for fname, (ok, status_msg) in results.items():
            status_tag = "[OK]" if ok else "[FAIL]"
            detail_lines.append(f"{status_tag} {fname} -> {status_msg}")

        summary = "\n".join(detail_lines)
        QMessageBox.information(
            self,
            "Migration Finished",
            f"{UIStrings.get('MSG_MIGRATE_SUCCESS')}\n\nTarget Directory: {target_dir}\n\n{summary}"
        )

