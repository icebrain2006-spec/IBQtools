import sys
import os
import serial
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QComboBox, QPushButton, QLabel, QMessageBox)
from PySide6.QtCore import Qt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from widgets import PortComboBox
from updater_thread import make_packet, CMD_RELAY_SET

class RelayWindow(QWidget):
    def __init__(self, parent=None):
        # parent를 None으로 강제하여 독립된 창으로 만듭니다.
        super().__init__(None)
        self.setWindowTitle("Mini Relay")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.Tool) # 툴 윈도우 스타일 추가
        
        # 메인 창의 기본 테마를 불러오되 살짝 다르게(고급스러운 다크 블루/퍼플 톤) 오버라이드
        qss_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                base_style = f.read()
                custom_style = base_style + """
                QWidget { background-color: #16161A; } 
                QGroupBox { background-color: #1D1D22; border: 1px solid #2B2B33; }
                """
                self.setStyleSheet(custom_style)

        self._init_ui()
        self.refresh_ports()
        
        # UI 구성이 끝난 후 현재 크기를 강제 고정하여 절대 변하지 않게 함
        self.adjustSize()
        self.setFixedSize(self.sizeHint().width() + 10, self.sizeHint().height() + 20)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        # layout.setSizeConstraint(QVBoxLayout.SetFixedSize) # 완전 삭제

        # COM Port Selection
        group_port = QGroupBox("Connection")
        layout_port = QVBoxLayout(group_port)
        layout_port.setContentsMargins(5, 5, 5, 5)
        layout_port.setSpacing(2)
        
        row_com = QHBoxLayout()
        row_com.setContentsMargins(0,0,0,0)
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
        for i in range(1, 7):
            btn = QPushButton(f"CH {i} : OFF")
            btn.setCheckable(True)
            btn.setMinimumWidth(130) # 글자 길이에 흔들리지 않게 최소 너비 고정
            btn.setMinimumHeight(32) # 글자가 잘리지 않게 최소 높이 고정
            # Apply some styling based on state using QSS
            btn.setStyleSheet("""
                QPushButton { font-weight: bold; padding: 4px; margin: 0px; background-color: #26262B; color: #BBBBBB; border: 1px solid #3A3A44; }
                QPushButton:hover { background-color: #35353C; }
                QPushButton:checked { background-color: #00BFA5; color: #FFFFFF; border: 1px solid #1DE9B6; }
            """)
            btn.toggled.connect(self.on_relay_toggled)
            self.ch_buttons.append(btn)
            layout_ch.addWidget(btn)
            
        layout.addWidget(group_ch)

        # Status
        self.lbl_status = QLabel("Ready\n") # 미리 2줄 공간 확보
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setMinimumHeight(32) # 상태 메시지가 2줄로 넘어가도 창이 커지지 않도록 고정
        font = self.lbl_status.font()
        font.setPointSize(8)
        self.lbl_status.setFont(font)
        layout.addWidget(self.lbl_status)

    def refresh_ports(self):
        if hasattr(self, 'combo_ports'):
            self.combo_ports.refresh_ports()

    def on_relay_toggled(self, checked):
        # Update text for the button that was just clicked
        sender_btn = self.sender()
        if sender_btn:
            ch_num = self.ch_buttons.index(sender_btn) + 1
            if checked:
                sender_btn.setText(f"CH {ch_num} : ON")
            else:
                sender_btn.setText(f"CH {ch_num} : OFF")

        # Calculate full mask based on all buttons
        mask = 0
        for i, btn in enumerate(self.ch_buttons):
            if btn.isChecked():
                mask |= (1 << i)
        
        self._send_relay_cmd(mask)

    def _send_relay_cmd(self, mask):
        port = self.combo_ports.currentText()
        if not port:
            QMessageBox.warning(self, "Error", "Please select a COM port first.")
            # Revert the button state visually if we failed? 
            # (Optional, but good UX if connection fails)
            return

        packet = make_packet(CMD_RELAY_SET, bytes([mask]))
        
        try:
            with serial.Serial(port, 115200, timeout=1.0) as ser:
                ser.write(packet)
                import time
                time.sleep(0.1)
                
            state_str = f"Mask: 0x{mask:02X}"
            self.lbl_status.setText(f"Relays updated successfully ({state_str}).")
        except Exception as e:
            self.lbl_status.setText(f"Error: {e}")
            QMessageBox.critical(self, "Error", f"Failed to send command to {port}:\n{e}")
