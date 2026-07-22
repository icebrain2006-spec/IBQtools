import sys
import os
import struct
import serial
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QProgressBar,
    QTextBrowser, QCheckBox, QGroupBox, QGridLayout, QLineEdit,
    QFileDialog, QMessageBox, QScrollArea, QSpinBox, QFormLayout
)
from PySide6.QtCore import Qt, QSize, QRegularExpression, Signal
from PySide6.QtGui import QIcon, QFont, QRegularExpressionValidator
import threading

from updater_thread import UpdaterWorker, make_packet, parse_response, CMD_I2C_RAW, RESP_OK, get_file_info

class ClickableProgressBar(QProgressBar):
    from PySide6.QtCore import Signal
    clicked = Signal(int)
    
    def __init__(self, ch_idx, parent=None):
        super().__init__(parent)
        self.ch_idx = ch_idx
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ch_idx)
        super().mousePressEvent(event)

class RP2040BoardWidget(QGroupBox):
    from PySide6.QtCore import Signal
    board_finished = Signal()
    
    def __init__(self, board_id, log_callback, get_expected_cb, cache_values_cb, parent=None):
        super().__init__(f"RP2040 Board {board_id}", parent)
        self.board_id = board_id
        self.log_callback = log_callback # Function to send logs to central console
        self.get_expected_cb = get_expected_cb
        self.cache_values_cb = cache_values_cb
        self.worker = None
        self.expected_sn_map = {}
        self.expected_date_map = {}
        self.expected_fmt = "DEC"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(5)
        
        # COM Port Selection Row
        com_layout = QHBoxLayout()
        com_layout.setContentsMargins(5, 0, 5, 0)
        com_layout.addWidget(QLabel("COM Port:"))
        self.combo_port = QComboBox()
        # Mock some default ports for convenience
        self.combo_port.addItems(["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "COM10"])
        self.combo_port.setCurrentText(f"COM{5 + board_id}") # Just a dummy default
        com_layout.addWidget(self.combo_port)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_info)
        com_layout.addWidget(self.btn_refresh)
        
        self.lbl_slfs_info = QLabel("SLFS: Unknown")
        self.lbl_slfs_info.setStyleSheet("color: #00E5FF; font-weight: bold; margin-left: 15px;")
        com_layout.addWidget(self.lbl_slfs_info)
        
        com_layout.addStretch()
        layout.addLayout(com_layout)
        
        # 6 Channels Grid
        channels_layout = QGridLayout()
        channels_layout.setContentsMargins(5, 0, 5, 5)
        channels_layout.setVerticalSpacing(5)
        channels_layout.setHorizontalSpacing(10)
        
        self.ch_checkboxes = []
        self.ch_progress = []
        self.ch_status = []
        
        for i in range(6):
            ch_idx = i + 1
            box = QGroupBox(f"CH {ch_idx}")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(8, 12, 8, 8)
            box_layout.setSpacing(4)
            
            chk = QCheckBox("Enable")
            chk.setChecked(True)
            self.ch_checkboxes.append(chk)
            
            prog = ClickableProgressBar(ch_idx)
            prog.setValue(0)
            prog.clicked.connect(self.start_single_channel)
            self.ch_progress.append(prog)
            
            stat = QLabel("Status: Waiting")
            self.ch_status.append(stat)
            
            box_layout.addWidget(chk)
            box_layout.addWidget(prog)
            box_layout.addWidget(stat)
            
            row, col = divmod(i, 6)
            channels_layout.addWidget(box, row, col)
            
        layout.addLayout(channels_layout)

    def refresh_info(self):
        port = self.combo_port.currentText()
        fname = get_file_info(port)
        if fname:
            self.lbl_slfs_info.setText(f"SLFS: {fname}")
        else:
            self.lbl_slfs_info.setText("SLFS: Not Connected / Error")

    def start_worker(self, loop_count):
        self.refresh_info()
        if "Unknown" in self.lbl_slfs_info.text() or "Error" in self.lbl_slfs_info.text():
            QMessageBox.warning(self, "SLFS Check", f"Board {self.board_id}: SLFS file not found! Please check the connection or upload the SLFS file first.")
            return False
            
        active_channels = []
        for i, chk in enumerate(self.ch_checkboxes):
            if chk.isChecked():
                active_channels.append(i + 1)
                
        if not active_channels:
            self.log_callback(f"[Board {self.board_id}] No channels selected. Skipping.")
            return False
            
        if self.cache_values_cb:
            self.cache_values_cb()
            
        port = self.combo_port.currentText()
        
        # UI State update
        for chk in self.ch_checkboxes:
            chk.setEnabled(False)
            
        for i in range(6):
            if (i+1) in active_channels:
                self.ch_progress[i].setValue(0)
                self.ch_status[i].setText("Status: Starting...")
            else:
                self.ch_status[i].setText("Status: Disabled")
                
        self.log_callback(f"[Board {self.board_id}] Initializing thread on {port}...")
        self.expected_sn_map.clear()
        self.expected_date_map.clear()
        
        self.worker = UpdaterWorker(port, active_channels, loop_count=loop_count, get_expected_cb=self._get_sn_for_worker)
        # Prefix log messages with board ID
        self.worker.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id}] {msg}"))
        self.worker.progress_updated.connect(self._on_progress_update)
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.verify_updated.connect(self._on_verify_update)
        self.worker.finished.connect(self._on_worker_finished)
        
        self.worker.start()
        return True

    def start_single_channel(self, ch_idx):
        if self.worker and self.worker.isRunning():
            self.log_callback(f"[Board {self.board_id}] Worker is already running. Please stop it first.")
            return
            
        self.refresh_info()
        if "Unknown" in self.lbl_slfs_info.text() or "Error" in self.lbl_slfs_info.text():
            QMessageBox.warning(self, "SLFS Check", f"Board {self.board_id}: SLFS file not found! Please check the connection or upload the SLFS file first.")
            return
            
        if self.cache_values_cb:
            self.cache_values_cb()
            
        port = self.combo_port.currentText()
        
        for chk in self.ch_checkboxes:
            chk.setEnabled(False)
            
        self.ch_progress[ch_idx - 1].setValue(0)
        self.ch_status[ch_idx - 1].setText("Status: Starting...")
        
        self.log_callback(f"[Board {self.board_id}] Initializing SINGLE update for CH {ch_idx} on {port}...")
        self.expected_sn_map.clear()
        self.expected_date_map.clear()
        
        self.worker = UpdaterWorker(port, [ch_idx], loop_count=1, get_expected_cb=self._get_sn_for_worker)
        self.worker.log_msg.connect(lambda msg: self.log_callback(f"[Board {self.board_id}] {msg}"))
        self.worker.progress_updated.connect(self._on_progress_update)
        self.worker.status_updated.connect(self._on_status_update)
        self.worker.verify_updated.connect(self._on_verify_update)
        self.worker.finished.connect(self._on_worker_finished)
        
        self.worker.start()

    def stop_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()

    def _get_sn_for_worker(self, ch_idx):
        exp_date, sn_int, fmt, should_write = self.get_expected_cb(True)
        if should_write:
            self.expected_date_map[ch_idx] = exp_date
            self.expected_sn_map[ch_idx] = sn_int
            self.expected_fmt = fmt
        return exp_date, sn_int, fmt, should_write

    def _on_progress_update(self, ch_idx, percent):
        if 1 <= ch_idx <= 6:
            self.ch_progress[ch_idx - 1].setValue(percent)
            
    def _on_status_update(self, ch_idx, status_text):
        if 1 <= ch_idx <= 6:
            self.ch_status[ch_idx - 1].setText(f"Status: {status_text}")
            self.ch_status[ch_idx - 1].setStyleSheet("") # Reset style
            
    def _on_verify_update(self, ch_idx, date_str, sn_int):
        if 1 <= ch_idx <= 6:
            if ch_idx in self.expected_sn_map:
                exp_date = self.expected_date_map[ch_idx]
                exp_sn_int = self.expected_sn_map[ch_idx]
                sn_fmt = self.expected_fmt
            else:
                exp_date, exp_sn_int, sn_fmt, _ = self.get_expected_cb(False)
            
            if not date_str or sn_int < 0:
                self.ch_status[ch_idx - 1].setText("Verify: ERROR")
                self.ch_status[ch_idx - 1].setStyleSheet("color: #FF4444; font-weight: bold;")
                return
                
            if sn_fmt == "HEX":
                sn_str = f"0x{sn_int:04X}"
                exp_sn_str = f"0x{exp_sn_int:04X}"
            else:
                sn_str = str(sn_int)
                exp_sn_str = str(exp_sn_int)
                
            if date_str == exp_date and sn_int == exp_sn_int:
                self.ch_status[ch_idx - 1].setText(f"PASS (M:{date_str} SN:{sn_str})")
                self.ch_status[ch_idx - 1].setStyleSheet("color: #00FF00; font-weight: bold;")
            else:
                self.ch_status[ch_idx - 1].setText(f"FAIL (M:{date_str} SN:{sn_str})")
                self.ch_status[ch_idx - 1].setStyleSheet("color: #FF4444; font-weight: bold;")
            
    def _on_worker_finished(self, success):
        for chk in self.ch_checkboxes:
            chk.setEnabled(True)
        self.log_callback(f"[Board {self.board_id}] Thread finished.")
        self.board_finished.emit()


