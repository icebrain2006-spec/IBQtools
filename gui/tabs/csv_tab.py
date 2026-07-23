from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLineEdit, QPushButton, QTextBrowser)

class CsvTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        group = QGroupBox("CSV to SLFS Generation")
        glayout = QVBoxLayout(group)
        
        file_layout = QHBoxLayout()
        self.csv_file_path = QLineEdit()
        self.csv_file_path.setPlaceholderText("Select .csv file...")
        self.btn_csv_browse = QPushButton("Browse")
        file_layout.addWidget(self.csv_file_path)
        file_layout.addWidget(self.btn_csv_browse)
        
        glayout.addLayout(file_layout)
        
        self.btn_convert = QPushButton("GENERATE SLFS")
        self.btn_convert.setObjectName("startBtn")
        glayout.addWidget(self.btn_convert)
        
        layout.addWidget(group)
        
        self.csv_console = QTextBrowser()
        layout.addWidget(self.csv_console, stretch=1)
