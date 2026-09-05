import os
import sys
import time
from PySide6.QtCore import QThread, Signal, Slot

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calibrators.utils import format_df4000_breakdown, write_calibration_log_file
from calibrators.verifiers import run_post_verify
from calibrators.smbus_comm import SMBusCommunicatorMixin
from calibrators.fw_detector import FWDetectorMixin
from calibrators.hw_calib import HWCalibratorMixin

BQ_SMBUS_ADDR = 0x0B

class CalibrationThread(QThread, SMBusCommunicatorMixin, FWDetectorMixin, HWCalibratorMixin):
    log_signal = Signal(str)
    row_signal = Signal(str, int, str, str) # param, channel, measured/value, status
    clear_ch_signal = Signal(int)
    play_sound_signal = Signal(bool)
    finished_signal = Signal(bool)
    limits_update_signal = Signal(dict)
    
    def __init__(self, port, channels, script_dir, script_base, targets, ic_name, limits=None, limits_per_ch=None):
        super().__init__()
        self.port = port
        self.channels = channels
        self.ch = channels[0] if channels else 1
        self.addr = BQ_SMBUS_ADDR
        self.script_dir = script_dir
        self.script_base = script_base
        self.targets = targets
        if isinstance(targets, dict) and "per_ch" in targets:
            self.targets_per_ch = targets["per_ch"]
        else:
            self.targets_per_ch = {}
        self.ic_name = ic_name
        self.limits = limits if limits is not None else {}
        self.limits_per_ch = limits_per_ch if limits_per_ch is not None else {}
        self.ser = None
        self._running = True
        self.relay_queue = []
        
        self.limits_update_signal.connect(self.on_limits_updated)
        
        self.cal_log_buffer = {}
        self.active_cells = 4 # Default
        self.history = {} # Store history of statuses for sliding window
        
    def stop(self):
        self._running = False
            
    @Slot(dict)
    def on_limits_updated(self, new_limits):
        self.limits = new_limits
        self._log(f"DEBUG THREAD: Received new limits via signal: V_Cell 2={self.limits.get('V_Cell 2')}")

    def _log(self, msg):
        self.log_signal.emit(f"[CH{self.ch}] {msg}")

    def _apply_history_filter(self, param_key, param_name, raw_status):
        """Applies sliding window / majority noise filtering to measurement status history."""
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
                if pass_count >= 3:
                    return "PASS"
                elif fail_count >= 3:
                    return "FAIL"
                else:
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
            if raw_status == "FAIL":
                if final_status == "PASS":
                    self._log(f"    (Filtered Noise) {param_key} val={val} limits=({min_val}, {max_val}) - Ignored due to majority PASS")
                else:
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

    def _run_monitoring_loop(self):
        """Runs continuous post-verification monitoring across active channels."""
        self._log("--- Entering Continuous Monitoring Mode ---")
        consecutive_fails = {ch: 0 for ch in self.channels}
        while self._running:
            # Process queued relay toggles
            if self.relay_queue:
                for rq_ch, rq_on in list(self.relay_queue):
                    old_ch = self.ch
                    self.ch = rq_ch
                    self._set_relay(rq_on)
                    self.ch = old_ch
                self.relay_queue.clear()
                
            any_ch_alive = False
            for ch in self.channels:
                if not self._running:
                    break
                self.ch = ch
                if consecutive_fails[ch] >= 2:
                    continue # Skip checking this channel if it's already dead
                    
                if not self.post_verify():
                    consecutive_fails[ch] += 1
                    if consecutive_fails[ch] >= 2:
                        self._log(f"Error: Communication lost on CH{ch} during monitoring.")
                else:
                    consecutive_fails[ch] = 0
                    any_ch_alive = True
                    
            if not any_ch_alive:
                self._log("All channels lost communication. Exiting monitoring mode.")
                break
                
            time.sleep(0.3)

    def run(self):
        total_start_time = time.time()
        import serial
        self._log(f"[INFO] Connecting to {self.port} for Calibration...")
        self.ser = None
        try:
            self.ser = serial.Serial(self.port, 115200, timeout=1.5)
            self.ser.reset_input_buffer()
        except Exception as e:
            self._log(f"[ERROR] Failed to open {self.port}: {e}")
            self.finished_signal.emit(False)
            return

        try:
            run_mode = self.targets.get("run_mode", "voltage")
            modes_to_run = ["voltage", "current"] if run_mode == "all" else [run_mode]
            ch_status_map = {}
            ch_mask = sum(1 << (ch - 1) for ch in self.channels)

            calib_done = self._run_hw_calibration_phase(modes_to_run, ch_mask, ch_status_map, run_mode)

            total_cal_time = time.time() - total_start_time
            self._log(f"[TIME] Total Pure RP2040 Hardware Calibration Time (All Channels): {total_cal_time:.3f} sec")

            if not calib_done:
                self._log("Error: RP2040 hardware calibration timed out or failed to reach DONE state.")

            # Phase 2: Post Verification & CSV Logging Loop
            self._log("--- Running Post-Verification & Measurement Capture ---")
            success = calib_done and all(ch_status_map.values()) if ch_status_map else False
            for ch in self.channels:
                if not self._running:
                    break
                self.ch = ch
                if self.targets_per_ch and ch in self.targets_per_ch:
                    self.targets = self.targets_per_ch[ch]
                
                self.post_verify()
                serial_num, mfg_date = self._read_mfg_info()
                self._write_cal_log(self.ch, serial_num, mfg_date, ch_status_map.get(ch, False))
                
            # 3. Verification & Continuous Monitoring
            if success:
                self.play_sound_signal.emit(True)
                self._run_monitoring_loop()
                self._log("--- Calibration Sequence Completed ---")
                self.finished_signal.emit(success)
            else:
                self.play_sound_signal.emit(False)
                self.finished_signal.emit(success)

        except Exception as e:
            import traceback
            self._log(f"CRASH in CalibrationThread: {e}\n{traceback.format_exc()}")
            self.play_sound_signal.emit(False)
            self.finished_signal.emit(False)
        finally:
            # SAFETY: Always ensure relays are turned off!
            for ch in self.channels:
                self.ch = ch
                try:
                    self._set_relay(False)
                except Exception:
                    pass # Ignore if port is already closed
            if hasattr(self, 'ser') and self.ser.is_open:
                self.ser.close()

    def _write_cal_log(self, ch, serial_num, mfg_date, overall_success):
        from config import config
        path = config.get_cal_log_path()
        if not path:
            return
        ch_data = self.cal_log_buffer.get(ch, {})
        if not ch_data:
            return
        try:
            write_calibration_log_file(path, ch, serial_num, mfg_date, ch_data, overall_success)
        except Exception as e:
            self._log(f"Failed to write Cal Log: {e}")
