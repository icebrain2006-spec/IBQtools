from PySide6.QtWidgets import QMenu
import serial

from gui.models import IC_CONFIGS
from gui.updater_thread import make_packet, CMD_RELAY_SET


class CalibrationChannelMixin:
    """Mixin for channel selection, input value persistence across channels, and manual relay toggling."""

    def _save_current_channel_inputs(self):
        ic_name = self.combo_ic.currentText()
        if not ic_name:
            return
        ch = self.current_channel
        for key, line_edit in self.dynamic_inputs.items():
            val = line_edit.text()
            self.settings.setValue(f"calib_ch{ch}_{ic_name}_{key}_val", val)
        for key, chk in self.dynamic_checks.items():
            self.settings.setValue(f"calib_ch{ch}_{ic_name}_{key}_chk", chk.isChecked())

    def _load_channel_inputs(self, ch):
        ic_name = self.combo_ic.currentText()
        if ic_name not in IC_CONFIGS:
            return
        config = IC_CONFIGS[ic_name]
        
        all_defaults = {}
        for section in ["voltage", "temperature", "current"]:
            if section in config and config[section]:
                all_defaults.update(config[section])
                
        for key, line_edit in self.dynamic_inputs.items():
            line_edit.blockSignals(True)
            default_data = all_defaults.get(key, "")
            default_val = default_data["val"] if isinstance(default_data, dict) else default_data
            global_fallback = self.settings.value(f"calib_{ic_name}_{key}_val", default_val)
            saved_val = self.settings.value(f"calib_ch{ch}_{ic_name}_{key}_val", global_fallback)
            line_edit.setText(str(saved_val))
            line_edit.blockSignals(False)
            
        for key, chk in self.dynamic_checks.items():
            chk.blockSignals(True)
            global_fallback = self.settings.value(f"calib_{ic_name}_{key}_chk", "true")
            saved_check = self.settings.value(f"calib_ch{ch}_{ic_name}_{key}_chk", global_fallback)
            is_checked = True if str(saved_check).lower() == "true" else False
            chk.setChecked(is_checked)
            chk.blockSignals(False)
            
        if hasattr(self, 'lbl_current_ch'):
            self.lbl_current_ch.setText(f"CH {ch}")

    def _switch_channel(self, new_ch):
        if new_ch < 1:
            new_ch = 6
        elif new_ch > 6:
            new_ch = 1
        if new_ch == self.current_channel:
            return
        self._save_current_channel_inputs()
        self.current_channel = new_ch
        self._load_channel_inputs(new_ch)

    def _on_prev_ch(self):
        self._switch_channel(self.current_channel - 1)

    def _on_next_ch(self):
        self._switch_channel(self.current_channel + 1)

    def _on_header_context_menu(self, pos):
        logical_index = self.table_data.horizontalHeader().logicalIndexAt(pos)
        if 1 <= logical_index <= 6:
            ch = logical_index
            menu = QMenu(self)
            action_on = menu.addAction(f"Turn Relay ON for CH{ch}")
            action_off = menu.addAction(f"Turn Relay OFF for CH{ch}")
            
            action_on.triggered.connect(lambda: self._toggle_manual_relay(ch, True))
            action_off.triggered.connect(lambda: self._toggle_manual_relay(ch, False))
            
            menu.exec(self.table_data.horizontalHeader().mapToGlobal(pos))

    def _toggle_manual_relay(self, ch, on):
        port = self.combo_port.currentText()
        if not port or "Select" in port:
            self.log("Error: Please select a COM port first to toggle relay.")
            return
            
        if hasattr(self, 'cal_thread') and self.cal_thread and self.cal_thread.isRunning():
            if hasattr(self.cal_thread, 'enqueue_relay'):
                self.cal_thread.enqueue_relay(ch, on)
                self.log(f"Queued Manual Relay {'ON' if on else 'OFF'} for CH{ch} via active thread.")
                return
            
        try:
            ser = serial.Serial(port, 115200, timeout=1.0)
            mask = (1 << (ch - 1)) if on else 0
            packet = make_packet(CMD_RELAY_SET, bytes([mask]))
            ser.reset_input_buffer()
            ser.write(packet)
            
            # Read response to prevent buffer accumulation on device
            rx = bytearray()
            while True:
                b = ser.read(1)
                if not b: break
                if b[0] == 0x02:
                    rx.extend(b)
                    break
            if rx:
                len_bytes = ser.read(2)
                rx.extend(len_bytes)
                if len(len_bytes) >= 2:
                    import struct
                    length = struct.unpack(">H", len_bytes)[0]
                    rx.extend(ser.read(length + 3))
                    
            ser.close()
            self.log(f"Manual Relay {'ON' if on else 'OFF'} executed for CH{ch}.")
        except Exception as e:
            self.log(f"Error toggling relay: {e}")
