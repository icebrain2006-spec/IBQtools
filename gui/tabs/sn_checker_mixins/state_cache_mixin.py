import logging
from gui.config import config
from gui.utils import format_sn_value

class StateCacheMixin:
    """Mixin class for thread-safe value caching and UI state saving/restoring via QSettings."""

    def _safe_update_sn_ui(self, sn_str):
        self.input_exp_sn.setText(sn_str)

    def _cache_values_if_needed(self):
        with self.sn_lock:
            if self.active_workers == 0:
                self.cached_exp_date = self.input_exp_date.text().strip()
                self.cached_should_write_date = self.chk_write_date.isChecked()
                self.cached_fmt = self.combo_sn_fmt.currentText()
                self.cached_should_write = self.chk_write_sn.isChecked()
                self.cached_should_inc = self.chk_auto_inc.isChecked()
                self.cached_should_toggle_led = self.chk_led.isChecked()
                sn_text = self.input_exp_sn.text().strip() or "0"
                self.cached_sn_int = int(sn_text, 16) if self.cached_fmt == "HEX" else int(sn_text)

    def _increment_and_format_sn(self, fmt: str) -> tuple[int, str]:
        """Increments cached SN, applies format overflow boundary checks, and returns updated int and formatted string."""
        self.cached_sn_int += 1
        self.cached_sn_int, formatted_sn = format_sn_value(self.cached_sn_int, fmt)
        return self.cached_sn_int, formatted_sn

    def _get_expected_values(self, is_writing=False):
        """Resolves cached target expected values and increments SN if writing with auto-increment enabled."""
        with self.sn_lock:
            exp_date = getattr(self, 'cached_exp_date', self.input_exp_date.text().strip())
            fmt = getattr(self, 'cached_fmt', self.combo_sn_fmt.currentText())
            should_write_sn = getattr(self, 'cached_should_write', self.chk_write_sn.isChecked())
            should_write_date = getattr(self, 'cached_should_write_date', self.chk_write_date.isChecked())
            should_toggle_led = getattr(self, 'cached_should_toggle_led', self.chk_led.isChecked())
            should_inc = getattr(self, 'cached_should_inc', self.chk_auto_inc.isChecked())
            chip_sn_int = getattr(self, 'cached_sn_int', 0)

            if is_writing and should_write_sn and should_inc:
                _, formatted_sn_str = self._increment_and_format_sn(fmt)
                self.update_sn_ui_signal.emit(formatted_sn_str)

            return exp_date, chip_sn_int, fmt, should_write_sn, should_write_date, should_toggle_led

    def save_ui_states(self):
        settings = config.settings
        settings.setValue("ui_boards", self.spin_boards.value())
        settings.setValue("ui_loop_count", self.loop_count.text())
        settings.setValue("ui_exp_date", self.input_exp_date.text())
        settings.setValue("ui_write_date", self.chk_write_date.isChecked())
        settings.setValue("ui_sn_fmt", self.combo_sn_fmt.currentText())
        settings.setValue("ui_exp_sn", self.input_exp_sn.text())
        settings.setValue("ui_write_sn", self.chk_write_sn.isChecked())
        settings.setValue("ui_auto_inc", self.chk_auto_inc.isChecked())
        settings.setValue("ui_led_toggle", self.chk_led.isChecked())
        
        for board in self.boards:
            bid = board.board_id
            settings.setValue(f"ui_board_{bid}_port", board.combo_port.currentText())
            for i, chk in enumerate(board.ch_checkboxes):
                settings.setValue(f"ui_board_{bid}_ch_{i+1}", chk.isChecked())
                
    def load_ui_states(self):
        settings = config.settings
        try:
            boards_count = int(settings.value("ui_boards", 1))
            self.spin_boards.setValue(boards_count)
            self.loop_count.setText(str(settings.value("ui_loop_count", "1")))
            self.input_exp_date.setText(str(settings.value("ui_exp_date", "2024-03-05")))
            self.chk_write_date.setChecked(str(settings.value("ui_write_date", "false")).lower() == "true")
            self.combo_sn_fmt.setCurrentText(str(settings.value("ui_sn_fmt", "DEC")))
            self.input_exp_sn.setText(str(settings.value("ui_exp_sn", "1")))
            
            write_sn_str = str(settings.value("ui_write_sn", "False")).lower()
            auto_inc_str = str(settings.value("ui_auto_inc", "False")).lower()
            led_toggle_str = str(settings.value("ui_led_toggle", "False")).lower()
            self.chk_write_sn.setChecked(write_sn_str == "true")
            self.chk_auto_inc.setChecked(auto_inc_str == "true")
            self.chk_led.setChecked(led_toggle_str == "true")
            
            used_ports = set()
            for board in self.boards:
                bid = board.board_id
                port = str(settings.value(f"ui_board_{bid}_port", f"COM{5 + bid}"))
                if port != "None" and port in used_ports:
                    port = "None"
                
                board.combo_port.setCurrentText(port)
                if port != "None":
                    used_ports.add(port)
                
                for i, chk in enumerate(board.ch_checkboxes):
                    ch_str = str(settings.value(f"ui_board_{bid}_ch_{i+1}", "True")).lower()
                    chk.setChecked(ch_str == "true")
        except Exception as e:
            logging.getLogger('IBQtools').error(f"Failed to load UI states: {e}")
