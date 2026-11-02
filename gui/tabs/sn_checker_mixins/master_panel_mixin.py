from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QGridLayout, QLabel, QComboBox, QLineEdit, 
    QPushButton, QTextBrowser, QCheckBox, QSpinBox, 
    QFormLayout, QScrollArea
)
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator

from gui.widgets.rp2040_board_widget import RP2040BoardWidget
from gui.styles import Styles, Colors
from gui.strings import UIStrings


class MasterPanelMixin:
    """Mixin class for constructing and managing the Master Configuration panel & Board scroll area."""

    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        # --- LEFT PANEL (Master Control & Log) ---
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Master Board Group
        master_group = QGroupBox(UIStrings.get("GRP_MASTER_CONFIG"))
        mlayout = QGridLayout(master_group)
        mlayout.addWidget(QLabel(UIStrings.get("LBL_NUM_BOARDS")), 0, 0)
        self.spin_boards = QSpinBox()
        self.spin_boards.setRange(1, 4)
        self.spin_boards.setValue(1)
        self.spin_boards.valueChanged.connect(self._update_board_count)
        mlayout.addWidget(self.spin_boards, 0, 1)
        
        mlayout.addWidget(QLabel(UIStrings.get("LBL_LOOP_COUNT")), 1, 0)
        self.loop_count = QLineEdit("1")
        mlayout.addWidget(self.loop_count, 1, 1)
        
        # SBS Serial & Date Group
        verify_group = QGroupBox(UIStrings.get("GRP_VERIFY_TARGETS"))
        verify_form = QFormLayout(verify_group)
        self.input_exp_date = QLineEdit("2024-03-05")
        self.input_exp_date.setInputMask("9999-99-99")
        self.chk_write_date = QCheckBox("Write Date to Chip")
        
        date_layout = QHBoxLayout()
        date_layout.addWidget(self.input_exp_date)
        date_layout.addWidget(self.chk_write_date)
        
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
        self.chk_led = QCheckBox("LED Toggle (0x002B)")
        
        verify_form.addRow("Expected Date:", date_layout)
        verify_form.addRow("Start SN:", sn_layout)
        verify_form.addRow("LED Option:", self.chk_led)

        # Manufacturer Data (Block A) Serial Group (Independent from SBS)
        mfg_group = QGroupBox(UIStrings.get("GRP_MFG_SERIAL"))
        mfg_form = QFormLayout(mfg_group)
        
        mfg_chk_layout = QHBoxLayout()
        self.chk_write_mfg_sn = QCheckBox(UIStrings.get("CHK_WRITE_MFG_SN"))
        self.chk_mfg_auto_inc = QCheckBox(UIStrings.get("CHK_MFG_AUTO_INC"))
        self.chk_mfg_auto_inc.setEnabled(False)
        self.chk_write_mfg_sn.toggled.connect(self.chk_mfg_auto_inc.setEnabled)
        mfg_chk_layout.addWidget(self.chk_write_mfg_sn)
        mfg_chk_layout.addWidget(self.chk_mfg_auto_inc)
        mfg_form.addRow("Mfg Options:", mfg_chk_layout)
        
        block_layout = QHBoxLayout()
        self.combo_mfg_start_block = QComboBox()
        self.combo_mfg_start_block.addItems([f"A{i:02d}" for i in range(1, 32)])
        self.combo_mfg_start_block.setCurrentText("A02")
        
        self.lbl_mfg_block_hint = QLabel(UIStrings.get("LBL_MFG_BLOCK_HINT").format(b1="A02", b2="A03"))
        self.lbl_mfg_block_hint.setStyleSheet(f"color: {Colors.HEX_WARN_CYAN}; font-weight: bold; font-size: 11px;")
        
        def _on_start_block_changed(blk):
            try:
                idx = int(blk[1:])
                next_blk = f"A{idx+1:02d}"
                self.lbl_mfg_block_hint.setText(UIStrings.get("LBL_MFG_BLOCK_HINT").format(b1=blk, b2=next_blk))
            except Exception:
                pass
        self.combo_mfg_start_block.currentTextChanged.connect(_on_start_block_changed)
        block_layout.addWidget(self.combo_mfg_start_block)
        block_layout.addWidget(self.lbl_mfg_block_hint)
        mfg_form.addRow(UIStrings.get("LBL_MFG_START_BLOCK"), block_layout)
        
        mfg_sn_layout = QHBoxLayout()
        self.combo_mfg_sn_fmt = QComboBox()
        self.combo_mfg_sn_fmt.addItems(["DEC", "HEX"])
        self.input_mfg_exp_sn = QLineEdit("1")
        
        self.val_mfg_dec = QRegularExpressionValidator(QRegularExpression(r"^[0-9]{1,5}$"))
        self.val_mfg_hex = QRegularExpressionValidator(QRegularExpression(r"^[0-9A-Fa-f]{1,4}$"))
        self.input_mfg_exp_sn.setValidator(self.val_mfg_dec)
        
        def _on_mfg_sn_fmt_changed(fmt):
            if fmt == "DEC":
                self.input_mfg_exp_sn.setValidator(self.val_mfg_dec)
                try:
                    val = int(self.input_mfg_exp_sn.text() or "0", 16)
                    if val > 65535: val = 65535
                    self.input_mfg_exp_sn.setText(str(val))
                except ValueError:
                    self.input_mfg_exp_sn.setText("0")
            else:
                self.input_mfg_exp_sn.setValidator(self.val_mfg_hex)
                try:
                    val = int(self.input_mfg_exp_sn.text() or "0")
                    if val > 65535: val = 65535
                    self.input_mfg_exp_sn.setText(f"{val:X}")
                except ValueError:
                    self.input_mfg_exp_sn.setText("0")
        self.combo_mfg_sn_fmt.currentTextChanged.connect(_on_mfg_sn_fmt_changed)
        mfg_sn_layout.addWidget(self.combo_mfg_sn_fmt)
        mfg_sn_layout.addWidget(self.input_mfg_exp_sn)
        mfg_form.addRow(UIStrings.get("LBL_MFG_SN"), mfg_sn_layout)
        
        left_layout.addWidget(master_group)
        left_layout.addWidget(verify_group)
        left_layout.addWidget(mfg_group)
        
        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_start = QPushButton(UIStrings.get("BTN_START_ALL"))
        self.btn_start.setObjectName("startBtn")
        self.btn_stop = QPushButton(UIStrings.get("BTN_STOP_ALL"))
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setEnabled(False)
        
        self.btn_quick_start = QPushButton(UIStrings.get("BTN_QUICK_START"))
        self.btn_quick_start.setCheckable(True)
        self.btn_quick_start.setStyleSheet(Styles.QUICK_START_BTN)
        self.btn_quick_start.setToolTip(UIStrings.get("TOOLTIP_QUICK_START"))
        
        self.btn_start.clicked.connect(self._start_all)
        self.btn_stop.clicked.connect(self._stop_all)
        
        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_stop)
        action_layout.addWidget(self.btn_quick_start)
        left_layout.addLayout(action_layout)
        
        self.btn_check_all = QPushButton(UIStrings.get("BTN_SERIAL_CHECK"))
        self.btn_check_all.setObjectName("checkBtn")
        self.btn_check_all.clicked.connect(self._check_all)
        left_layout.addWidget(self.btn_check_all)
        
        # Log Console
        self.log_console = QTextBrowser()
        self.log_console.setStyleSheet(Styles.LOG_CONSOLE)
        self.log_console.append("Welcome to Multi-Board BQ40Z50 Updater GUI.")
        left_layout.addWidget(self.log_console, stretch=1)
        
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
        self._update_board_count(1)

    def is_hotkey_ready(self):
        return hasattr(self, 'btn_quick_start') and self.btn_quick_start.isChecked()
        
    def trigger_start_all(self):
        if self.btn_start.isEnabled():
            self.btn_start.click()

    def _update_board_count(self, count):
        for board in self.boards:
            self.boards_layout.removeWidget(board)
            board.deleteLater()
        self.boards.clear()
        
        for i in range(count):
            board = RP2040BoardWidget(i + 1, self._log_to_console, self._get_expected_values, self._cache_values_if_needed)
            board.board_finished.connect(self._on_board_finished_callback)
            board.request_start.connect(self._start_single_board)
            board.combo_port.currentTextChanged.connect(self._on_port_changed)
            self.boards_layout.addWidget(board)
            self.boards.append(board)

    def _on_port_changed(self, text):
        if text == "None":
            return
            
        sender_combo = self.sender()
        if not sender_combo: return
        
        for board in self.boards:
            if board.combo_port != sender_combo and board.combo_port.currentText() == text:
                board.combo_port.blockSignals(True)
                board.combo_port.setCurrentText("None")
                board.combo_port.blockSignals(False)
