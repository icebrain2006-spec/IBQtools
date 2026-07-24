from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class CalibrationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        label = QLabel("Calibration configuration and controls will go here.")
        layout.addWidget(label)
