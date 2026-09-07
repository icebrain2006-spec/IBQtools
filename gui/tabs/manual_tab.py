import re
import time
import serial
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLineEdit, QPushButton, QTextBrowser, QLabel, QComboBox,
    QCheckBox, QMessageBox
)
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression, QThread, Signal

from gui.widgets import PortComboBox
from gui.protocol import (
    make_packet, parse_response, CMD_SMBUS_CMD, CMD_I2C_RAW, RESP_OK
)
from gui.styles import Colors, Styles
from gui.utils import is_error_status
from gui.config import log_error
from gui.strings import UIStrings


class ManualCommandWorker(QThread):
    """Background worker for sending structured I2C/SMBus commands without blocking UI."""
    finished = Signal(bool, str, bytes)

    def __init__(self, port: str, ch: int, addr: int, mode: str, reg: int, tx_data: list[int], rx_len: int, use_pec: bool):
        super().__init__()
        self.port = port
        self.ch = ch
        self.addr = addr
        self.mode = mode
        self.reg = reg
        self.tx_data = tx_data
        self.rx_len = rx_len
        self.use_pec = use_pec

    def run(self):
        try:
            is_raw = (self.mode == "Raw I2C TRX")
            if is_raw:
                payload = bytes([self.ch, self.addr, len(self.tx_data), self.rx_len]) + bytes(self.tx_data)
                packet = make_packet(CMD_I2C_RAW, payload)
                expected_cmd = CMD_I2C_RAW
            else:
                is_read = 1 if "Read" in self.mode else 0
                if "Word" in self.mode:
                    data_len = 2
                elif "Byte" in self.mode:
                    data_len = 1
                elif "Read Block" in self.mode:
                    data_len = self.rx_len
                else:  # Write Block
                    data_len = len(self.tx_data)

                pec_val = 1 if self.use_pec else 0
                payload = bytes([self.ch, self.addr, self.reg, is_read, data_len, pec_val])
                if not is_read:
                    payload += bytes(self.tx_data)
                else:
                    payload += b'\x00'  # Dummy data byte to ensure payload >= 7 for firmware safety

                packet = make_packet(CMD_SMBUS_CMD, payload)
                expected_cmd = CMD_SMBUS_CMD

            with serial.Serial(self.port, 115200, timeout=1.0) as ser:
                ser.reset_input_buffer()
                ser.write(packet)
                resp = ser.read(256)

            if not resp:
                self.finished.emit(False, "[ERROR] Serial Read Timeout (No response from board).", b"")
                return

            resp_cmd, resp_payload = parse_response(resp)
            if resp_cmd != expected_cmd:
                hex_raw = " ".join([f"{b:02X}" for b in resp])
                self.finished.emit(False, f"[WARN] Unexpected Cmd 0x{resp_cmd:02X} (Raw: {hex_raw})", resp)
                return

            status = resp_payload[0]
            if status != RESP_OK:
                err_detail = resp_payload[1] if len(resp_payload) > 1 else 0
                self.finished.emit(False, f"[ERROR] Target NACK/HW Error (Status: 0x{status:02X}, Detail: 0x{err_detail:02X})", resp_payload)
                return

            # Success formatting (Firmware: [RESP_OK, Data...] for Word/Byte, [RESP_OK, Len, Data...] for Block)
            if is_raw:
                rx_data = resp_payload[2:] if len(resp_payload) >= 2 else b""
                hex_rx = " ".join([f"{b:02X}" for b in rx_data])
                log_msg = f"[RX] SUCCESS (Raw I2C) ➔ Bytes({len(rx_data)}): [{hex_rx}]"
            elif "Read" in self.mode:
                if "Word" in self.mode:
                    # Firmware returns: [RESP_OK, LowByte, HighByte]
                    rx_data = resp_payload[1:3]
                    hex_rx = " ".join([f"{b:02X}" for b in rx_data])
                    if len(rx_data) >= 2:
                        val_u16 = rx_data[0] | (rx_data[1] << 8)
                        val_s16 = val_u16 if val_u16 < 32768 else val_u16 - 65536
                        log_msg = f"[RX] SUCCESS ({self.mode}) ➔ Hex: [{hex_rx}] (0x{val_u16:04X}) | Dec: {val_u16} (Signed: {val_s16})"
                    else:
                        log_msg = f"[RX] SUCCESS ({self.mode}) ➔ Hex: [{hex_rx}]"
                elif "Byte" in self.mode:
                    # Firmware returns: [RESP_OK, ByteVal]
                    rx_data = resp_payload[1:2]
                    hex_rx = " ".join([f"{b:02X}" for b in rx_data])
                    val_u8 = rx_data[0] if rx_data else 0
                    log_msg = f"[RX] SUCCESS ({self.mode}) ➔ Hex: [{hex_rx}] | Dec: {val_u8} (0x{val_u8:02X})"
                else:  # Read Block
                    # Firmware returns: [RESP_OK, BlockLen, Data...]
                    actual_len = resp_payload[1] if len(resp_payload) > 1 else 0
                    rx_data = resp_payload[2:2 + actual_len]
                    hex_rx = " ".join([f"{b:02X}" for b in rx_data])
                    log_msg = f"[RX] SUCCESS (Read Block) ➔ Bytes({len(rx_data)}): [{hex_rx}]"
            else:
                log_msg = f"[RX] SUCCESS ({self.mode} OK)"

            self.finished.emit(True, log_msg, resp_payload)

        except Exception as e:
            self.finished.emit(False, f"[CRITICAL] Serial Communication Failure: {e}", b"")


