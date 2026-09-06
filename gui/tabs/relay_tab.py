import os
import time
import serial
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QPushButton, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal

from gui.widgets import PortComboBox
from gui.updater_thread import make_packet, CMD_RELAY_SET
from gui.styles import Colors


class RelayCommandWorker(QThread):
    """Background worker for sending relay control commands over serial."""
    finished = Signal(bool, str)  # success, message

    def __init__(self, port: str, mask: int):
        super().__init__()
        self.port = port
        self.mask = mask

    def run(self):
        packet = make_packet(CMD_RELAY_SET, bytes([self.mask]))
        try:
            with serial.Serial(self.port, 115200, timeout=1.0) as ser:
                ser.write(packet)
                time.sleep(0.1)
            state_str = f"Mask: 0x{self.mask:02X}"
            self.finished.emit(True, f"Relays updated successfully ({state_str}).")
        except Exception as e:
            self.finished.emit(False, str(e))


class RelayWindow(QWidget):
    """Independent Mini Relay Control Window."""

    def __init__(self, parent=None):
        # parent를 None으로 강제하여 독립된 창으로 설정
        super().__init__(None)
        self.setWindowTitle("Mini Relay")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.Tool)
        
        # 메인 창의 기본 테마 적용 및 스타일 오버라이드
        qss_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                base_style = f.read()
                custom_style = base_style + f"""
                QWidget {{ background-color: {Colors.HEX_BG_DARK}; }} 
                QGroupBox {{ background-color: {Colors.HEX_BG_PANEL}; border: 1px solid {Colors.HEX_BORDER_DARK}; }}
                """
                self.setStyleSheet(custom_style)

        self.worker = None
        self._init_ui()
        self.refresh_ports()
        
        # UI 구성 완료 후 크기 고정
        self.adjustSize()
        self.setFixedSize(self.sizeHint().width() + 10, self.sizeHint().height() + 20)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # COM Port Selection
        group_port = QGroupBox("Connection")
        layout_port = QVBoxLayout(group_port)
        layout_port.setContentsMargins(5, 5, 5, 5)
        layout_port.setSpacing(2)
        
        row_com = QHBoxLayout()
        row_com.setContentsMargins(0, 0, 0, 0)
        row_com.addWidget(QLabel("COM:"))
        self.combo_ports = PortComboBox()
        row_com.addWidget(self.combo_ports, 1)
        layout_port.addLayout(row_com)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        layout_port.addWidget(self.btn_refresh)
        
        layout.addWidget(group_port)

        # Channel Toggle Buttons (Vertical)
        group_ch = QGroupBox("Relay Control")
        layout_ch = QVBoxLayout(group_ch)
        layout_ch.setContentsMargins(5, 5, 5, 5)
        layout_ch.setSpacing(2)
        
        self.ch_buttons = []
        btn_qss = f"""
            QPushButton {{ 
                font-weight: bold; 
                padding: 4px; 
                margin: 0px; 
                background-color: {Colors.HEX_BG_DARK}; 
                color: {Colors.HEX_WHITE}; 
                border: 1px solid {Colors.HEX_BORDER_DARK}; 
            }}
            QPushButton:hover {{ 
                background-color: {Colors.HEX_BORDER_LIGHT}; 
            }}
            QPushButton:checked {{ 
                background-color: #00897B; 
                color: {Colors.HEX_WHITE}; 
                border: 1px solid {Colors.HEX_PASS_GREEN}; 
            }}
        """
        for i in range(1, 7):
            btn = QPushButton(f"CH {i} : OFF")
            btn.setCheckable(True)
            btn.setMinimumWidth(130)
            btn.setMinimumHeight(32)
            btn.setStyleSheet(btn_qss)
            btn.toggled.connect(self.on_relay_toggled)
            self.ch_buttons.append(btn)
            layout_ch.addWidget(btn)
            
        layout.addWidget(group_ch)

        # Status Label
        self.lbl_status = QLabel("Ready\n")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setMinimumHeight(32)
        font = self.lbl_status.font()
        font.setPointSize(8)
        self.lbl_status.setFont(font)
        layout.addWidget(self.lbl_status)

    def refresh_ports(self):
        if hasattr(self, 'combo_ports'):
            self.combo_ports.refresh_ports()

    def on_relay_toggled(self, checked):
        sender_btn = self.sender()
        if sender_btn:
            ch_num = self.ch_buttons.index(sender_btn) + 1
            sender_btn.setText(f"CH {ch_num} : ON" if checked else f"CH {ch_num} : OFF")

        # Calculate mask from channel buttons
        mask = 0
        for i, btn in enumerate(self.ch_buttons):
            if btn.isChecked():
                mask |= (1 << i)
        
        self._send_relay_cmd(mask)

    def _send_relay_cmd(self, mask):
        port = self.combo_ports.currentText()
        if not port:
            QMessageBox.warning(self, "Error", "Please select a COM port first.")
            return

        self.lbl_status.setText("Sending relay command...")
        self.worker = RelayCommandWorker(port, mask)
        self.worker.finished.connect(lambda success, msg: self._on_cmd_finished(success, msg, port))
        self.worker.start()

    def _on_cmd_finished(self, success: bool, msg: str, port: str):
        self.lbl_status.setText(msg)
        if not success:
            QMessageBox.critical(self, "Error", f"Failed to send command to {port}:\n{msg}")