class BqUpdaterMainWindow(QMainWindow):
    update_sn_ui_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Board BQ40Z50 Firmware Updater")
        self.resize(1500, 800)
        
        self.boards = []
        self.active_workers = 0
        self.sn_lock = threading.Lock()
        
        self.cached_exp_date = ""
        self.cached_fmt = "DEC"
        self.cached_should_write = False
        self.cached_should_inc = False
        self.cached_sn_int = 0
        
        self.update_sn_ui_signal.connect(self._safe_update_sn_ui)
        
        # Apply QSS
        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Failed to load QSS: {e}")

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
        # Master layout for the updater tab: Split Left/Right
        layout = QHBoxLayout(self.tab_updater)
        
        # --- LEFT PANEL (Master Control & Log) ---
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0,0,0,0)
        
        master_group = QGroupBox("Master Configuration")
        mlayout = QGridLayout(master_group)
        
        mlayout.addWidget(QLabel("Number of Boards (1-4):"), 0, 0)
        self.spin_boards = QSpinBox()
        self.spin_boards.setRange(1, 4)
        self.spin_boards.setValue(1)
        self.spin_boards.valueChanged.connect(self._update_board_count)
        mlayout.addWidget(self.spin_boards, 0, 1)
        
        mlayout.addWidget(QLabel("Loop Count:"), 1, 0)
        self.loop_count = QLineEdit("1")
        mlayout.addWidget(self.loop_count, 1, 1)
        
        # Expected Verification Targets row
        verify_group = QGroupBox("Verification Targets")
        verify_form = QFormLayout(verify_group)
        self.input_exp_date = QLineEdit("2024-03-05")
        self.input_exp_date.setInputMask("9999-99-99")
        
        chk_layout = QHBoxLayout()
        self.chk_write_sn = QCheckBox("Write SN to Chip")
        self.chk_auto_inc = QCheckBox("Auto Increment (+1)")
        self.chk_auto_inc.setEnabled(False)
        self.chk_write_sn.toggled.connect(self.chk_auto_inc.setEnabled)
        chk_layout.addWidget(self.chk_write_sn)
        chk_layout.addWidget(self.chk_auto_inc)
        verify_form.addRow("SN Options:", chk_layout)
        
        sn_layout = QHBoxLayout()
        self.combo_sn_fmt = QComboBox()
        self.combo_sn_fmt.addItems(["DEC", "HEX"])
        self.input_exp_sn = QLineEdit("1")
        
        self.val_dec = QRegularExpressionValidator(QRegularExpression(r"^[0-9]{1,4}$"))
        self.val_hex = QRegularExpressionValidator(QRegularExpression(r"^[0-9A-Fa-f]{1,4}$"))
        self.input_exp_sn.setValidator(self.val_dec)
        
        def _on_sn_fmt_changed(fmt):
            if fmt == "DEC":
                self.input_exp_sn.setValidator(self.val_dec)
                try:
                    val = int(self.input_exp_sn.text() or "0", 16)
                    if val > 9999: val = 9999
                    self.input_exp_sn.setText(str(val))
                except ValueError:
                    self.input_exp_sn.setText("0")
            else:
                self.input_exp_sn.setValidator(self.val_hex)
                try:
                    val = int(self.input_exp_sn.text() or "0")
                    self.input_exp_sn.setText(f"{val:X}")
                except ValueError:
                    self.input_exp_sn.setText("0")
                    
        self.combo_sn_fmt.currentTextChanged.connect(_on_sn_fmt_changed)
        
        sn_layout.addWidget(self.combo_sn_fmt)
        sn_layout.addWidget(self.input_exp_sn)
        
        verify_form.addRow("Expected Date:", self.input_exp_date)
        verify_form.addRow("Start SN:", sn_layout)
        left_layout.addWidget(master_group)
        left_layout.addWidget(verify_group)
        
        self.log_console = QTextBrowser()
        self.log_console.append("Welcome to Multi-Board BQ40Z50 Updater GUI.")
        left_layout.addWidget(self.log_console, stretch=1)
        
        # Action Buttons
        self.btn_start = QPushButton("START ALL")
        self.btn_start.setObjectName("startBtn")
        self.btn_stop = QPushButton("STOP ALL")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setEnabled(False)
        
        self.btn_start.clicked.connect(self._start_all)
        self.btn_stop.clicked.connect(self._stop_all)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        left_layout.addLayout(btn_layout)
        
        layout.addWidget(left_panel)
        
        # --- RIGHT PANEL (Scroll Area with Boards) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("boardScroll")
        
        self.scroll_content = QWidget()
        self.boards_layout = QVBoxLayout(self.scroll_content)
        self.boards_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        
        layout.addWidget(self.scroll_area, stretch=1)
        
        # Initialize board widgets
        self.boards = []
        self._update_board_count(1)

    def _update_board_count(self, count):
        # Remove all existing boards from layout
        for board in self.boards:
            self.boards_layout.removeWidget(board)
            board.deleteLater()
        self.boards.clear()
        
        # Add new boards
        for i in range(count):
            board = RP2040BoardWidget(i + 1, self._log_to_console, self._get_expected_values, self._cache_values_if_needed)
            board.board_finished.connect(self._on_board_finished_callback)
            self.boards_layout.addWidget(board)
            self.boards.append(board)

    def _safe_update_sn_ui(self, sn_str):
        self.input_exp_sn.setText(sn_str)

    def _cache_values_if_needed(self):
        with self.sn_lock:
            if self.active_workers == 0:
                self.cached_exp_date = self.input_exp_date.text().strip()
                self.cached_fmt = self.combo_sn_fmt.currentText()
                self.cached_should_write = self.chk_write_sn.isChecked()
                self.cached_should_inc = self.chk_auto_inc.isChecked()
                sn_text = self.input_exp_sn.text().strip() or "0"
                self.cached_sn_int = int(sn_text, 16) if self.cached_fmt == "HEX" else int(sn_text)

    def _get_expected_values(self, is_writing=False):
        with self.sn_lock:
            exp_date = self.cached_exp_date
            fmt = self.cached_fmt
            should_write = self.cached_should_write
            should_inc = self.cached_should_inc
            ui_sn_int = self.cached_sn_int
            
            # For BCD behavior: treat the decimal string as a base-16 number to form the chip value
            chip_sn_int = int(str(ui_sn_int), 16) if fmt == "DEC" else ui_sn_int
            
            if is_writing and should_write and should_inc:
                self.cached_sn_int += 1
                if fmt == "DEC" and self.cached_sn_int > 9999:
                    self.cached_sn_int = 0
                elif fmt == "HEX" and self.cached_sn_int > 65535:
                    self.cached_sn_int = 0
                    
                if fmt == "HEX":
                    self.update_sn_ui_signal.emit(f"{self.cached_sn_int:X}")
                else:
                    self.update_sn_ui_signal.emit(str(self.cached_sn_int))
                    
            return exp_date, chip_sn_int, fmt, should_write

    def _on_board_finished_callback(self):
        self.active_workers -= 1
        if self.active_workers <= 0:
            self.active_workers = 0
            self._reset_master_ui()

    def _log_to_console(self, msg):
        self.log_console.append(msg)

    def _start_all(self):
        try:
            loops = int(self.loop_count.text())
        except ValueError:
            loops = 1
            
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.spin_boards.setEnabled(False)
        
        self.log_console.append(f"\n[SYS] STARTING ALL {len(self.boards)} BOARDS...")
        
        self.active_workers = 0
        for board in self.boards:
            if board.start_worker(loops):
                self.active_workers += 1
                
        if self.active_workers == 0:
            self.log_console.append("[SYS] No channels were enabled across any boards.")
            self._reset_master_ui()

    def _stop_all(self):
        self.log_console.append("\n[SYS] STOP ALL REQUESTED...")
        for board in self.boards:
            board.stop_worker()
        self._reset_master_ui()

    def _reset_master_ui(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.spin_boards.setEnabled(True)

    def _init_manual_tab(self):
        layout = QVBoxLayout(self.tab_manual)
        
        ctrl_group = QGroupBox("Command Configuration")
        ctrl_layout = QGridLayout(ctrl_group)
        
        ctrl_layout.addWidget(QLabel("COM Port:"), 0, 0)
        self.man_port = QComboBox()
        self.man_port.addItems(["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "COM10"])
        ctrl_layout.addWidget(self.man_port, 0, 1)
        
        ctrl_layout.addWidget(QLabel("Channel (1-6):"), 0, 2)
        self.man_ch = QComboBox()
        self.man_ch.addItems(["1","2","3","4","5","6"])
        ctrl_layout.addWidget(self.man_ch, 0, 3)
        
        ctrl_layout.addWidget(QLabel("I2C Address (Hex):"), 1, 0)
        self.man_addr = QLineEdit("0B")
        ctrl_layout.addWidget(self.man_addr, 1, 1)
        
        ctrl_layout.addWidget(QLabel("Command Mode:"), 1, 2)
        self.man_mode = QComboBox()
        self.man_mode.addItems(["RAW I2C TRX", "SMBus Read Word", "SMBus Read Block"])
        ctrl_layout.addWidget(self.man_mode, 1, 3)
        
        ctrl_layout.addWidget(QLabel("TX Data (Hex space separated):"), 2, 0)
        self.man_tx = QLineEdit("08")
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
