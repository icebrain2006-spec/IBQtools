import os
import sys
import time
import serial
from PySide6.QtCore import QThread, Signal, Slot

from gui.calibrators.utils import format_df4000_breakdown, write_calibration_log_file
from gui.calibrators.verifiers import run_post_verify
from gui.calibrators.smbus_comm import SMBusCommunicatorMixin
from gui.calibrators.fw_detector import FWDetectorMixin
from gui.calibrators.hw_calib import HWCalibratorMixin
from gui.updater_thread import make_packet, CMD_RELAY_SET

BQ_SMBUS_ADDR = 0x0B


def schedule_current_calib_batches(selected_channels):
    """
    Partitions selected global channels (1..18) into 3-channel group batches for Current Calibration.
    - Group 1: CH 1..3  (Board 1 Bank 1)
    - Group 2: CH 4..6  (Board 1 Bank 2)
    - Group 3: CH 7..9  (Board 2 Bank 1)
    - Group 4: CH 10..12 (Board 2 Bank 2)
    - Group 5: CH 13..15 (Board 3 Bank 1)
    - Group 6: CH 16..18 (Board 3 Bank 2)
    Channels belonging to the same 3-channel group run current calibration simultaneously.
    """
    groups = {}
    for ch in sorted(selected_channels):
        grp_idx = (ch - 1) // 3
        if grp_idx not in groups:
            groups[grp_idx] = []
        groups[grp_idx].append(ch)

    return [groups[k] for k in sorted(groups.keys())]


