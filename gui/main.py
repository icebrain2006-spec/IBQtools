import sys
import os
import struct
import serial
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QProgressBar,
    QTextBrowser, QCheckBox, QGroupBox, QGridLayout, QLineEdit, QFileDialog,
    QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QFont

from updater_thread import UpdaterWorker, make_packet, parse_response, CMD_I2C_RAW, RESP_OK

class BqUpdaterMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BQ40Z50 SLFS Multi-Channel Updater")
        self.resize(1100, 750)
        
        # Apply QSS
        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Failed to load QSS: {e}")

        self.worker = None # Reference to background thread
        
        # Central
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Tabs
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        # Init Tabs
        self.tab_updater = QWidget()
        self.tabs.addTab(self.tab_updater, "Firmware Update (Main)")
        self._init_updater_tab()
        
        self.tab_manual = QWidget()
        self.tabs.addTab(self.tab_manual, "Manual I2C Debug")
        self._init_manual_tab()
        
        self.tab_upload = QWidget()
        self.tabs.addTab(self.tab_upload, "SLFS Upload")
        self._init_upload_tab()
        
        self.tab_csv = QWidget()
        self.tabs.addTab(self.tab_csv, "CSV to SLFS")
        self._init_csv_tab()

    def _init_updater_tab(self):
        layout = QVBoxLayout(self.tab_updater)
        
        # 1. Top Bar (Settings)
        top_group = QGroupBox("Target Configuration")
        top_layout = QHBoxLayout(top_group)
        
        self.combo_port = QComboBox()
        self.combo_port.addItem("COM6")
        self.btn_refresh_port = QPushButton("Refresh Ports")
        
        self.loop_count = QLineEdit("1")
        self.loop_count.setFixedWidth(50)
        
        top_layout.addWidget(QLabel("COM Port:"))
        top_layout.addWidget(self.combo_port)
        top_layout.addWidget(self.btn_refresh_port)
        top_layout.addWidget(QLabel("   Loop Count:"))
        top_layout.addWidget(self.loop_count)
        top_layout.addStretch()
        layout.addWidget(top_group)
        
        # 2. Channels (Grid 2x3)
        channels_group = QGroupBox("Channel Monitoring")
        channels_layout = QGridLayout(channels_group)
        
        self.ch_checkboxes = []
        self.ch_progress = []
        self.ch_status = []
        
        for i in range(6):
            ch_idx = i + 1
            box = QGroupBox(f"Channel {ch_idx}")
            box_layout = QVBoxLayout(box)
            
            chk = QCheckBox("Enable")
            chk.setChecked(True)
            self.ch_checkboxes.append(chk)
            
            prog = QProgressBar()
            prog.setValue(0)
            self.ch_progress.append(prog)
            
            stat = QLabel("Status: Waiting")
            self.ch_status.append(stat)
            
            box_layout.addWidget(chk)
            box_layout.addWidget(prog)
            box_layout.addWidget(stat)
            
            row, col = divmod(i, 3)
            channels_layout.addWidget(box, row, col)
            
        layout.addWidget(channels_group)
        
        # 3. Log Console
        self.log_console = QTextBrowser()
        self.log_console.append("Welcome to BQ40Z50 Firmware Updater GUI.")
        layout.addWidget(self.log_console, stretch=1)
        
        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("START UPDATE")
        self.btn_start.setObjectName("startBtn")
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setEnabled(False)
        
        # Connect buttons
        self.btn_start.clicked.connect(self._start_update)
        self.btn_stop.clicked.connect(self._stop_update)
        
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        layout.addLayout(btn_layout)

    def _start_update(self):
        # 1. Gather selected channels
        active_channels = []
        for i, chk in enumerate(self.ch_checkboxes):
            if chk.isChecked():
                active_channels.append(i + 1)
                
        if not active_channels:
            self.log_console.append("[ERROR] Please select at least one channel to update.")
            return
            
        port = self.combo_port.currentText()
        
        # 2. UI State update
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        for chk in self.ch_checkboxes:
            chk.setEnabled(False)
            
        for i in range(6):
            if (i+1) in active_channels:
                self.ch_progress[i].setValue(0)
                self.ch_status[i].setText("Status: Starting...")
            else:
                self.ch_status[i].setText("Status: Disabled")
                
        self.log_console.append(f"\n[SYS] Initializing thread on {port}...")
        
        try:
            loops = int(self.loop_count.text())
        except ValueError:
            loops = 1
            
        # 3. Create and Start Worker
        self.worker = UpdaterWorker(port, active_channels, loop_count=loops)
        self.worker.log_msg.connect(self._on_log_msg)
        self.worker.progress_updated.connect(self._on_progress_update)
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _stop_update(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.btn_stop.setEnabled(False)

    def _on_log_msg(self, msg):
        self.log_console.append(msg)
        
    def _on_progress_update(self, ch_idx, percent):
        if 1 <= ch_idx <= 6:
            self.ch_progress[ch_idx - 1].setValue(percent)
            
    def _on_status_update(self, ch_idx, status_text):
        if 1 <= ch_idx <= 6:
            self.ch_status[ch_idx - 1].setText(f"Status: {status_text}")
            
    def _on_worker_finished(self, success):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        for chk in self.ch_checkboxes:
            chk.setEnabled(True)
        self.log_console.append("[SYS] Thread finished and cleaned up.")

    def _init_manual_tab(self):
        layout = QVBoxLayout(self.tab_manual)
        
        ctrl_group = QGroupBox("Command Configuration")
        ctrl_layout = QGridLayout(ctrl_group)
        
        ctrl_layout.addWidget(QLabel("Channel (1-6):"), 0, 0)
        self.man_ch = QComboBox()
        self.man_ch.addItems(["1","2","3","4","5","6"])
        ctrl_layout.addWidget(self.man_ch, 0, 1)
        
        ctrl_layout.addWidget(QLabel("I2C Address (Hex):"), 0, 2)
        self.man_addr = QLineEdit("0B")
        ctrl_layout.addWidget(self.man_addr, 0, 3)
        
        ctrl_layout.addWidget(QLabel("Command Mode:"), 1, 0)
        self.man_mode = QComboBox()
        self.man_mode.addItems(["RAW I2C TRX", "SMBus Read Word", "SMBus Read Block"])
        ctrl_layout.addWidget(self.man_mode, 1, 1)
        
        ctrl_layout.addWidget(QLabel("TX Data (Hex space separated):"), 2, 0)
        self.man_tx = QLineEdit("08 11")
        ctrl_layout.addWidget(self.man_tx, 2, 1, 1, 3)
        
        ctrl_layout.addWidget(QLabel("Expected RX Bytes:"), 3, 0)
        self.man_rx_len = QLineEdit("4")
        ctrl_layout.addWidget(self.man_rx_len, 3, 1)
        
        self.btn_send_cmd = QPushButton("SEND COMMAND")
        self.btn_send_cmd.setObjectName("startBtn")
        self.btn_send_cmd.clicked.connect(self._send_manual_command)
        ctrl_layout.addWidget(self.btn_send_cmd, 3, 3)
        
        layout.addWidget(ctrl_group)
        
        self.man_console = QTextBrowser()
        self.man_console.append("Ready for manual I2C commands.")
        layout.addWidget(self.man_console, stretch=1)

    def _send_manual_command(self):
        port = self.combo_port.currentText()
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
        
        # Build payload for CMD_I2C_RAW: [channel, addr, tx_len, rx_len, tx_data...]
        payload = bytes([ch, addr, tx_len, rx_len]) + bytes(tx_data)
        packet = make_packet(CMD_I2C_RAW, payload)
        
        self.man_console.append(f"\n[TX] CH:{ch} Addr:{addr:#04x} TX:{tx_data} Expected_RX:{rx_len}")
        
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

    def _init_upload_tab(self):
        layout = QVBoxLayout(self.tab_upload)
        
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

    def _init_csv_tab(self):
        layout = QVBoxLayout(self.tab_csv)
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

def main():
    app = QApplication(sys.argv)
    window = BqUpdaterMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
