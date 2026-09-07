import binascii
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLineEdit, QPushButton, QTextBrowser, QLabel, QMessageBox
)
from PySide6.QtCore import QThread, Signal

from gui.widgets import PortComboBox
from gui.updater_thread import make_packet, parse_response
from gui.styles import Colors, Styles
from gui.utils import is_error_status
from gui.strings import UIStrings


class ManualCommandWorker(QThread):
    """Background worker for sending manual HEX commands over Serial without blocking UI."""
    finished = Signal(bool, str, bytes)  # success, formatted_log, raw_response

    def __init__(self, port: str, hex_str: str):
        super().__init__()
        self.port = port
        self.hex_str = hex_str

    def run(self):
        try:
            import serial
            cleaned_hex = self.hex_str.replace(" ", "")
            raw_bytes = bytes.fromhex(cleaned_hex)
            
            if len(raw_bytes) == 0:
                self.finished.emit(False, "Error: Empty byte array.", b"")
                return

            cmd_byte = raw_bytes[0]
            payload = raw_bytes[1:]
            packet = make_packet(cmd_byte, payload)

            with serial.Serial(self.port, 115200, timeout=1.0) as ser:
                ser.write(packet)
                resp = ser.read(128)

            if not resp:
                self.finished.emit(False, "Error: Serial Read Timeout (No response from board).", b"")
                return

            resp_cmd, resp_payload = parse_response(resp)
            
            if resp_cmd is not None:
                hex_resp = " ".join([f"{b:02X}" for b in resp_payload])
                log_msg = f"[SUCCESS] Response Cmd: 0x{resp_cmd:02X} | Payload({len(resp_payload)}B): {hex_resp}"
                self.finished.emit(True, log_msg, resp_payload)
            else:
                hex_raw = " ".join([f"{b:02X}" for b in resp])
                log_msg = f"[WARN] Invalid Packet CRC/Header. Raw ({len(resp)}B): {hex_raw}"
                self.finished.emit(False, log_msg, resp)

        except ValueError as ve:
            self.finished.emit(False, f"Error: Invalid Hex String format: {ve}", b"")
        except Exception as e:
            self.finished.emit(False, f"Error: Communication failure on {self.port}: {e}", b"")


class ManualTab(QWidget):
    """Manual Serial Command Test & Debugging Tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        group_man = QGroupBox(UIStrings.get("GRP_MANUAL_CONTROL"))
        layout_man = QVBoxLayout(group_man)

        # Port Selection
        layout_port = QHBoxLayout()
        layout_port.addWidget(QLabel(UIStrings.get("LBL_COM_PORT")))
        self.combo_ports = PortComboBox()
        layout_port.addWidget(self.combo_ports, 1)

        self.btn_refresh = QPushButton(UIStrings.get("BTN_REFRESH"))
        self.btn_refresh.clicked.connect(self.combo_ports.refresh_ports)
        layout_port.addWidget(self.btn_refresh)
        layout_man.addLayout(layout_port)

        # HEX Input Line
        layout_input = QHBoxLayout()
        layout_input.addWidget(QLabel(UIStrings.get("LBL_HEX_INPUT")))
        self.input_man_hex = QLineEdit()
        self.input_man_hex.setPlaceholderText(UIStrings.get("PH_HEX_INPUT"))
        self.input_man_hex.returnPressed.connect(self._send_manual_command)
        layout_input.addWidget(self.input_man_hex)

        self.btn_man_send = QPushButton(UIStrings.get("BTN_SEND_COMMAND"))
        self.btn_man_send.setObjectName("startBtn")
        self.btn_man_send.clicked.connect(self._send_manual_command)
        layout_input.addWidget(self.btn_man_send)
        layout_man.addLayout(layout_input)

        layout.addWidget(group_man)

        # Console Output
        self.man_console = QTextBrowser()
        self.man_console.setStyleSheet(Styles.LOG_CONSOLE)
        layout.addWidget(self.man_console, stretch=1)

    def _send_manual_command(self):
        port = self.combo_ports.currentText()
        if not port or port == "Select COM":
            QMessageBox.warning(self, "Error", "Please select a valid COM port first.")
            return

        hex_str = self.input_man_hex.text().strip()
        if not hex_str:
            QMessageBox.warning(self, "Error", "Please enter a HEX command string.")
            return

        self.btn_man_send.setEnabled(False)
        self.man_console.append(f"\n>>> Sending to {port}: {hex_str}")

        self.worker = ManualCommandWorker(port, hex_str)
        self.worker.finished.connect(self._on_command_finished)
        self.worker.start()

    def _on_command_finished(self, success: bool, log_msg: str, raw_payload: bytes):
        self.btn_man_send.setEnabled(True)
        if success:
            self.man_console.append(f'<span style="color: {Colors.HEX_PASS_GREEN};">{log_msg}</span>')
        elif is_error_status(log_msg):
            from gui.config import log_error
            log_error(f"[Manual Debug] {log_msg}")
            self.man_console.append(f'<span style="color: {Colors.HEX_FAIL};">{log_msg}</span>')
        else:
            self.man_console.append(log_msg)