class MultiCalibrationThread(QThread, SMBusCommunicatorMixin, FWDetectorMixin, HWCalibratorMixin):
    log_signal = Signal(str)
    row_signal = Signal(str, int, str, str) # param, global_ch, measured/value, status
    clear_ch_signal = Signal(int)
    play_sound_signal = Signal(bool)
    finished_signal = Signal(bool)
    limits_update_signal = Signal(dict)

    def __init__(self, ports_map, channels, targets, ic_name, limits=None, limits_per_ch=None):
        super().__init__()
        # ports_map: {1: 'COM3', 2: 'COM4', 3: 'COM5'}
        self.ports_map = ports_map
        self.channels = sorted(channels)
        self.ch = self.channels[0] if self.channels else 1
        self.addr = BQ_SMBUS_ADDR
        self.targets = targets
        self.targets_per_ch = targets.get("per_ch", {}) if isinstance(targets, dict) else {}
        self.ic_name = ic_name
        self.limits = limits if limits is not None else {}
        self.limits_per_ch = limits_per_ch if limits_per_ch is not None else {}
        
        self.ser_map = {} # {board_idx: serial_handle}
        self.ser = None # Current active serial handle for SMBusCommunicatorMixin
        self._running = True
        self.relay_queue = []
        
        self.limits_update_signal.connect(self.on_limits_updated)
        self.cal_log_buffer = {}
        self.active_cells = 4
        self.history = {}

    def stop(self):
        self._running = False

    @Slot(dict)
    def on_limits_updated(self, new_limits):
        self.limits = new_limits

    def _log(self, msg):
        board_idx = ((self.ch - 1) // 6) + 1
        ch_in_board = ((self.ch - 1) % 6) + 1
        self.log_signal.emit(f"[B{board_idx}-CH{ch_in_board}] {msg}")

    def _apply_history_filter(self, param_key, param_name, raw_status):
        if param_name not in self.history:
            self.history[param_name] = {}
        if self.ch not in self.history[param_name]:
            self.history[param_name][self.ch] = []
            
        ch_hist = self.history[param_name][self.ch]
        ch_hist.append(raw_status)
        if len(ch_hist) > 2:
            ch_hist.pop(0)
            
        if "BQ78350" in self.ic_name.upper() and param_key.startswith("V_Cell"):
            pass_count = ch_hist.count("PASS")
            fail_count = ch_hist.count("FAIL")
            if len(ch_hist) >= 3:
                return "PASS" if pass_count >= fail_count else "FAIL"
            else:
                return raw_status
        else:
            return "FAIL" if "FAIL" in ch_hist else raw_status

    def emit_result(self, param_key, param_name, raw_adc, val, is_gain=False, suffix="", force_fail=False):
        raw_status = "PASS" if is_gain else "INFO"
        ch_limits = self.limits_per_ch.get(self.ch, self.limits)
        min_val, max_val = ch_limits.get(param_key, (None, None))
        
        if param_key in ch_limits and min_val is not None and max_val is not None:
            raw_status = "PASS" if (min_val <= val <= max_val) else "FAIL"
                
        if force_fail:
            raw_status = "FAIL"
                
        if is_gain:
            if raw_status == "FAIL":
                self._log(f"FAIL: {param_key} val={val} limits=({min_val}, {max_val})")
            self.row_signal.emit(param_name, self.ch, str(raw_adc), raw_status)
        else:
            final_status = self._apply_history_filter(param_key, param_name, raw_status)
            if raw_status == "FAIL" and final_status != "PASS":
                self._log(f"FAIL: {param_key} val={val} limits=({min_val}, {max_val})")
            self.row_signal.emit(param_name, self.ch, f"{val}{suffix}", final_status)
            
        if self.ch not in self.cal_log_buffer:
            self.cal_log_buffer[self.ch] = {}
        min_v, max_v = self.limits.get(param_key, (None, None))
        range_str = f"{min_v}{suffix} - {max_v}{suffix}" if min_v is not None and max_v is not None else "0 - 65535"
        if is_gain: range_str = "0 - 65535"
        
        stored_val = raw_adc if is_gain else val
        self.cal_log_buffer[self.ch][param_key] = {
            'value': f"{stored_val}{suffix}",
            'range': range_str
        }

    def format_df4000_breakdown(self, df_bytes, label="0x4000 DF DUMP"):
        return format_df4000_breakdown(df_bytes, label)

    def post_verify(self):
        return run_post_verify(self)

    def _set_board_relays(self, board_idx, mask):
        ser = self.ser_map.get(board_idx)
        if not ser or not ser.is_open:
            return
        packet = make_packet(CMD_RELAY_SET, bytes([mask]))
        ser.reset_input_buffer()
        ser.write(packet)
        time.sleep(0.05)

    def run(self):
        total_start_time = time.time()
        self.log_signal.emit("[INFO] Opening serial ports for RP2040 Boards...")
        
        # 1. Open serial ports for configured boards
        for board_idx, port in self.ports_map.items():
            if port and "Select" not in port and port != "None":
                try:
                    ser_obj = serial.Serial(port, 115200, timeout=1.5)
                    ser_obj.reset_input_buffer()
                    self.ser_map[board_idx] = ser_obj
                    self.log_signal.emit(f"[INFO] Connected Board #{board_idx} on {port}")
                except Exception as e:
                    self.log_signal.emit(f"[ERROR] Failed to open Board #{board_idx} port {port}: {e}")

        if not self.ser_map:
            self.log_signal.emit("[ERROR] No valid serial connections opened.")
            self.finished_signal.emit(False)
            return

        try:
            run_mode = self.targets.get("run_mode", "voltage")
            ch_status_map = {}

            if run_mode in ("current", "all"):
                # --- Execute Current Calibration via 3-Channel Group Scheduler ---
                current_batches = schedule_current_calib_batches(self.channels)
                self.log_signal.emit(f"[INFO] Scheduled {len(current_batches)} Batch(es) for Current Calibration.")
                
                for batch_no, batch_channels in enumerate(current_batches, 1):
                    if not self._running: break
                    target_board_idx = ((batch_channels[0] - 1) // 6) + 1
                    ch_desc = ", ".join([f"B{target_board_idx}-CH{((c-1)%6)+1}" for c in batch_channels])
                    self.log_signal.emit(f"--- Running Current Calib Batch {batch_no}/{len(current_batches)}: [{ch_desc}] (Simultaneous) ---")
                    
                    ser_obj = self.ser_map.get(target_board_idx)
                    if not ser_obj:
                        self.log_signal.emit(f"[ERROR] Board #{target_board_idx} serial connection not available.")
                        continue
                    self.ser = ser_obj
                    self.ch = batch_channels[0]
                    
                    # Compute board channel mask for this batch (bits 0..5)
                    batch_ch_mask = sum(1 << (((c - 1) % 6)) for c in batch_channels)
                    
                    # 1. Set relays ON for batch channels on target board, OFF on other boards
                    for b_idx_item in (1, 2, 3):
                        if b_idx_item in self.ser_map:
                            mask = batch_ch_mask if b_idx_item == target_board_idx else 0
                            self._set_board_relays(b_idx_item, mask)
                            
                    # 2. Execute Current HW Calibration simultaneously for batch channels
                    saved_channels = self.channels
                    self.channels = batch_channels
                    try:
                        res = self._run_hw_calibration_phase(["current"], batch_ch_mask, ch_status_map, "current")
                    finally:
                        self.channels = saved_channels

                    # 3. Reset relays OFF after batch
                    if target_board_idx in self.ser_map:
                        self._set_board_relays(target_board_idx, 0)
                    time.sleep(0.1)

            if run_mode in ("voltage", "temp", "all"):
                # --- Execute Voltage/Temp Calibration ---
                modes = ["voltage"] if run_mode == "voltage" else (["temp"] if run_mode == "temp" else ["voltage"])
                self.log_signal.emit(f"--- Running {run_mode.upper()} Calibration ---")
                
                # Group selected channels by board
                board_channels = {1: [], 2: [], 3: []}
                for ch in self.channels:
                    b_idx = ((ch - 1) // 6) + 1
                    board_channels[b_idx].append(ch)
                    
                for b_idx, b_chs in board_channels.items():
                    if not b_chs or not self._running: continue
                    ser_obj = self.ser_map.get(b_idx)
                    if not ser_obj: continue
                    self.ser = ser_obj
                    
                    ch_mask = sum(1 << (((c - 1) % 6)) for c in b_chs)
                    for ch in b_chs:
                        self.ch = ch
                        if self.targets_per_ch and ch in self.targets_per_ch:
                            self.targets = self.targets_per_ch[ch]
                        self._run_hw_calibration_phase(modes, ch_mask, ch_status_map, run_mode)

            total_cal_time = time.time() - total_start_time
            self.log_signal.emit(f"[TIME] Total 18-Channel Calibration Time: {total_cal_time:.3f} sec")

            # Post verification across all channels
            self.log_signal.emit("--- Running Post-Verification & Log Recording ---")
            success = len(ch_status_map) > 0 and all(ch_status_map.values())
            for ch in self.channels:
                if not self._running: break
                self.ch = ch
                b_idx = ((ch - 1) // 6) + 1
                self.ser = self.ser_map.get(b_idx)
                if not self.ser: continue
                if self.targets_per_ch and ch in self.targets_per_ch:
                    self.targets = self.targets_per_ch[ch]
                    
                self.post_verify()
                serial_num, mfg_date = self._read_mfg_info()
                self._write_cal_log(self.ch, serial_num, mfg_date, ch_status_map.get(ch, False))

            if success:
                self.play_sound_signal.emit(True)
                self.log_signal.emit("--- 18-Channel Calibration Finished Successfully ---")
                self.finished_signal.emit(True)
            else:
                self.play_sound_signal.emit(False)
                self.finished_signal.emit(False)

        except Exception as e:
            import traceback
            self.log_signal.emit(f"CRASH in MultiCalibrationThread: {e}\n{traceback.format_exc()}")
            self.play_sound_signal.emit(False)
            self.finished_signal.emit(False)
        finally:
            # Turn OFF all relays on exit
            for b_idx, ser_obj in self.ser_map.items():
                try:
                    packet = make_packet(CMD_RELAY_SET, bytes([0]))
                    ser_obj.write(packet)
                    ser_obj.close()
                except Exception:
                    pass

    def _write_cal_log(self, ch, serial_num, mfg_date, overall_success):
        from gui.config import config
        path = config.get_cal_log_path()
        if not path: return
        ch_data = self.cal_log_buffer.get(ch, {})
        if not ch_data: return
        try:
            write_calibration_log_file(path, ch, serial_num, mfg_date, ch_data, overall_success)
        except Exception as e:
            self._log(f"Failed to write Cal Log: {e}")
