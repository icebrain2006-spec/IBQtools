import os
import shutil
import tempfile
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLineEdit, QPushButton, QFormLayout, QMessageBox,
                               QFileDialog, QLabel, QProgressBar, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox)
from PySide6.QtCore import QThread, Signal, Qt
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from widgets import get_available_ports
from config import config, setup_error_logging
from fw_updater import get_latest_github_release, download_file, find_rp2040_drive
from updater_thread import get_fw_version

class CheckUpdateWorker(QThread):
    finished = Signal(str, str, list, list) # tag_name, url, versions, active_ports
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
            active_ports, _ = get_available_ports(include_none=False)
            active_ports = [p for p in active_ports if p != "Select COM"]
                
            versions = []
            valid_ports = []
            for port in active_ports:
                ver = get_fw_version(port)
                if ver:
                    versions.append(ver)
                    valid_ports.append(port)
                    
            if tag and url:
                self.finished.emit(tag, url, versions, valid_ports)
            else:
                self.error.emit("Could not find a valid .uf2 release.")
        except Exception as e:
            self.error.emit(str(e))

def send_software_bootsel_reboot(target_port=None, progress_signal=None):
    import serial.tools.list_ports
    import struct
    import time
    
    def crc16_calculate(data):
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc
        
    found = False
    for p in serial.tools.list_ports.comports():
        if target_port and p.device != target_port:
            continue
        if "USB" in str(p.hwid).upper() or "USB" in str(p.description).upper():
            try:
                ser = serial.Serial(p.device, 115200, timeout=1.0)
                cmd = 0x02 # CMD_REBOOT_BOOTSEL
                payload = b""
                total_len = 1 + len(payload)
                header = struct.pack(">B H B", 0x02, total_len, cmd)
                crc_data = bytes([cmd]) + payload
                crc = crc16_calculate(crc_data)
                footer = struct.pack(">H B", crc, 0x03)
                packet = header + payload + footer
                ser.write(packet)
                ser.close()
                if progress_signal:
                    progress_signal.emit(f"Sent BOOTSEL reset to {p.device}")
                found = True
            except Exception as e:
                if progress_signal:
                    progress_signal.emit(f"Failed to reset {p.device}: {e}")
    if found:
        time.sleep(2.0) # Wait for it to remount as a drive
    return found

class DownloadUpdateWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str) # success, message
    
    def __init__(self, url=None, local_file=None):
        super().__init__()
        self.url = url
        self.local_file = local_file
        
    def run(self):
        if self.local_file:
            self.progress.emit("Using local .uf2 file...")
            dest_path = self.local_file
        else:
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


class CsvViewerDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"CSV Viewer - {os.path.basename(file_path)}")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        
        # Search Bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to filter logs by date, SN, result, etc...")
        self.search_input.textChanged.connect(self._filter_table)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1A1A1A;
                color: #E0E0E0;
                gridline-color: #444444;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #FFFFFF;
                padding: 4px;
                border: 1px solid #444444;
            }
        """)
        layout.addWidget(self.table)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)
        
        self._load_csv(file_path)
        
    def _load_csv(self, file_path):
        try:
            with open(file_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                data = list(reader)
                
            if not data:
                return
                
            self.table.setRowCount(len(data))
            self.table.setColumnCount(max(len(row) for row in data))
            
            for row_idx, row_data in enumerate(data):
                for col_idx, col_data in enumerate(row_data):
                    # Replace " - " with a newline to force wrapping in range cells
                    if " - " in col_data:
                        col_data = col_data.replace(" - ", "\n~\n")
                        
                    item = QTableWidgetItem(col_data)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row_idx, col_idx, item)
            
            self.table.resizeColumnsToContents()
            for col in range(self.table.columnCount()):
                if self.table.columnWidth(col) > 150:
                    self.table.setColumnWidth(col, 150)
            self.table.resizeRowsToContents()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load CSV: {e}")
            
    def _filter_table(self, text):
        search_text = text.lower()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True
                    break
            # Optional: Always show empty rows or header-like rows? 
            # For simplicity, if search_text is empty, all rows match.
            self.table.setRowHidden(row, not match)

class OptionsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.latest_uf2_url = None
        self._init_ui()
        
    def _init_ui(self):
        layout_options = QVBoxLayout(self)
        
        # --- Data Logging Settings ---
        group_log_settings = QGroupBox("Data Logging Settings (CSV)")
        layout_log = QFormLayout(group_log_settings)
        
        self.input_work_log = QLineEdit()
        self.btn_browse_work = QPushButton("Browse...")
        self.btn_view_work = QPushButton("Viewer")
        work_layout = QHBoxLayout()
        work_layout.addWidget(self.input_work_log)
        work_layout.addWidget(self.btn_browse_work)
        work_layout.addWidget(self.btn_view_work)
        
        self.input_cal_log = QLineEdit()
        self.btn_browse_cal = QPushButton("Browse...")
        self.btn_view_cal = QPushButton("Viewer")
        cal_layout = QHBoxLayout()
        cal_layout.addWidget(self.input_cal_log)
        cal_layout.addWidget(self.btn_browse_cal)
        cal_layout.addWidget(self.btn_view_cal)
        
        self.input_error_log = QLineEdit()
        self.btn_browse_error = QPushButton("Browse...")
        error_layout = QHBoxLayout()
        error_layout.addWidget(self.input_error_log)
        error_layout.addWidget(self.btn_browse_error)
        
        layout_log.addRow("Work Log:", work_layout)
        layout_log.addRow("Calibration Log:", cal_layout)
        
        # --- Error & Debug Settings ---
        group_error_settings = QGroupBox("Error & Debug Settings")
        layout_error = QFormLayout(group_error_settings)
        
        layout_error.addRow("Error Log (TXT):", error_layout)
        
        self.cb_global_debug_log = QCheckBox("Show Detailed / Debug Logs in Console (All Tabs)")
        self.cb_global_debug_log.setChecked(config.settings.value("global_debug_log_en", "false") == "true")
        layout_error.addRow("Console Output:", self.cb_global_debug_log)
        
        # --- Production Settings ---
        group_prod_settings = QGroupBox("Production Settings")
        layout_prod = QFormLayout(group_prod_settings)
        
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QKeySequenceEdit
        self.input_hotkey = QKeySequenceEdit()
        self.input_hotkey.setKeySequence(QKeySequence(config.get_start_hotkey()))
        self.input_hotkey.setToolTip("Click here and press the desired hotkey combination (e.g., Space)")
        layout_prod.addRow("Quick Start Hotkey:", self.input_hotkey)
        
        self.btn_save_options = QPushButton("Save Settings")
        
        layout_options.addWidget(group_log_settings)
        layout_options.addWidget(group_error_settings)
        layout_options.addWidget(group_prod_settings)
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
        
        self.btn_flash_local = QPushButton("Flash Local .uf2")
        self.btn_flash_local.setObjectName("startBtn")
        
        btn_layout.addWidget(self.btn_check_update)
        btn_layout.addWidget(self.btn_download_update)
        btn_layout.addWidget(self.btn_flash_local)
        layout_fw.addLayout(btn_layout)
        
        self.lbl_update_status = QLabel("Ready.")
        layout_fw.addWidget(self.lbl_update_status)
        
        layout_options.addWidget(group_fw)
        
        layout_options.addStretch()
        
        # Connections
        self.input_work_log.setText(config.get_work_log_path())
        self.input_cal_log.setText(config.get_cal_log_path())
        self.input_error_log.setText(config.get_error_log_path())
        
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
        if not seq: seq = "Space" # Default fallback
        config.set_start_hotkey(seq)
        
        config.settings.sync()
        
        # Also notify main window to update its shortcut
        # We can find the main window and call a method
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
            self.lbl_latest_ver.setText(f'Board: Unknown | Latest: <span style="color: #00FF00;">{tag}</span>')
            self.lbl_update_status.setText("No boards found.")
            return
            
        ver_strs = []
        for p, v in zip(active_ports, versions):
            color = "#00FF00" if v == tag else "#FF4444"
            ver_strs.append(f'{p}(<span style="color: {color};">{v}</span>)')
            
        self.lbl_latest_ver.setText(f'Boards: {", ".join(ver_strs)} | Latest: <span style="color: #00FF00;">{tag}</span>')
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
        if not hasattr(self, 'boards_to_update') or not self.boards_to_update:
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
        send_software_bootsel_reboot(target_port=port)
        
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
        if not hasattr(self, 'boards_to_update') or not self.boards_to_update:
            QMessageBox.information(self, "No boards", "Please click 'Check Update' first to scan connected boards.")
            return
            
        self.update_queue = list(self.boards_to_update)
        self._process_next_board(is_local=True, local_path=path)
        
    def _on_dl_progress(self, msg):
        self.lbl_update_status.setText(msg)
        
    def _on_dl_finished(self, success, msg):
        if success:
            self.lbl_update_status.setText(f"Done: {msg}")
            if hasattr(self, 'update_queue') and self.update_queue:
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