class ManualTab(QWidget):
    """Structured Manual I2C / SMBus Command Test & Debugging Tab."""

    MODES = [
        "SMBus Read Word",
        "SMBus Read Block",
        "SMBus Read Byte",
        "SMBus Write Word",
        "SMBus Write Block",
        "SMBus Write Byte",
        "Raw I2C TRX"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # --- 1. Target Device Settings ---
        group_target = QGroupBox(UIStrings.get("GRP_MANUAL_TARGET"))
        layout_target = QHBoxLayout(group_target)

        layout_target.addWidget(QLabel(UIStrings.get("LBL_COM_PORT")))
        self.combo_ports = PortComboBox()
        layout_target.addWidget(self.combo_ports, 2)

        self.btn_refresh = QPushButton(UIStrings.get("BTN_REFRESH"))
        self.btn_refresh.clicked.connect(self.combo_ports.refresh_ports)
        layout_target.addWidget(self.btn_refresh)

        layout_target.addWidget(QLabel(UIStrings.get("LBL_CHANNEL")))
        self.combo_ch = QComboBox()
        self.combo_ch.addItems([f"CH {i}" for i in range(1, 7)])
        layout_target.addWidget(self.combo_ch, 1)

        layout_target.addWidget(QLabel(UIStrings.get("LBL_I2C_ADDR")))
        self.input_addr = QLineEdit("0B")
        self.input_addr.setValidator(QRegularExpressionValidator(QRegularExpression("^[0-9a-fA-F]{1,2}$")))
        self.input_addr.setMaximumWidth(60)
        layout_target.addWidget(self.input_addr)

        self.chk_pec = QCheckBox(UIStrings.get("CHK_USE_PEC"))
        layout_target.addWidget(self.chk_pec)

        layout.addWidget(group_target)

        # --- 2. Command Configuration ---
        group_cmd = QGroupBox(UIStrings.get("GRP_MANUAL_COMMAND"))
        grid = QGridLayout(group_cmd)

        grid.addWidget(QLabel(UIStrings.get("LBL_CMD_MODE")), 0, 0)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(self.MODES)
        self.combo_mode.currentTextChanged.connect(self._on_mode_changed)
        grid.addWidget(self.combo_mode, 0, 1)

        grid.addWidget(QLabel(UIStrings.get("LBL_REGISTER")), 0, 2)
        self.input_reg = QLineEdit("09")
        self.input_reg.setValidator(QRegularExpressionValidator(QRegularExpression("^[0-9a-fA-F]{1,2}$")))
        self.input_reg.setMaximumWidth(80)
        grid.addWidget(self.input_reg, 0, 3)

        grid.addWidget(QLabel(UIStrings.get("LBL_EXPECTED_RX")), 0, 4)
        self.input_rx_len = QLineEdit("2")
        self.input_rx_len.setValidator(QRegularExpressionValidator(QRegularExpression("^[0-9]{1,3}$")))
        self.input_rx_len.setMaximumWidth(80)
        grid.addWidget(self.input_rx_len, 0, 5)

        grid.addWidget(QLabel(UIStrings.get("LBL_WRITE_DATA")), 1, 0)
        self.input_tx_data = QLineEdit()
        self.input_tx_data.setPlaceholderText(UIStrings.get("PH_WRITE_DATA"))
        self.input_tx_data.textEdited.connect(self._format_hex_input)
        grid.addWidget(self.input_tx_data, 1, 1, 1, 3)

        btn_layout = QHBoxLayout()
        self.btn_send = QPushButton(UIStrings.get("BTN_SEND_COMMAND"))
        self.btn_send.setObjectName("startBtn")
        self.btn_send.clicked.connect(self._send_command)
        btn_layout.addWidget(self.btn_send)

        self.btn_clear = QPushButton(UIStrings.get("BTN_CLEAR_CONSOLE"))
        self.btn_clear.clicked.connect(self._clear_console)
        btn_layout.addWidget(self.btn_clear)
        grid.addLayout(btn_layout, 1, 4, 1, 2)

        layout.addWidget(group_cmd)

        # --- 3. Transaction Console ---
        self.man_console = QTextBrowser()
        self.man_console.setStyleSheet(Styles.LOG_CONSOLE)
        layout.addWidget(self.man_console, stretch=1)

        self._on_mode_changed(self.combo_mode.currentText())

    def _format_hex_input(self, text: str):
        clean = re.sub(r'[^0-9a-fA-F]', '', text)
        spaced = ' '.join(clean[i:i+2] for i in range(0, len(clean), 2)).upper()
        self.input_tx_data.blockSignals(True)
        self.input_tx_data.setText(spaced)
        self.input_tx_data.blockSignals(False)

    def _on_mode_changed(self, mode: str):
        is_write = "Write" in mode
        is_raw = (mode == "Raw I2C TRX")

        self.input_tx_data.setEnabled(is_write or is_raw)
        self.input_reg.setEnabled(not is_raw)

        if mode in ("SMBus Read Word", "SMBus Write Word"):
            self.input_rx_len.setText("2")
            self.input_rx_len.setEnabled(False)
        elif mode in ("SMBus Read Byte", "SMBus Write Byte"):
            self.input_rx_len.setText("1")
            self.input_rx_len.setEnabled(False)
        elif mode == "SMBus Read Block":
            self.input_rx_len.setText("32")
            self.input_rx_len.setEnabled(True)
        elif mode == "SMBus Write Block":
            self.input_rx_len.setText("0")
            self.input_rx_len.setEnabled(False)
        elif is_raw:
            self.input_rx_len.setEnabled(True)

    def _send_command(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Warning", "Previous command is still executing. Please wait.")
            return

        port = self.combo_ports.currentText().strip()
        if not port or port == "Select COM":
            QMessageBox.warning(self, "Error", "Please select a valid COM port first.")
            return

        ch_idx = self.combo_ch.currentIndex() + 1
        addr_str = self.input_addr.text().strip() or "0B"
        try:
            addr = int(addr_str, 16)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid I2C Address (must be Hex, e.g. 0B).")
            return

        mode = self.combo_mode.currentText()
        is_raw = (mode == "Raw I2C TRX")
        reg = 0
        if not is_raw:
            reg_str = self.input_reg.text().strip() or "00"
            try:
                reg = int(reg_str, 16)
            except ValueError:
                QMessageBox.warning(self, "Input Error", "Invalid Register/Command (must be Hex, e.g. 09).")
                return

        tx_data = []
        tx_str = self.input_tx_data.text().strip()
        if tx_str:
            try:
                tx_data = [int(b, 16) for b in tx_str.split()]
            except ValueError:
                QMessageBox.warning(self, "Input Error", "Invalid TX Data (must be space-separated Hex).")
                return

        if "Write" in mode and not tx_data:
            QMessageBox.warning(self, "Input Error", "Please provide Write Data.")
            return

        rx_len = 0
        try:
            rx_len = int(self.input_rx_len.text().strip())
        except ValueError:
            rx_len = 0

        use_pec = self.chk_pec.isChecked()

        # Log TX summary
        timestamp = time.strftime("%H:%M:%S")
        pec_tag = " | PEC: ON" if use_pec else ""
        if is_raw:
            tx_desc = f"[TX] CH{ch_idx} ➔ Addr:0x{addr:02X} | Mode:{mode} | TX:[{' '.join(f'{b:02X}' for b in tx_data)}] | RxLen:{rx_len}"
        elif "Write" in mode:
            tx_desc = f"[TX] CH{ch_idx} ➔ Addr:0x{addr:02X} | Reg:0x{reg:02X} ({mode}) | TX:[{' '.join(f'{b:02X}' for b in tx_data)}]{pec_tag}"
        else:
            tx_desc = f"[TX] CH{ch_idx} ➔ Addr:0x{addr:02X} | Reg:0x{reg:02X} ({mode}) | RxLen:{rx_len}{pec_tag}"

        self.man_console.append(f"[{timestamp}] {tx_desc}")
        self.btn_send.setEnabled(False)

        self.worker = ManualCommandWorker(port, ch_idx, addr, mode, reg, tx_data, rx_len, use_pec)
        self.worker.finished.connect(self._on_command_finished)
        self.worker.start()

    def _on_command_finished(self, success: bool, log_msg: str, raw_payload: bytes):
        self.btn_send.setEnabled(True)
        timestamp = time.strftime("%H:%M:%S")
        if success:
            self.man_console.append(f'<span style="color: {Colors.HEX_PASS_GREEN};">[{timestamp}] {log_msg}</span>\n')
        elif is_error_status(log_msg):
            log_error(f"[Manual Debug] {log_msg}")
            self.man_console.append(f'<span style="color: {Colors.HEX_FAIL};">[{timestamp}] {log_msg}</span>\n')
        else:
            self.man_console.append(f"[{timestamp}] {log_msg}\n")

    def _clear_console(self):
        self.man_console.clear()
