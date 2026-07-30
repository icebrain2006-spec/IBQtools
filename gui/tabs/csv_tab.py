import os
import csv
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLabel, QComboBox, QLineEdit, QPushButton, 
                               QFileDialog, QTextBrowser, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal

class ConversionWorker(QThread):
    finished = Signal(bool, str)
    log_msg = Signal(str)

    def __init__(self, input_path, output_path, ic_type, version, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.ic_type = ic_type
        self.version = version

    def run(self):
        try:
            self.log_msg.emit(f"[INFO] Starting conversion: {self.input_path} -> {self.output_path}")
            with open(self.input_path, 'r', encoding='utf-8') as infile, open(self.output_path, 'w', encoding='utf-8') as outfile:
                reader = csv.DictReader(infile)
                rows = list(reader)
                
                outfile.write("; slfs file generated from i2cdata.csv\n")
                outfile.write(f"; IC Type: {self.ic_type}\n")
                outfile.write(f"; Version: {self.version}\n")           
                
                i = 0
                last_time = 0
                transaction_count = 0
                
                while i < len(rows):
                    if rows[i].get('type') == 'start':
                        j = i + 1
                        stop_index = -1
                        while j < len(rows):
                            if rows[j].get('type') == 'stop':
                                stop_index = j
                                break
                            j += 1
                        
                        if stop_index == -1:
                            i += 1
                            continue # Incomplete transaction

                        transaction_rows = rows[i:stop_index + 1]
                        
                        # Time delay
                        if last_time != 0:
                            time_diff = (float(transaction_rows[0]['start_time']) - last_time) * 1000
                            if time_diff > 0:
                                if time_diff < 30:
                                    time_diff = 2
                                outfile.write(f"X: {int(time_diff)}\n")

                        # Pattern: Write-then-Read
                        if (len(transaction_rows) >= 6 and
                            transaction_rows[1].get('type') == 'address' and transaction_rows[1].get('read') == 'false' and
                            transaction_rows[2].get('type') == 'data' and
                            transaction_rows[3].get('type') == 'start' and
                            transaction_rows[4].get('type') == 'address' and transaction_rows[4].get('read') == 'true' and
                            transaction_rows[1].get('address') == transaction_rows[4].get('address')):
                            
                            address_hex = transaction_rows[1]['address'].replace('0x', '')
                            command_byte = transaction_rows[2]['data'].replace('0x', '')
                            read_bytes = [r['data'].replace('0x', '') for r in transaction_rows[5:] if r.get('type') == 'data']
                            
                            write_address_8bit = f"{(int(address_hex, 16) << 1):02X}"
                            all_bytes = [write_address_8bit, command_byte] + read_bytes
                            outfile.write(f"C: {' '.join(all_bytes)}\n")
                            transaction_count += 1

                        else: # Simple Write or Simple Read
                            if len(transaction_rows) > 1 and transaction_rows[1].get('type') == 'address':
                                address_hex = transaction_rows[1]['address'].replace('0x', '')
                                is_read = transaction_rows[1]['read'] == 'true'
                                data_bytes = [r['data'].replace('0x', '') for r in transaction_rows[2:] if r.get('type') == 'data']

                                if not is_read: # Simple Write
                                    write_address_8bit = f"{(int(address_hex, 16) << 1):02X}"
                                    all_bytes = [write_address_8bit] + data_bytes
                                    outfile.write(f"W: {' '.join(all_bytes)}\n")
                                    transaction_count += 1
                                else: # Simple Read
                                    outfile.write(f"C: {address_hex} R\n")
                                    if data_bytes:
                                        outfile.write(f"W: {' '.join(data_bytes)}\n")
                                    transaction_count += 1

                        last_time = float(transaction_rows[-1]['start_time']) + float(transaction_rows[-1]['duration'])
                        i = stop_index + 1
                    else:
                        i += 1
            
            self.log_msg.emit(f"[INFO] Processed {transaction_count} transactions.")
            self.finished.emit(True, "File converted successfully!")
        except Exception as e:
            self.finished.emit(False, str(e))

class CsvTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._init_ui()
        self._load_ic_data()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # IC Selection Group
        ic_group = QGroupBox("IC Configuration")
        ic_layout = QHBoxLayout(ic_group)
        
        ic_layout.addWidget(QLabel("IC Type:"))
        self.combo_ic = QComboBox()
        self.combo_ic.currentIndexChanged.connect(self._update_versions)
        ic_layout.addWidget(self.combo_ic, stretch=1)
        
        ic_layout.addSpacing(20)
        
        ic_layout.addWidget(QLabel("Version:"))
        self.combo_version = QComboBox()
        ic_layout.addWidget(self.combo_version, stretch=1)
        
        layout.addWidget(ic_group)
        
        # File Selection Group
        file_group = QGroupBox("File Paths")
        file_layout = QVBoxLayout(file_group)
        
        # Input row
        in_row = QHBoxLayout()
        in_row.addWidget(QLabel("Input CSV:"))
        self.input_path = QLineEdit()
        self.input_path.setReadOnly(True)
        self.btn_browse_in = QPushButton("Browse...")
        self.btn_browse_in.clicked.connect(self._browse_input)
        in_row.addWidget(self.input_path, stretch=1)
        in_row.addWidget(self.btn_browse_in)
        file_layout.addLayout(in_row)
        
        # Output row
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output SLFS:"))
        self.output_path = QLineEdit()
        self.btn_browse_out = QPushButton("Browse...")
        self.btn_browse_out.clicked.connect(self._browse_output)
        out_row.addWidget(self.output_path, stretch=1)
        out_row.addWidget(self.btn_browse_out)
        file_layout.addLayout(out_row)
        
        layout.addWidget(file_group)
        
        # Action Group
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        self.btn_convert = QPushButton("CONVERT TO SLFS")
        self.btn_convert.setObjectName("startBtn")
        self.btn_convert.setMinimumWidth(200)
        self.btn_convert.clicked.connect(self._start_conversion)
        action_layout.addWidget(self.btn_convert)
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        # Console
        self.console = QTextBrowser()
        layout.addWidget(self.console, stretch=1)
        
    def _load_ic_data(self):
        info_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "BQ_Information.csv")
        self.ic_dict = {} # {ic_name: [versions]}
        
        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ic = row.get('IC')
                    version = row.get('Version')
                    if ic and version:
                        if ic not in self.ic_dict:
                            self.ic_dict[ic] = set()
                        self.ic_dict[ic].add(version)
            
            # Sort and populate combo box
            for ic in sorted(self.ic_dict.keys(), reverse=True):
                self.combo_ic.addItem(ic)
                
        except Exception as e:
            self.log_msg(f"[ERROR] Could not load BQ_Information.csv: {e}")
            
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
            
            # Auto-generate output path
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
            
    def log_msg(self, msg):
        if "ERROR" in msg or "Failed" in msg:
            self.console.append(f'<span style="color: #FF4444;">{msg}</span>')
        elif "SUCCESS" in msg:
            self.console.append(f'<span style="color: #00FF00;">{msg}</span>')
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
        self.btn_convert.setText("CONVERTING...")
        
        self.worker = ConversionWorker(in_path, out_path, ic_type, version)
        self.worker.log_msg.connect(self.log_msg)
        self.worker.finished.connect(self._on_conversion_finished)
        self.worker.start()
        
    def _on_conversion_finished(self, success, msg):
        self.btn_convert.setEnabled(True)
        self.btn_convert.setText("CONVERT TO SLFS")
        
        if success:
            self.log_msg(f"[SUCCESS] {msg}")
        else:
            self.log_msg(f"[ERROR] {msg}")
