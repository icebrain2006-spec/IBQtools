import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLineEdit, QPushButton, QFormLayout, QMessageBox,
    QFileDialog, QLabel, QCheckBox
)
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QKeySequenceEdit

from gui.config import config, setup_error_logging
from gui.dialogs.csv_viewer_dialog import CsvViewerDialog
from gui.workers.fw_update_worker import CheckUpdateWorker, DownloadUpdateWorker, RebootBootselWorker
from gui.styles import Colors
from gui.strings import UIStrings


class OptionsTab(QWidget):
    """Options and configuration settings tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.latest_uf2_url = None
        self.boards_to_update = []
        self.update_queue = []
        self._init_ui()
        
    def _init_ui(self):
        layout_options = QVBoxLayout(self)
        
        # --- Data Logging Settings ---
        group_log_settings = QGroupBox(UIStrings.get("GRP_DATA_LOGGING"))
        layout_log = QFormLayout(group_log_settings)
        
        self.input_work_log = QLineEdit()
        self.btn_browse_work = QPushButton(UIStrings.get("BTN_BROWSE"))
        self.btn_view_work = QPushButton(UIStrings.get("BTN_VIEWER"))
        work_layout = QHBoxLayout()
        work_layout.addWidget(self.input_work_log)
        work_layout.addWidget(self.btn_browse_work)
        work_layout.addWidget(self.btn_view_work)
        
        self.input_cal_log = QLineEdit()
        self.btn_browse_cal = QPushButton(UIStrings.get("BTN_BROWSE"))
        self.btn_view_cal = QPushButton(UIStrings.get("BTN_VIEWER"))
        cal_layout = QHBoxLayout()
        cal_layout.addWidget(self.input_cal_log)
        cal_layout.addWidget(self.btn_browse_cal)
        cal_layout.addWidget(self.btn_view_cal)
        
        self.input_error_log = QLineEdit()
        self.btn_browse_error = QPushButton(UIStrings.get("BTN_BROWSE"))
        error_layout = QHBoxLayout()
        error_layout.addWidget(self.input_error_log)
        error_layout.addWidget(self.btn_browse_error)
        
        layout_log.addRow(UIStrings.get("LBL_WORK_LOG"), work_layout)
        layout_log.addRow(UIStrings.get("LBL_CAL_LOG"), cal_layout)
        
        # --- Error & Debug Settings ---
        group_error_settings = QGroupBox(UIStrings.get("GRP_ERROR_DEBUG"))
        layout_error = QFormLayout(group_error_settings)
        layout_error.addRow(UIStrings.get("LBL_ERROR_LOG"), error_layout)
        
        self.cb_global_debug_log = QCheckBox(UIStrings.get("CB_GLOBAL_DEBUG_LOG"))
        self.cb_global_debug_log.setChecked(config.settings.value("global_debug_log_en", "false") == "true")
        layout_error.addRow(UIStrings.get("LBL_CONSOLE_OUTPUT"), self.cb_global_debug_log)
        
        # --- Production Settings ---
        group_prod_settings = QGroupBox(UIStrings.get("GRP_PRODUCTION"))
        layout_prod = QFormLayout(group_prod_settings)
        
        self.input_hotkey = QKeySequenceEdit()
        self.input_hotkey.setKeySequence(QKeySequence(config.get_start_hotkey()))
        self.input_hotkey.setToolTip(UIStrings.get("TOOLTIP_HOTKEY"))
        layout_prod.addRow(UIStrings.get("LBL_QUICK_START_HOTKEY"), self.input_hotkey)
        
        self.btn_save_options = QPushButton(UIStrings.get("BTN_SAVE_SETTINGS"))
        
        layout_options.addWidget(group_log_settings)
        layout_options.addWidget(group_error_settings)
        layout_options.addWidget(group_prod_settings)
        layout_options.addWidget(self.btn_save_options)
        
        # --- Firmware Auto-Update Settings ---
        group_fw = QGroupBox(UIStrings.get("GRP_FW_UPDATE"))
        layout_fw = QVBoxLayout(group_fw)
        
        form_fw = QFormLayout()
        self.input_github_repo = QLineEdit(config.settings.value("github_repo", "icebrain2006-spec/IBQtools", type=str))
        self.input_github_repo.setPlaceholderText(UIStrings.get("PH_GITHUB_REPO"))
        form_fw.addRow(UIStrings.get("LBL_GITHUB_REPO"), self.input_github_repo)
        
        self.lbl_latest_ver = QLabel("Board: Unknown | Latest: Unknown")
        self.lbl_latest_ver.setStyleSheet(f"color: {Colors.HEX_WARN_CYAN}; font-weight: bold;")
        form_fw.addRow(UIStrings.get("LBL_STATUS"), self.lbl_latest_ver)
        
        layout_fw.addLayout(form_fw)
        
        btn_layout = QHBoxLayout()
        self.btn_check_update = QPushButton(UIStrings.get("BTN_CHECK_UPDATE"))
        self.btn_download_update = QPushButton(UIStrings.get("BTN_DOWNLOAD_FLASH"))
        self.btn_download_update.setEnabled(False)
        self.btn_download_update.setObjectName("startBtn")
        
        self.btn_flash_local = QPushButton(UIStrings.get("BTN_FLASH_LOCAL"))
        self.btn_flash_local.setObjectName("startBtn")
        
        btn_layout.addWidget(self.btn_check_update)
        btn_layout.addWidget(self.btn_download_update)
        btn_layout.addWidget(self.btn_flash_local)
        layout_fw.addLayout(btn_layout)
        
        self.lbl_update_status = QLabel(UIStrings.get("LBL_READY"))
        layout_fw.addWidget(self.lbl_update_status)
        
        layout_options.addWidget(group_fw)
        layout_options.addStretch()
        
        # Initial File Path Values
        self.input_work_log.setText(config.get_work_log_path())
        self.input_cal_log.setText(config.get_cal_log_path())
        self.input_error_log.setText(config.get_error_log_path())
        
        # Connect signals
        self.btn_browse_work.clicked.connect(self._browse_work_log)
        self.btn_browse_cal.clicked.connect(self._browse_cal_log)
        self.btn_browse_error.clicked.connect(self._browse_error_log)
        
        self.btn_view_work.clicked.connect(self._view_work_log)
        self.btn_view_cal.clicked.connect(self._view_cal_log)
        
        self.btn_save_options.clicked.connect(self._save_settings)
        self.btn_check_update.clicked.connect(self._on_check_update)
        self.btn_download_update.clicked.connect(self._on_download_update)
        self.btn_flash_local.clicked.connect(self._on_flash_local)

    def _browse_work_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Work Log File", self.input_work_log.text(), "CSV Files (*.csv);;All Files (*)")
        if path:
            self.input_work_log.setText(path)

    def _view_work_log(self):
        path = self.input_work_log.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Not Found", "The specified CSV file does not exist yet.")
            return
        dialog = CsvViewerDialog(path, self)
        dialog.exec()

    def _browse_cal_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Cal Log File", self.input_cal_log.text(), "CSV Files (*.csv);;All Files (*)")
        if path:
            self.input_cal_log.setText(path)

    def _view_cal_log(self):
        path = self.input_cal_log.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Not Found", "The specified CSV file does not exist yet.")
            return
        dialog = CsvViewerDialog(path, self)
        dialog.exec()

    def _browse_error_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Error Log File", self.input_error_log.text(), "Text Files (*.txt *.log);;All Files (*)")
        if path:
            self.input_error_log.setText(path)

    def _save_settings(self):
        config.set_work_log_path(self.input_work_log.text())
        config.set_cal_log_path(self.input_cal_log.text())
        config.set_error_log_path(self.input_error_log.text())
        config.settings.setValue("github_repo", self.input_github_repo.text().strip())
        config.settings.setValue("global_debug_log_en", "true" if self.cb_global_debug_log.isChecked() else "false")
        
        seq = self.input_hotkey.keySequence().toString()
        if not seq: 
            seq = "Space"
        config.set_start_hotkey(seq)
        config.settings.sync()
        
        main_win = self.window()
        if hasattr(main_win, 'update_start_hotkey'):
            main_win.update_start_hotkey(seq)
            
        setup_error_logging(self.input_error_log.text())
        QMessageBox.information(self, "Settings Saved", "Application settings have been saved successfully.")

    def _on_check_update(self):
        repo = self.input_github_repo.text().strip()
        if not repo or '/' not in repo:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid GitHub repository (e.g. username/repo).")
            return
            
        self.btn_check_update.setEnabled(False)
        self.lbl_update_status.setText("Checking for updates...")
        self.btn_download_update.setEnabled(False)
        
        self.check_worker = CheckUpdateWorker(repo)
        self.check_worker.finished.connect(self._on_check_finished)
        self.check_worker.error.connect(self._on_check_error)
        self.check_worker.start()

    def _on_check_finished(self, tag, url, versions, active_ports):
        self.btn_check_update.setEnabled(True)
        
        if not versions:
            self.lbl_latest_ver.setText(f'Board: Unknown | Latest: <span style="color: {Colors.HEX_SUCCESS};">{tag}</span>')
            self.lbl_update_status.setText("No boards found.")
            return
            
        ver_strs = []
        for p, v in zip(active_ports, versions):
            color = Colors.HEX_SUCCESS if v == tag else Colors.HEX_FAIL
            ver_strs.append(f'{p}(<span style="color: {color};">{v}</span>)')
            
        self.lbl_latest_ver.setText(f'Boards: {", ".join(ver_strs)} | Latest: <span style="color: {Colors.HEX_SUCCESS};">{tag}</span>')
        self.lbl_update_status.setText("Update available.")
        self.latest_uf2_url = url
        self.boards_to_update = list(active_ports)
        self.btn_download_update.setEnabled(True)

    def _on_check_error(self, err_msg):
        self.btn_check_update.setEnabled(True)
        self.lbl_update_status.setText(f"Check failed: {err_msg}")
        self.lbl_latest_ver.setText("Board: Unknown | Latest: Error")

    def _on_download_update(self):
        if not self.latest_uf2_url:
            return
        if not self.boards_to_update:
            QMessageBox.information(self, "No boards", "No connected boards to update.")
            return
            
        self.update_queue = list(self.boards_to_update)
        self._process_next_board(is_local=False)

    def _process_next_board(self, is_local=False, local_path=None):
        if not self.update_queue:
            QMessageBox.information(self, "Finished", "All connected boards have been updated successfully.")
            self.btn_download_update.setEnabled(True)
            self.btn_check_update.setEnabled(True)
            self.btn_flash_local.setEnabled(True)
            self.lbl_update_status.setText("Batch update complete.")
            return
            
        port = self.update_queue.pop(0)
        self.current_update_port = port
        self.is_local_update = is_local
        self.local_update_path = local_path
        
        self.lbl_update_status.setText(f"Sending software reset to {port}...")
        
        # Async reboot worker to avoid UI blocking
        self.reboot_worker = RebootBootselWorker(target_port=port)
        self.reboot_worker.progress.connect(self._on_dl_progress)
        self.reboot_worker.finished.connect(
            lambda success, msg: self._on_reboot_finished(success, msg, port, is_local, local_path)
        )
        self.reboot_worker.start()

    def _on_reboot_finished(self, success, msg, port, is_local, local_path):
        upload_reply = QMessageBox.information(
            self,
            f"Ready to Upload - {port}",
            f"Board at {port} has been reset.\n"
            "Please wait for the USB drive (RPI-RP2) to be recognized.\n\n"
            "Click OK when the drive is ready.",
            QMessageBox.Ok | QMessageBox.Cancel
        )
        
        if upload_reply == QMessageBox.Ok:
            self.btn_download_update.setEnabled(False)
            self.btn_check_update.setEnabled(False)
            self.btn_flash_local.setEnabled(False)
            
            if is_local:
                self.dl_worker = DownloadUpdateWorker(local_file=local_path)
            else:
                self.dl_worker = DownloadUpdateWorker(url=self.latest_uf2_url)
                
            self.dl_worker.progress.connect(self._on_dl_progress)
            self.dl_worker.finished.connect(self._on_dl_finished)
            self.dl_worker.start()
        else:
            self.lbl_update_status.setText("Update cancelled.")
            self.btn_download_update.setEnabled(True)
            self.btn_check_update.setEnabled(True)
            self.btn_flash_local.setEnabled(True)

    def _on_flash_local(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Local Firmware", "", "UF2 Files (*.uf2);;All Files (*)")
        if not path:
            return
        if not self.boards_to_update:
            QMessageBox.information(self, "No boards", "Please click 'Check Update' first to scan connected boards.")
            return
            
        self.update_queue = list(self.boards_to_update)
        self._process_next_board(is_local=True, local_path=path)

    def _on_dl_progress(self, msg):
        self.lbl_update_status.setText(msg)

    def _on_dl_finished(self, success, msg):
        if success:
            self.lbl_update_status.setText(f"Done: {msg}")
            if self.update_queue:
                reply = QMessageBox.question(
                    self, 
                    "Next Board", 
                    f"Update for {self.current_update_port} successful!\n\nDo you want to proceed with the next board ({self.update_queue[0]})?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._process_next_board(is_local=self.is_local_update, local_path=self.local_update_path)
                    return
                else:
                    self.update_queue = []
                    self.lbl_update_status.setText("Batch update stopped.")
            else:
                QMessageBox.information(self, "Update Complete", "All selected boards updated successfully.")
        else:
            self.lbl_update_status.setText(f"Error: {msg}")
            QMessageBox.critical(self, "Update Error", msg)
            
        self.btn_check_update.setEnabled(True)
        self.btn_flash_local.setEnabled(True)
        self.btn_download_update.setEnabled(True)
