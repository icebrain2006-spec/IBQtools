from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLineEdit, QPushButton, QTextBrowser, QFileDialog, QLabel, QComboBox, QProgressBar, QMessageBox)
from PySide6.QtCore import Qt
import serial.tools.list_ports
from updater_thread import UploadWorker

class UploadTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox("SLFS Data Upload (RP2040 Flash)")
        glayout = QVBoxLayout(group)
        
        # COM Port Selection
        com_layout = QHBoxLayout()
        com_layout.addWidget(QLabel("RP2040 COM Port:"))
        self.combo_port = QComboBox()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        com_layout.addWidget(self.combo_port)
        com_layout.addWidget(self.btn_refresh)
        com_layout.addStretch()
        glayout.addLayout(com_layout)
        
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
        
        self.btn_upload = QPushButton("UPLOAD TO RP2040")
        self.btn_upload.setObjectName("startBtn")
        self.btn_upload.clicked.connect(self.start_upload)
        
        action_layout.addWidget(self.progress_bar, stretch=1)
        action_layout.addWidget(self.btn_upload)
        glayout.addLayout(action_layout)
        
        layout.addWidget(group)
        
        self.upload_console = QTextBrowser()
        layout.addWidget(self.upload_console, stretch=1)
        
        self.refresh_ports()

    def refresh_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.combo_port.addItem(p.device)
            
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

    def start_upload(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.btn_upload.setText("UPLOAD TO RP2040")
            self.btn_upload.setStyleSheet("")
            return
            
        port = self.combo_port.currentText()
        file_path = self.upload_file_path.text().strip()
        
        if not port:
            QMessageBox.warning(self, "Warning", "Please select a COM port.")
            return
            
        if not file_path:
            QMessageBox.warning(self, "Warning", "Please select an SLFS file.")
            return
            
        self.upload_console.clear()
        self.progress_bar.setValue(0)
        self.btn_upload.setText("STOP UPLOAD")
        self.btn_upload.setStyleSheet("background-color: #FF4444; color: white;")
        
        self.worker = UploadWorker(port, file_path)
        self.worker.log_msg.connect(self.log_msg)
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self._on_upload_finished)
        self.worker.start()
        
    def _on_upload_finished(self, success):
        self.btn_upload.setText("UPLOAD TO RP2040")
        self.btn_upload.setStyleSheet("")
        if success:
            self.log_msg("[SUCCESS] Upload Process Completed Successfully!")
        else:
            self.log_msg("[ERROR] Upload Process Failed or Stopped.")
