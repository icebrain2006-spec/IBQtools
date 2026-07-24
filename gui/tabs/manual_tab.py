import serial
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QGridLayout, QLabel, QComboBox, QLineEdit, 
                               QPushButton, QTextBrowser, QMessageBox)
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from updater_thread import make_packet, parse_response, CMD_I2C_RAW, RESP_OK
from tabs.updater_tab import PortComboBox
import serial.tools.list_ports
import re

class ManualTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        ctrl_group = QGroupBox("Command Configuration")
        ctrl_layout = QGridLayout(ctrl_group)
        
        ctrl_layout.addWidget(QLabel("COM Port:"), 0, 0)
        self.man_port = PortComboBox()
        
        # Initial population
        active_ports = []
        for p in serial.tools.list_ports.comports():
            hwid = str(p.hwid).upper()
            desc = str(p.description).upper()
            if "BTHENUM" in hwid or "BLUETOOTH" in desc or "BTHENUM" in desc: continue
            if "USB" not in hwid and "USB" not in desc: continue
            active_ports.append(p.device)
            
        if active_ports:
            self.man_port.addItems(active_ports)
        else:
            self.man_port.addItem("None")
            
        ctrl_layout.addWidget(self.man_port, 0, 1)
        
        ctrl_layout.addWidget(QLabel("Channel (1-6):"), 0, 2)
        self.man_ch = QComboBox()
        self.man_ch.addItems(["1","2","3","4","5","6"])
        ctrl_layout.addWidget(self.man_ch, 0, 3)
        
        ctrl_layout.addWidget(QLabel("I2C Address (Hex):"), 1, 0)
        self.man_addr = QLineEdit("0B")
        addr_validator = QRegularExpressionValidator(QRegularExpression("^[0-9a-fA-F]{1,2}$"))
        self.man_addr.setValidator(addr_validator)
        ctrl_layout.addWidget(self.man_addr, 1, 1)
        
        ctrl_layout.addWidget(QLabel("Command Mode:"), 1, 2)
        self.man_mode = QComboBox()
        self.man_mode.addItems(["RAW I2C TRX", "SMBus Read Word", "SMBus Read Block"])
        ctrl_layout.addWidget(self.man_mode, 1, 3)
        
        ctrl_layout.addWidget(QLabel("TX Data (Hex space separated):"), 2, 0)
        self.man_tx = QLineEdit("08")
        self.man_tx.textEdited.connect(self._format_tx_data)
        ctrl_layout.addWidget(self.man_tx, 2, 1, 1, 3)
        
        ctrl_layout.addWidget(QLabel("Expected RX Bytes:"), 3, 0)
        self.man_rx_len = QLineEdit("2")
        ctrl_layout.addWidget(self.man_rx_len, 3, 1)
        
        self.btn_send_cmd = QPushButton("SEND COMMAND")
        self.btn_send_cmd.setObjectName("startBtn")
        self.btn_send_cmd.clicked.connect(self._send_manual_command)
        ctrl_layout.addWidget(self.btn_send_cmd, 3, 3)
        
        layout.addWidget(ctrl_group)
        
        self.man_console = QTextBrowser()
        self.man_console.append("Ready for manual I2C commands.")
        layout.addWidget(self.man_console, stretch=1)

    def _format_tx_data(self, text):
        clean = re.sub(r'[^0-9a-fA-F]', '', text)
        spaced = ' '.join(clean[i:i+2] for i in range(0, len(clean), 2)).upper()
        
        self.man_tx.blockSignals(True)
        self.man_tx.setText(spaced)
        self.man_tx.blockSignals(False)

    def _send_manual_command(self):
        port = self.man_port.currentText()
        ch = int(self.man_ch.currentText())
        
        try:
            addr = int(self.man_addr.text(), 16)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid I2C Address (must be Hex)")
            return
            
        try:
            rx_len = int(self.man_rx_len.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid RX Length (must be integer)")
            return
            
        tx_str = self.man_tx.text().strip()
        tx_data = []
        if tx_str:
            try:
                tx_data = [int(x, 16) for x in tx_str.split()]
            except ValueError:
                QMessageBox.warning(self, "Input Error", "Invalid TX Data (must be space-separated Hex)")
                return
                
        tx_len = len(tx_data)
        
        payload = bytes([ch, addr, tx_len, rx_len]) + bytes(tx_data)
        packet = make_packet(CMD_I2C_RAW, payload)
        
        self.man_console.append(f"\n[TX] Port:{port} CH:{ch} Addr:{addr:#04x} TX:{tx_data} Expected_RX:{rx_len}")
        
        try:
            with serial.Serial(port, 115200, timeout=1.0) as ser:
                ser.write(packet)
                rx = ser.read(128)
                
                if not rx:
                    self.man_console.append("[ERROR] No response from RP2040 (Timeout)")
                    return
                    
                cmd, resp_payload = parse_response(rx)
                if cmd == CMD_I2C_RAW:
                    status = resp_payload[0]
                    if status == RESP_OK:
                        rx_bytes = resp_payload[1:]
                        hex_rx = " ".join([f"{b:02X}" for b in rx_bytes])
                        self.man_console.append(f"[RX] Success: {hex_rx}")
                    else:
                        self.man_console.append(f"[ERROR] I2C Error Code: {status:#04x}")
                else:
                    self.man_console.append(f"[ERROR] Unexpected response command: {cmd:#04x}")
                    
        except Exception as e:
            self.man_console.append(f"[CRITICAL] Serial Error: {e}")
