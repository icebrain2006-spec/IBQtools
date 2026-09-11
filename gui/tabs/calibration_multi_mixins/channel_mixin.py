from PySide6.QtWidgets import QMenu
import serial

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import IC_CONFIGS
from updater_thread import make_packet, CMD_RELAY_SET


class MultiCalibrationChannelMixin:
    """Mixin for 18-channel selection, input persistence across 18 channels, and multi-port manual relay toggling."""

    def _save_current_channel_inputs(self):
        ic_name = self.combo_ic.currentText()
        if not ic_name or not hasattr(self, 'board_current_ch'):
            return
        if not isinstance(self.dynamic_inputs, dict):
            return
            
        for board_idx, board_inputs in self.dynamic_inputs.items():
            if not isinstance(board_inputs, dict):
                continue
            ch = self.board_current_ch.get(board_idx, (board_idx - 1) * 6 + 1)
            for key, line_edit in board_inputs.items():
                val = line_edit.text()
                self.settings.setValue(f"calib_multi_ch{ch}_{ic_name}_{key}_val", val)
                
        for board_idx, board_checks in self.dynamic_checks.items():
            if not isinstance(board_checks, dict):
                continue
            ch = self.board_current_ch.get(board_idx, (board_idx - 1) * 6 + 1)
            for key, chk in board_checks.items():
                self.settings.setValue(f"calib_multi_ch{ch}_{ic_name}_{key}_chk", chk.isChecked())

    def _load_board_inputs(self, board_idx, ch):
        ic_name = self.combo_ic.currentText()
        if ic_name not in IC_CONFIGS:
            return
        config = IC_CONFIGS[ic_name]
        
        all_defaults = {}
        for section in ["voltage", "temperature", "current"]:
            if section in config and config[section]:
                all_defaults.update(config[section])
                
        if not hasattr(self, 'dynamic_inputs') or board_idx not in self.dynamic_inputs:
            return
            
        for key, line_edit in self.dynamic_inputs[board_idx].items():
            line_edit.blockSignals(True)
            default_data = all_defaults.get(key, "")
            default_val = default_data["val"] if isinstance(default_data, dict) else default_data
            global_fallback = self.settings.value(f"calib_{ic_name}_{key}_val", default_val)
            saved_val = self.settings.value(f"calib_multi_ch{ch}_{ic_name}_{key}_val", global_fallback)
            line_edit.setText(str(saved_val))
            line_edit.blockSignals(False)
            
        if board_idx in self.dynamic_checks:
            for key, chk in self.dynamic_checks[board_idx].items():
                chk.blockSignals(True)
                global_fallback = self.settings.value(f"calib_{ic_name}_{key}_chk", "true")
                saved_check = self.settings.value(f"calib_multi_ch{ch}_{ic_name}_{key}_chk", global_fallback)
                is_checked = True if str(saved_check).lower() == "true" else False
                chk.setChecked(is_checked)
                chk.blockSignals(False)
            
        lbl = getattr(self, f"lbl_ch_board_{board_idx}", None)
        if lbl:
            ch_in_board = ((ch - 1) % 6) + 1
            lbl.setText(f"CH {ch_in_board}")

    @property
    def current_channel(self):
        return getattr(self, 'board_current_ch', {}).get(1, 1)

    @current_channel.setter
    def current_channel(self, value):
        if not hasattr(self, 'board_current_ch'):
            self.board_current_ch = {1: 1, 2: 7, 3: 13}
        self.board_current_ch[1] = value

    def _on_prev_board_ch(self, board_idx):
        cur_ch = self.board_current_ch.get(board_idx, (board_idx - 1) * 6 + 1)
        min_ch = (board_idx - 1) * 6 + 1
        max_ch = board_idx * 6
        new_ch = cur_ch - 1
        if new_ch < min_ch:
            new_ch = max_ch
        self.board_current_ch[board_idx] = new_ch
        self._load_board_inputs(board_idx, new_ch)

    def _on_next_board_ch(self, board_idx):
        cur_ch = self.board_current_ch.get(board_idx, (board_idx - 1) * 6 + 1)
        min_ch = (board_idx - 1) * 6 + 1
        max_ch = board_idx * 6
        new_ch = cur_ch + 1
        if new_ch > max_ch:
            new_ch = min_ch
        self.board_current_ch[board_idx] = new_ch
        self._load_board_inputs(board_idx, new_ch)

    def _on_header_context_menu(self, pos):
        logical_index = self.table_data.horizontalHeader().logicalIndexAt(pos)
        if 1 <= logical_index <= 18:
            ch = logical_index
            board_idx = ((ch - 1) // 6) + 1
            ch_in_board = ((ch - 1) % 6) + 1
            menu = QMenu(self)
            action_on = menu.addAction(f"Turn Relay ON for B{board_idx}-CH{ch_in_board}")
            action_off = menu.addAction(f"Turn Relay OFF for B{board_idx}-CH{ch_in_board}")
            
            action_on.triggered.connect(lambda: self._toggle_manual_relay(ch, True))
            action_off.triggered.connect(lambda: self._toggle_manual_relay(ch, False))
            
            menu.exec(self.table_data.horizontalHeader().mapToGlobal(pos))

    def _toggle_manual_relay(self, ch, on):
        board_idx = ((ch - 1) // 6) + 1
        ch_in_board = ((ch - 1) % 6) + 1
        
        port_combo = getattr(self, f"combo_port_{board_idx}", None)
        port = port_combo.currentText() if port_combo else ""
        if not port or "Select" in port:
            self.log(f"Error: Please select a valid COM port for Board #{board_idx} to toggle relay.")
            return
            
        if hasattr(self, 'cal_thread') and self.cal_thread and self.cal_thread.isRunning():
            if hasattr(self.cal_thread, 'enqueue_relay'):
                self.cal_thread.enqueue_relay(ch, on)
                self.log(f"Queued Manual Relay {'ON' if on else 'OFF'} for B{board_idx}-CH{ch_in_board} via active thread.")
                return
            
        try:
            ser = serial.Serial(port, 115200, timeout=1.0)
            mask = (1 << (ch_in_board - 1)) if on else 0
            packet = make_packet(CMD_RELAY_SET, bytes([mask]))
            ser.reset_input_buffer()
            ser.write(packet)
            
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
            self.log(f"Manual Relay {'ON' if on else 'OFF'} executed for B{board_idx}-CH{ch_in_board} on {port}.")
        except Exception as e:
            self.log(f"Error toggling relay on {port}: {e}")
