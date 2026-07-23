from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLineEdit, QPushButton, QTextBrowser, QFileDialog, QLabel, QListWidget, QProgressBar, QMessageBox)
from PySide6.QtCore import Qt
import serial.tools.list_ports
from updater_thread import UploadWorker, ScanWorker

class UploadTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.scan_worker = None
        self.target_ports = []
        self.current_upload_idx = 0
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox("SLFS Batch Upload (Multi-Board)")
        glayout = QVBoxLayout(group)
        
        # COM Port Scanning
        com_layout = QHBoxLayout()
        com_layout.addWidget(QLabel("Detected RP2040 Boards:"))
        self.btn_scan = QPushButton("SCAN BOARDS")
        self.btn_scan.clicked.connect(self.start_scan)
        com_layout.addStretch()
        com_layout.addWidget(self.btn_scan)
        glayout.addLayout(com_layout)
        
        self.list_ports = QListWidget()
        self.list_ports.setMaximumHeight(80)
        glayout.addWidget(self.list_ports)
        
        # File Selection
        file_layout = QHBoxLayout()
        self.upload_file_path = QLineEdit()
        self.upload_file_path.setPlaceholderText("Select .slfs file...")
        self.upload_file_path.setReadOnly(True)
        self.btn_browse = QPushButton("Browse")
        self.btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(self.upload_file_path)
        file_layout.addWidget(self.btn_browse)
        glayout.addLayout(file_layout)
        
        # Progress and Upload
        action_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        
        self.btn_upload = QPushButton("UPLOAD TO ALL")
        self.btn_upload.setObjectName("startBtn")
        self.btn_upload.clicked.connect(self.start_batch_upload)
        
        action_layout.addWidget(self.progress_bar, stretch=1)
        action_layout.addWidget(self.btn_upload)
        glayout.addLayout(action_layout)
        
        layout.addWidget(group)
        
        self.upload_console = QTextBrowser()
        layout.addWidget(self.upload_console, stretch=1)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select SLFS File", "", "SLFS Files (*.slfs);;All Files (*)")
        if file_path:
            self.upload_file_path.setText(file_path)
            
    def log_msg(self, msg):
        if "ERROR" in msg or "Failed" in msg:
            self.upload_console.append(f'<span style="color: #FF4444;">{msg}</span>')
        elif "SUCCESS" in msg:
            self.upload_console.append(f'<span style="color: #00FF00;">{msg}</span>')
        else:
            self.upload_console.append(msg)

    def start_scan(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            return
            
        self.btn_scan.setText("STOP SCAN")
        self.list_ports.clear()
        self.upload_console.clear()
        self.target_ports = []
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Scanning...")
        ports = []
        for p in serial.tools.list_ports.comports():
            hwid = str(p.hwid).upper()
            desc = str(p.description).upper()
            # Skip Bluetooth or virtual ports that might cause serial.Serial to hang
            if "BTHENUM" in hwid or "BLUETOOTH" in desc or "USB" not in hwid:
                self.log_msg(f"Skipping non-USB/BT port: {p.device} ({p.description})")
                continue
            ports.append(p.device)
            
        self.scan_worker = ScanWorker(ports)
        self.scan_worker.log_msg.connect(self.log_msg)
        self.scan_worker.progress_updated.connect(self.progress_bar.setValue)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.start()
        
    def _on_scan_finished(self, valid_ports):
        self.btn_scan.setText("SCAN BOARDS")
        self.progress_bar.setFormat("%p%")
        self.target_ports = valid_ports
        for p in valid_ports:
            self.list_ports.addItem(p)
        if not valid_ports:
            self.log_msg("[WARNING] No RP2040 boards detected.")
        else:
            self.log_msg(f"[INFO] Found {len(valid_ports)} valid RP2040 board(s).")

    def start_batch_upload(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.btn_upload.setText("UPLOAD TO ALL")
            self.btn_upload.setStyleSheet("")
            return
            
        if not self.target_ports:
            QMessageBox.warning(self, "Warning", "No boards scanned/detected. Please scan first.")
            return
            
        file_path = self.upload_file_path.text().strip()
        if not file_path:
            QMessageBox.warning(self, "Warning", "Please select an SLFS file.")
            return
            
        self.upload_console.clear()
        self.btn_upload.setText("STOP UPLOAD")
        self.btn_upload.setStyleSheet("background-color: #FF4444; color: white;")
        
        self.current_upload_idx = 0
        self._upload_next()
        
    def _upload_next(self):
        if self.current_upload_idx >= len(self.target_ports):
            self.btn_upload.setText("UPLOAD TO ALL")
            self.btn_upload.setStyleSheet("")
            self.log_msg("[SUCCESS] Batch Upload Completed for all boards!")
            self.progress_bar.setFormat("Done")
            return
            
        port = self.target_ports[self.current_upload_idx]
        file_path = self.upload_file_path.text().strip()
        
        self.log_msg(f"\n--- Starting Upload for {port} ({self.current_upload_idx + 1}/{len(self.target_ports)}) ---")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"[{port}] %p%")
        
        self.worker = UploadWorker(port, file_path)
        self.worker.log_msg.connect(self.log_msg)
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self._on_single_upload_finished)
        self.worker.start()
        
    def _on_single_upload_finished(self, success):
        if not success:
            self.log_msg(f"[ERROR] Upload Failed or Stopped on {self.target_ports[self.current_upload_idx]}.")
            self.btn_upload.setText("UPLOAD TO ALL")
            self.btn_upload.setStyleSheet("")
            self.progress_bar.setFormat("Error")
            return
            
        self.current_upload_idx += 1
        self._upload_next()
