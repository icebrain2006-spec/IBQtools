import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLabel, QComboBox, QLineEdit, QPushButton, 
    QFileDialog, QTextBrowser, QMessageBox
)
from PySide6.QtCore import QThread, Signal

from gui.styles import Colors
from gui.strings import UIStrings
from gui.utils import convert_csv_to_slfs, load_bq_ic_info, is_error_status


class ConversionWorker(QThread):
    finished = Signal(bool, str)
    log_msg = Signal(str)

    def __init__(self, input_path: str, output_path: str, ic_type: str, version: str, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.ic_type = ic_type
        self.version = version

    def run(self):
        success, _count, msg = convert_csv_to_slfs(
            self.input_path, self.output_path, self.ic_type, self.version, log_callback=self.log_msg.emit
        )
        self.finished.emit(success, msg)


class CsvTab(QWidget):
    """CSV to SLFS Conversion Tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.ic_dict = {}
        self._init_ui()
        self._load_ic_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # IC Selection Group
        ic_group = QGroupBox(UIStrings.get("GRP_IC_CONFIG"))
        ic_layout = QHBoxLayout(ic_group)

        ic_layout.addWidget(QLabel(UIStrings.get("LBL_IC_TYPE")))
        self.combo_ic = QComboBox()
        self.combo_ic.currentIndexChanged.connect(self._update_versions)
        ic_layout.addWidget(self.combo_ic, stretch=1)

        ic_layout.addSpacing(20)

        ic_layout.addWidget(QLabel(UIStrings.get("LBL_VERSION")))
        self.combo_version = QComboBox()
        ic_layout.addWidget(self.combo_version, stretch=1)

        layout.addWidget(ic_group)

        # File Selection Group
        file_group = QGroupBox(UIStrings.get("GRP_FILE_PATHS"))
        file_layout = QVBoxLayout(file_group)

        # Input row
        in_row = QHBoxLayout()
        in_row.addWidget(QLabel(UIStrings.get("LBL_INPUT_CSV")))
        self.input_path = QLineEdit()
        self.input_path.setReadOnly(True)
        self.btn_browse_in = QPushButton(UIStrings.get("BTN_BROWSE"))
        self.btn_browse_in.clicked.connect(self._browse_input)
        in_row.addWidget(self.input_path, stretch=1)
        in_row.addWidget(self.btn_browse_in)
        file_layout.addLayout(in_row)

        # Output row
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel(UIStrings.get("LBL_OUTPUT_SLFS")))
        self.output_path = QLineEdit()
        self.btn_browse_out = QPushButton(UIStrings.get("BTN_BROWSE"))
        self.btn_browse_out.clicked.connect(self._browse_output)
        out_row.addWidget(self.output_path, stretch=1)
        out_row.addWidget(self.btn_browse_out)
        file_layout.addLayout(out_row)

        layout.addWidget(file_group)

        # Action Group (Convert Button)
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        self.btn_convert = QPushButton(UIStrings.get("BTN_CONVERT_SLFS"))
        self.btn_convert.setObjectName("startBtn")
        self.btn_convert.setMinimumWidth(220)
        self.btn_convert.clicked.connect(self._start_conversion)
        action_layout.addWidget(self.btn_convert)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        # Console
        self.console = QTextBrowser()
        self.console.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {Colors.HEX_BG_DARK};
                color: {Colors.HEX_WHITE};
                border: 1px solid {Colors.HEX_BORDER_LIGHT};
                font-family: 'Consolas', monospace;
            }}
        """)
        layout.addWidget(self.console, stretch=1)

    def _load_ic_data(self):
        info_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "BQ_Information.csv")
        self.ic_dict = load_bq_ic_info(info_path)

        if not self.ic_dict:
            self.log_msg("[ERROR] Could not load BQ_Information.csv or file is empty.")
            return

        for ic in sorted(self.ic_dict.keys(), reverse=True):
            self.combo_ic.addItem(ic)

    def _update_versions(self):
        self.combo_version.clear()
        ic = self.combo_ic.currentText()
        if ic in self.ic_dict:
            for v in sorted(list(self.ic_dict[ic])):
                self.combo_version.addItem(v)

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Logic i2cdata.csv", "", "CSV Files (*.csv);;All Files (*)")
        if path:
            self.input_path.setText(path)

            base = os.path.basename(path)
            name, _ = os.path.splitext(base)
            output_name = f"BQU_{name}.slfs"
            output_dir = os.path.dirname(path)
            output_path = os.path.join(output_dir, output_name)
            self.output_path.setText(os.path.normpath(output_path))

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save SLFS file as", self.output_path.text(), "SLFS Files (*.slfs);;All Files (*)")
        if path:
            self.output_path.setText(path)

    def log_msg(self, msg: str):
        if is_error_status(msg):
            self.console.append(f'<span style="color: {Colors.HEX_FAIL};">{msg}</span>')
        elif "SUCCESS" in msg or "successfully" in msg.lower():
            self.console.append(f'<span style="color: {Colors.HEX_PASS_GREEN};">{msg}</span>')
        else:
            self.console.append(msg)

    def _start_conversion(self):
        in_path = self.input_path.text().strip()
        out_path = self.output_path.text().strip()
        ic_type = self.combo_ic.currentText()
        version = self.combo_version.currentText()

        if not in_path or not out_path:
            QMessageBox.warning(self, "Warning", "Please specify both input and output files.")
            return

        self.console.clear()
        self.btn_convert.setEnabled(False)
        self.btn_convert.setText(UIStrings.get("BTN_CONVERTING"))

        self.worker = ConversionWorker(in_path, out_path, ic_type, version)
        self.worker.log_msg.connect(self.log_msg)
        self.worker.finished.connect(self._on_conversion_finished)
        self.worker.start()

    def _on_conversion_finished(self, success: bool, msg: str):
        self.btn_convert.setEnabled(True)
        self.btn_convert.setText(UIStrings.get("BTN_CONVERT_SLFS"))

        if success:
            self.log_msg(f"[SUCCESS] {msg}")
        else:
            self.log_msg(f"[ERROR] {msg}")
