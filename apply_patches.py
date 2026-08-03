import re

# Patch updater_tab.py
with open("gui/tabs/updater_tab.py", "r", encoding="utf-8") as f:
    tab_code = f.read()

# 1. _init_ui
tab_code = tab_code.replace(
    '        self.input_exp_date = QLineEdit("2024-03-05")\n        self.input_exp_date.setInputMask("9999-99-99")',
    '''        self.input_exp_date = QLineEdit("2024-03-05")
        self.input_exp_date.setInputMask("9999-99-99")
        
        self.chk_write_date = QCheckBox("Write Date to Chip")
        
        date_layout = QHBoxLayout()
        date_layout.addWidget(self.input_exp_date)
        date_layout.addWidget(self.chk_write_date)'''
)

tab_code = tab_code.replace(
    '        verify_form.addRow("Expected Date:", self.input_exp_date)',
    '        verify_form.addRow("Expected Date:", date_layout)'
)

# 2. _cache_values_if_needed
tab_code = tab_code.replace(
    '                self.cached_exp_date = self.input_exp_date.text().strip()\n                self.cached_fmt = self.combo_sn_fmt.currentText()',
    '                self.cached_exp_date = self.input_exp_date.text().strip()\n                self.cached_should_write_date = self.chk_write_date.isChecked()\n                self.cached_fmt = self.combo_sn_fmt.currentText()'
)

# 3. _get_expected_values
old_get_exp = '''    def _get_expected_values(self, is_writing=False):
        with self.sn_lock:
            exp_date = self.cached_exp_date
            fmt = self.cached_fmt
            should_write = self.cached_should_write
            should_inc = self.cached_should_inc
            ui_sn_int = self.cached_sn_int
            
            chip_sn_int = ui_sn_int
            
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
                    
            return exp_date, chip_sn_int, fmt, should_write'''

new_get_exp = '''    def _get_expected_values(self, is_writing=False):
        with self.sn_lock:
            exp_date = self.cached_exp_date
            fmt = self.cached_fmt
            should_write_sn = self.cached_should_write
            should_write_date = getattr(self, 'cached_should_write_date', False)
            should_inc = self.cached_should_inc
            ui_sn_int = self.cached_sn_int
            
            chip_sn_int = ui_sn_int
            
            if is_writing and should_write_sn and should_inc:
                self.cached_sn_int += 1
                if fmt == "DEC" and self.cached_sn_int > 9999:
                    self.cached_sn_int = 0
                elif fmt == "HEX" and self.cached_sn_int > 65535:
                    self.cached_sn_int = 0
                    
                if fmt == "HEX":
                    self.update_sn_ui_signal.emit(f"{self.cached_sn_int:X}")
                else:
                    self.update_sn_ui_signal.emit(str(self.cached_sn_int))
                    
            return exp_date, chip_sn_int, fmt, should_write_sn, should_write_date'''

tab_code = tab_code.replace(old_get_exp, new_get_exp)

# 4. save_ui_states
tab_code = tab_code.replace(
    '        settings.setValue("ui_exp_date", self.input_exp_date.text())',
    '        settings.setValue("ui_exp_date", self.input_exp_date.text())\n        settings.setValue("ui_write_date", self.chk_write_date.isChecked())'
)

# 5. load_ui_states
tab_code = tab_code.replace(
    '            self.input_exp_date.setText(str(settings.value("ui_exp_date", "2024-03-05")))',
    '            self.input_exp_date.setText(str(settings.value("ui_exp_date", "2024-03-05")))\n            self.chk_write_date.setChecked(str(settings.value("ui_write_date", "false")).lower() == "true")'
)

# 6. BoardPanel usages of get_expected_cb
tab_code = tab_code.replace(
    '        _, _, fmt, _ = self.get_expected_cb(False)',
    '        _, _, fmt, _, _ = self.get_expected_cb(False)'
)
tab_code = tab_code.replace(
    '        exp_date, sn_int, fmt, should_write = self.get_expected_cb(True)\n        if should_write:',
    '        exp_date, sn_int, fmt, should_write_sn, should_write_date = self.get_expected_cb(True)\n        if should_write_sn or should_write_date:'
)
tab_code = tab_code.replace(
    '                _, _, _, should_write = self.get_expected_cb(False)\n            else:\n                exp_date, exp_sn_int, sn_fmt, should_write = self.get_expected_cb(False)\n            \n            return exp_date, exp_sn_int, sn_fmt, should_write',
    '                _, _, _, should_write_sn, should_write_date = self.get_expected_cb(False)\n            else:\n                exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date = self.get_expected_cb(False)\n            \n            return exp_date, exp_sn_int, sn_fmt, should_write_sn, should_write_date'
)

with open("gui/tabs/updater_tab.py", "w", encoding="utf-8") as f:
    f.write(tab_code)

# Patch updater_thread.py
with open("gui/updater_thread.py", "r", encoding="utf-8") as f:
    thread_code = f.read()

# 1. run() method unpack
thread_code = thread_code.replace(
    '                                exp_date, exp_sn_int, fmt, should_write = self.get_expected_cb(ch)\n                                if should_write:\n                                    write_val = exp_sn_int',
    '''                                exp_date, exp_sn_int, fmt, should_write_sn, should_write_date = self.get_expected_cb(ch)
                                
                                if should_write_date:
                                    try:
                                        y, m, d = map(int, exp_date.split('-'))
                                        date_val = d + (m * 32) + ((y - 1980) * 512)
                                        self.log_msg.emit(f"[CH {ch}] Writing Expected Date: {exp_date} (0x{date_val:04X})")
                                        ok = self._write_smbus_word(ch, 0x0B, 0x1B, date_val)
                                        if not ok:
                                            self.log_msg.emit(f"[CH {ch}] Write Date FAILED!")
                                        time.sleep(0.1)
                                    except Exception as e:
                                        self.log_msg.emit(f"[CH {ch}] Failed to parse Date: {e}")
                                        
                                if should_write_sn:
                                    write_val = exp_sn_int'''
)

with open("gui/updater_thread.py", "w", encoding="utf-8") as f:
    f.write(thread_code)

print("Patch applied")
