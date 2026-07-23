import os
import shutil
import tempfile
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLineEdit, QPushButton, QFormLayout, QMessageBox,
                               QFileDialog, QLabel, QProgressBar)
from PySide6.QtCore import QThread, Signal, Qt
from config import config, setup_error_logging
from fw_updater import get_latest_github_release, download_file, find_rp2040_drive
from updater_thread import get_fw_version

class CheckUpdateWorker(QThread):
    finished = Signal(str, str, str) # tag_name, url, current_version
    error = Signal(str)
    
    def __init__(self, repo):
        super().__init__()
        self.repo = repo
        
    def run(self):
        try:
            # 1. Fetch latest github release
            tag, url = get_latest_github_release(self.repo)
            
            # 2. Get current board version by scanning active COM ports
            current_ver = "Not Connected"
            import serial.tools.list_ports
            active_ports = []
            for p in serial.tools.list_ports.comports():
                hwid = str(p.hwid).upper()
                desc = str(p.description).upper()
                if "BTHENUM" in hwid or "BLUETOOTH" in desc or "BTHENUM" in desc:
                    continue
                if "USB" not in hwid and "USB" not in desc:
                    continue
                active_ports.append(p.device)
                
            for port in active_ports:
                ver = get_fw_version(port)
                if ver:
                    current_ver = ver
                    break
                    
            if tag and url:
                self.finished.emit(tag, url, current_ver)
            else:
                self.error.emit("Could not find a valid .uf2 release.")
        except Exception as e:
            self.error.emit(str(e))

class DownloadUpdateWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str) # success, message
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        
    def run(self):
        self.progress.emit("Downloading .uf2 file...")
        temp_dir = tempfile.gettempdir()
        dest_path = os.path.join(temp_dir, "rp2040_update.uf2")
        
        success = download_file(self.url, dest_path)
        if not success:
            self.finished.emit(False, "Failed to download the file.")
            return
            
        self.progress.emit("Waiting for RP2040 BOOTSEL Drive...")
        import time
        drive = None
        # Poll for up to 30 seconds
        for _ in range(60):
            drive = find_rp2040_drive()
            if drive:
                break
            time.sleep(0.5)
            
        if not drive:
            self.finished.emit(False, "Timeout: RP2040 BOOTSEL drive not found.")
            return
            
        self.progress.emit(f"RP2040 found at {drive}. Copying firmware...")
        try:
            shutil.copy2(dest_path, os.path.join(drive, "rp2040_update.uf2"))
            self.progress.emit("Update complete! Device will reboot automatically.")
            self.finished.emit(True, "Update successfully flashed to RP2040.")
        except Exception as e:
            self.finished.emit(False, f"Error copying file: {e}")


class OptionsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.latest_uf2_url = None
        self._init_ui()
        
    def _init_ui(self):
        layout_options = QVBoxLayout(self)
        
        # --- Logging Settings ---
        group_log_settings = QGroupBox("Logging Settings")
        layout_log = QFormLayout(group_log_settings)
        
        self.input_work_log = QLineEdit()
        self.btn_browse_work = QPushButton("Browse...")
        work_layout = QHBoxLayout()
        work_layout.addWidget(self.input_work_log)
        work_layout.addWidget(self.btn_browse_work)
        
        self.input_error_log = QLineEdit()
        self.btn_browse_error = QPushButton("Browse...")
        error_layout = QHBoxLayout()
        error_layout.addWidget(self.input_error_log)
        error_layout.addWidget(self.btn_browse_error)
        
        layout_log.addRow("Work Log (CSV):", work_layout)
        layout_log.addRow("Error Log (TXT):", error_layout)
        
        self.btn_save_options = QPushButton("Save Settings")
        
        layout_options.addWidget(group_log_settings)
        layout_options.addWidget(self.btn_save_options)
        
        # --- Firmware Auto-Update Settings ---
        group_fw = QGroupBox("RP2040 Firmware Auto-Update")
        layout_fw = QVBoxLayout(group_fw)
        
        form_fw = QFormLayout()
        self.input_github_repo = QLineEdit(config.settings.value("github_repo", "icebrain2006-spec/IBQtools", type=str))
        self.input_github_repo.setPlaceholderText("e.g. username/repository")
        form_fw.addRow("GitHub Repository:", self.input_github_repo)
        
        self.lbl_latest_ver = QLabel("Board: Unknown | Latest: Unknown")
        self.lbl_latest_ver.setStyleSheet("color: #FFB300; font-weight: bold;")
        form_fw.addRow("Status:", self.lbl_latest_ver)
        
        layout_fw.addLayout(form_fw)
        
        btn_layout = QHBoxLayout()
        self.btn_check_update = QPushButton("Check Update")
        self.btn_download_update = QPushButton("Download && Flash")
        self.btn_download_update.setEnabled(False)
        self.btn_download_update.setObjectName("startBtn") # Use green style
        
        btn_layout.addWidget(self.btn_check_update)
        btn_layout.addWidget(self.btn_download_update)
        layout_fw.addLayout(btn_layout)
        
        self.lbl_update_status = QLabel("Ready.")
        layout_fw.addWidget(self.lbl_update_status)
        
        layout_options.addWidget(group_fw)
        
        layout_options.addStretch()
        
        # Connections
        self.input_work_log.setText(config.get_work_log_path())
        self.input_error_log.setText(config.get_error_log_path())
        self.btn_browse_work.clicked.connect(self._browse_work_log)
        self.btn_browse_error.clicked.connect(self._browse_error_log)
        self.btn_save_options.clicked.connect(self._save_options)
        
        self.btn_check_update.clicked.connect(self._on_check_update)
        self.btn_download_update.clicked.connect(self._on_download_update)
        
    def _browse_work_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Work Log File", self.input_work_log.text(), "CSV Files (*.csv);;All Files (*)")
        if path:
            self.input_work_log.setText(path)
            
    def _browse_error_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Error Log File", self.input_error_log.text(), "Text Files (*.txt *.log);;All Files (*)")
        if path:
            self.input_error_log.setText(path)
            
    def _save_options(self):
        config.set_work_log_path(self.input_work_log.text())
        config.set_error_log_path(self.input_error_log.text())
        config.settings.setValue("github_repo", self.input_github_repo.text().strip())
        
        setup_error_logging(self.input_error_log.text())
        QMessageBox.information(self, "Settings Saved", "Configuration saved successfully.")

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
        
    def _on_check_finished(self, tag, url, current_ver):
        self.btn_check_update.setEnabled(True)
        
        # Color current version red if mismatch, else green
        cur_color = "#00FF00" if current_ver == tag else "#FF4444"
        self.lbl_latest_ver.setText(f'Board: <span style="color: {cur_color};">{current_ver}</span> | Latest: <span style="color: #00FF00;">{tag}</span>')
        self.lbl_update_status.setText("Update available.")
        self.latest_uf2_url = url
        self.btn_download_update.setEnabled(True)
        
    def _on_check_error(self, err_msg):
        self.btn_check_update.setEnabled(True)
        self.lbl_update_status.setText(f"Check failed: {err_msg}")
        self.lbl_latest_ver.setText("Board: Unknown | Latest: Error")

    def _on_download_update(self):
        if not self.latest_uf2_url:
            return
            
        reply = QMessageBox.information(
            self, 
            "Firmware Update", 
            "Please follow these steps:\n\n"
            "1. Unplug the RP2040 board from the USB port.\n"
            "2. Hold down the BOOTSEL button on the RP2040.\n"
            "3. While holding the button, plug the USB back into the PC.\n"
            "4. Release the button.\n\n"
            "Click OK once you have plugged it in (or click OK first and plug it in within 30 seconds).",
            QMessageBox.Ok | QMessageBox.Cancel
        )
        
        if reply != QMessageBox.Ok:
            return
            
        self.btn_download_update.setEnabled(False)
        self.btn_check_update.setEnabled(False)
        
        self.dl_worker = DownloadUpdateWorker(self.latest_uf2_url)
        self.dl_worker.progress.connect(self.lbl_update_status.setText)
        self.dl_worker.finished.connect(self._on_download_finished)
        self.dl_worker.start()
        
    def _on_download_finished(self, success, msg):
        self.btn_download_update.setEnabled(True)
        self.btn_check_update.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "Update Success", msg + "\n\nPress OK to verify the new version.")
            self.lbl_update_status.setText("Verifying new version...")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1000, self._on_check_update)
        else:
            QMessageBox.warning(self, "Update Failed", msg)
            self.lbl_update_status.setText("Update failed.")
