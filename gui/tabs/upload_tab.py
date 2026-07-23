from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLineEdit, QPushButton, QTextBrowser)

class UploadTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox("SLFS Data Upload (RP2040 Flash)")
        glayout = QVBoxLayout(group)
        
        file_layout = QHBoxLayout()
        self.upload_file_path = QLineEdit()
        self.upload_file_path.setPlaceholderText("Select .slfs file...")
        self.btn_browse = QPushButton("Browse")
        file_layout.addWidget(self.upload_file_path)
        file_layout.addWidget(self.btn_browse)
        
        glayout.addLayout(file_layout)
        
        self.btn_upload = QPushButton("UPLOAD TO RP2040")
        self.btn_upload.setObjectName("startBtn")
        glayout.addWidget(self.btn_upload)
        
        layout.addWidget(group)
        
        self.upload_console = QTextBrowser()
        layout.addWidget(self.upload_console, stretch=1)
