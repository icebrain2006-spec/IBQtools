from PySide6.QtWidgets import QProgressBar
from PySide6.QtCore import Qt, Signal

class ClickableProgressBar(QProgressBar):
    clicked = Signal(int)
    
    def __init__(self, ch_idx: int, parent=None):
        super().__init__(parent)
        self.ch_idx = ch_idx
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ch_idx)
        super().mousePressEvent(event)
