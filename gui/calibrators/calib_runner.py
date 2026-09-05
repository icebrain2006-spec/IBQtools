import os
import sys
import time
import struct
from PySide6.QtCore import QThread, Signal, Slot

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from updater_thread import make_packet, parse_response, RESP_OK, CMD_I2C_RAW, CMD_SMBUS_CMD, CMD_SMBUS_POLL_BLOCK, CMD_RELAY_SET, PROTOCOL_STX
from calibrators.utils import detect_dataflash_offset, load_calibration_offsets, load_adc_offset_0xf081, load_dastatus1_offset_0x0071, load_dastatus2_offset_0x0072, crc8_smbus_byte, smbus_pec_calculate, float_to_xemics, xemics_to_float, format_df4000_breakdown
from calibrators.verifiers import run_post_verify

BQ_SMBUS_ADDR = 0x0B
CMD_CALIB_RUN = 0x60
CMD_CALIB_STATUS = 0x61

class CalibrationThread(QThread):
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

    def _send_cmd(self, cmd: int, payload: bytes = b""):
        """Sends command packet to RP2040 and parses response packet."""
        if not self.ser or not self.ser.is_open:
            return None, None
        packet = make_packet(cmd, payload)
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        rx = self._read_packet()
        return parse_response(rx)

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
        
    def _set_relay(self, on: bool, mask: int = None):
        if mask is None:
            mask = (1 << (self.ch - 1)) if on else 0
        elif not on:
            mask = 0

        self._send_cmd(CMD_RELAY_SET, bytes([mask]))
        self._log(f"    [Relay] {'ON' if on else 'OFF'} (mask: 0x{mask:02X})")
        time.sleep(0.1) # Command process delay
        
    def _log(self, msg):
        self.log_signal.emit(f"[CH{self.ch}] {msg}")

    def smbus_write_word(self, reg, val):
        payload = struct.pack('<BBBBBBH', self.ch, self.addr, reg, 0, 2, 0, val)
        cmd, resp = self._send_cmd(CMD_SMBUS_CMD, payload)
        return isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK
        
    def smbus_write_block_raw(self, cmd_reg, data_bytes, use_pec=True):
        tx_data = bytearray([cmd_reg, len(data_bytes)]) + bytearray(data_bytes)
        if use_pec:
            pec_data = bytearray([(self.addr << 1)]) + tx_data
            pec = smbus_pec_calculate(pec_data)
            tx_data.append(pec)
            
        payload = bytes([self.ch, self.addr, len(tx_data), 0]) + tx_data
        cmd, resp = self._send_cmd(CMD_I2C_RAW, payload)
        return isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK

    def _read_packet(self):
        start_time = time.time()
        buf = b""
        old_timeout = self.ser.timeout
        self.ser.timeout = 0.05
        try:
            while time.time() - start_time < 0.5:
                rx = self.ser.read(128)
                if rx:
                    buf += rx
                
                stx_idx = buf.find(PROTOCOL_STX)
                if stx_idx != -1 and len(buf) >= stx_idx + 7:
                    length = struct.unpack(">H", buf[stx_idx+1:stx_idx+3])[0]
                    expected_total = length + 6
                    if len(buf) >= stx_idx + expected_total:
                        return buf[stx_idx:stx_idx+expected_total]
        finally:
            self.ser.timeout = old_timeout
        return b""

    def smbus_read_word(self, cmd_reg):
        payload = bytes([self.ch, self.addr, cmd_reg, 1, 2, 0, 0])
        cmd, resp = self._send_cmd(CMD_SMBUS_CMD, payload)
        if isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK:
            return resp[1:3]
        return None

    def smbus_read_block(self, cmd_reg):
        resp = None
        for attempt in range(10):
            if not self._running: return None
            payload = bytes([self.ch, self.addr, cmd_reg, 1, 32, 0, 0])
            cmd, resp = self._send_cmd(CMD_SMBUS_CMD, payload)
            if cmd is None:
                time.sleep(0.05)
                continue
            if isinstance(resp, (bytes, bytearray)) and len(resp) > 0:
                if resp[0] == RESP_OK:
                    return resp[2:2+resp[1]]
                if resp[0] == 0x04 and len(resp) > 1 and resp[1] == 0x04:
                    time.sleep(0.05)
                    continue
            break
        if resp:
            if isinstance(resp, (bytes, bytearray)) and len(resp) > 0:
                err_code = resp[0]
                detail = resp[1] if len(resp) > 1 else 'None'
                self._log(f"    -> Comm Lost: 0x{err_code:02x}, Detail: {detail}")
            else:
                self._log(f"    -> Comm Lost: {resp}")
            self.clear_ch_signal.emit(self.ch)
        return None

    def _exit_rom_mode(self):
        payload = bytes([self.ch, 0x0B, 1, 0, 0x08])
        self._send_cmd(CMD_I2C_RAW, payload)
        time.sleep(0.01)

    def _read_mfg_info(self):
        serial_num = "Unknown"
        mfg_date = "Unknown"
        try:
            # 1st attempt: Direct read (Fast path)
            m_data = self.smbus_read_word(0x1B)
            if not m_data or len(m_data) < 2:
                # 2nd attempt: If direct read fails, exit ROM mode and retry
                self._exit_rom_mode()
                time.sleep(0.1) # Brief wait for BQ firmware mode
                m_data = self.smbus_read_word(0x1B)

            if m_data and len(m_data) >= 2:
                val = struct.unpack('<H', bytes(m_data))[0]
                day = val & 0x1F
                month = (val >> 5) & 0x0F
                year = (val >> 9) + 1980
                mfg_date = f"{year}-{month:02d}-{day:02d}"
                
            s_data = self.smbus_read_word(0x1C)
            if s_data and len(s_data) >= 2:
                val = struct.unpack('<H', bytes(s_data))[0]
                serial_num = f"{val:04X}"
        except Exception as e:
            self._log(f"Error reading Mfg Info: {e}")
        return serial_num, mfg_date

    def _find_header(self, data, header_bytes):
        """Locates header_bytes inside SMBus response data to prevent byte-shift errors."""
        if not data or len(data) < len(header_bytes):
            return -1
        return bytes(data).find(bytes(header_bytes))

    def read_mac_block(self, sub_cmd_bytes):
        """Writes sub-command bytes to 0x44 and reads back response block."""
        self.smbus_write_block_raw(0x44, sub_cmd_bytes)
        time.sleep(0.05)
        return self.smbus_read_block(0x44)

    def _read_firmware_version(self):
        """Reads BQ IC firmware version via MAC 0x0002. Returns (device, version, major, minor) or None."""
        data = self.read_mac_block([0x02, 0x00])
        
        if not data:
            self._log("Failed to detect firmware version (0x0002).")
            return None
            
        self._log(f"MAC 0x0002 Raw Read: {data.hex(' ')}")
        
        idx = self._find_header(data, [0x02, 0x00])
        if idx == -1:
            self._log("Warning: 0x0002 echo not found, using index 0")
            idx = 0
                
        if idx + 5 < len(data):
            device = struct.unpack_from('>H', data, idx + 2)[0]
            major = data[idx + 4]
            minor = data[idx + 5]
            version = (major << 8) | minor
            self._log(f"Detected Firmware: Device 0x{device:04X}, Version V{major}.{minor:02d}")
            return device, version, major, minor
        else:
            self._log("Failed to parse firmware version due to invalid length.")
            return None

    def _load_dataflash_map(self, version, major, minor):
        """Looks up DataFlash offset and loads parameter offsets dictionary."""
        offset, csv_name = detect_dataflash_offset(self.ic_name, version, "DA Configuration")
        if offset is None:
            self._log(f"Warning: Could not find DA Configuration offset for {self.ic_name} V{major}.{minor:02d}. Defaulting to 0x4000.")
            return 0x4000
        else:
            self.csv_name = csv_name
            self.df_offsets = load_calibration_offsets(csv_name)
            self._log(f"Loaded CSV: {csv_name}, DA Config Offset: {offset}")
            return 0x4000 + offset

    def _detect_active_cells(self, da_addr):
        """Reads DA Configuration and determines active cell count for the pack."""
        self._log(f"Reading DA Configuration at 0x{da_addr:04X}...")
        addr_bytes = [da_addr & 0xFF, (da_addr >> 8) & 0xFF]
        da_data = self.read_mac_block(addr_bytes)
        
        if da_data:
            self._log(f"DA Config Raw Read: {da_data.hex(' ')}")
            
            idx = self._find_header(da_data, addr_bytes)
            if idx == -1 and len(da_data) >= 4:
                self._log("Warning: Address echo not found in DA Config read, falling back to index 0.")
                idx = 0
                    
            if idx != -1 and idx + 3 < len(da_data):
                da_val = struct.unpack_from('<H', da_data, idx + 2)[0]
                if "BQ78350" in self.ic_name.upper():
                    da_val = struct.unpack_from('>H', da_data, idx + 3)[0]
                    self.afe_cell_map = da_val
                    self.active_cells = bin(da_val).count('1')
                    self._log(f"Parsed AFE Cell Map: 0x{da_val:04X} -> Detected {self.active_cells} active cells.")
                else:
                    cc0 = (da_val >> 0) & 1
                    cc1 = (da_val >> 1) & 1
                    self.active_cells = ((cc1 << 1) | cc0) + 1
                    self._log(f"Parsed DA_VAL: 0x{da_val:04X} -> Detected {self.active_cells} active cells (CC1={cc1}, CC0={cc0}).")
                return True
            else:
                self._log("Failed to locate address echo in DA Config read.")
                
        self._log("Failed to read DA Configuration. Assuming 4 cells.")
        self.active_cells = 4
        return True

    def detect_firmware_and_config(self):
        """Orchestrates firmware detection, DataFlash offset mapping, and cell count detection."""
        fw_info = self._read_firmware_version()
        if not fw_info:
            return False

        device, version, major, minor = fw_info
        da_addr = self._load_dataflash_map(version, major, minor)
        return self._detect_active_cells(da_addr)

    def format_df4000_breakdown(self, df_bytes, label="0x4000 DF DUMP"):
        return format_df4000_breakdown(df_bytes, label)

    def post_verify(self):
        return run_post_verify(self)

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
        
            # 1. Detect Firmware and Configuration & 2. Run requested modes
            modes_to_run = []
            if run_mode == "all":
                modes_to_run = ["voltage", "current"]
            else:
                modes_to_run = [run_mode]
            
            ch_status_map = {}
            
            ch_mask = 0
            for ch in self.channels:
                ch_mask |= (1 << (ch - 1))

            for mode_name in modes_to_run:
                self._log(f"\n--- Executing Hardware Calibration Mode: {mode_name.upper()} ---")
                mode_code = 0 if mode_name == "voltage" else (1 if mode_name == "current" else 2)

                # Pre-calibration 0x4000 DF Dump Checkpoint
                for ch in self.channels:
                    df_pre = self.read_mac_block([0x00, 0x40])
                    if df_pre:
                        stage_tag = "1. BEFORE VOLTAGE" if mode_name == "voltage" else "3. BEFORE CURRENT"
                        self._log(self.format_df4000_breakdown(df_pre, f"CH{ch} {stage_tag} CALIBRATION 0x4000 DF BLOCK"))

                # Set Relay state: OFF for Voltage mode, ON for Current mode
                relay_mask = ch_mask if mode_name == "current" else 0
                self._set_relay(mode_name == "current", mask=relay_mask)
                time.sleep(0.4)

                payload_bytes = bytearray([ch_mask, mode_code])
                for ch in range(1, 7):
                    ch_t = self.targets_per_ch.get(ch, self.targets)
                    if mode_name == "current":
                        tc1 = int(abs(ch_t.get('currentma', -2000)))
                        tpk = 0
                        tbt = 0
                    else:
                        tc1 = int(ch_t.get('cell1mv', 3200))
                        tpk = int(ch_t.get('packmv', 12780))
                        tbt = int(ch_t.get('batmv', 12780))
                    payload_bytes.extend(struct.pack(">HHH", tc1, tpk, tbt))
                    if ch in self.channels:
                        if mode_name == "current":
                            self._log(f"    [DEBUG Target CH{ch}] Current={tc1}mA")
                        else:
                            self._log(f"    [DEBUG Target CH{ch}] Cell1={tc1}mV, Pack={tpk}mV, Bat={tbt}mV")

                self._log(f"--- Sending Hardware Calibration Command to RP2040 ({mode_name.upper()} mode, Channels: {self.channels}) ---")
                
                # Send CMD_CALIB_RUN (0x60) packet
                cmd, resp = self._send_cmd(CMD_CALIB_RUN, bytes(payload_bytes))
                if not isinstance(resp, (bytes, bytearray)) or len(resp) == 0 or resp[0] != RESP_OK:
                    err_code = resp[0] if isinstance(resp, (bytes, bytearray)) and len(resp) > 0 else resp
                    self._log(f"Error: RP2040 rejected hardware calibration start command for {mode_name}. (Resp Code: {err_code}, Cmd: {cmd})")
                    self.finished_signal.emit(False)
                    return

                # Poll CMD_CALIB_STATUS (0x61) until state becomes 2 (DONE) or 3 (ERROR)
                calib_done = False
                for _ in range(60): # Max 6 seconds poll timeout
                    if not self._running: break
                    time.sleep(0.1)
                    
                    st_cmd, st_resp = self._send_cmd(CMD_CALIB_STATUS, b"")
                    if isinstance(st_resp, (bytes, bytearray)) and st_resp[0] == RESP_OK:
                        state = st_resp[1]
                        active_channels = st_resp[2]
                        err_channels = st_resp[3]
                        if state == 2: # DONE
                            calib_done = True
                            self._log(f"    [DEBUG RAW RESP] len={len(st_resp)}, hex={bytes(st_resp).hex(' ')}")
                            idx = 4
                            cc_adc_map = {}
                            cc_calc_map = {}
                            for ch in range(1, 7):
                                cell1_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
                                pack_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
                                bat_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
                                ch_succ_val = st_resp[idx]; idx += 1
                                
                                raw_c1_adc = struct.unpack('<H', st_resp[idx:idx+2])[0] if idx + 2 <= len(st_resp) else 0; idx += 2
                                raw_pack_adc = struct.unpack('<H', st_resp[idx:idx+2])[0] if idx + 2 <= len(st_resp) else 0; idx += 2
                                raw_bat_adc = struct.unpack('<H', st_resp[idx:idx+2])[0] if idx + 2 <= len(st_resp) else 0; idx += 2
                                raw_bytes = st_resp[idx:idx+18] if idx + 18 <= len(st_resp) else b""; idx += 18

                                ch_succ = (ch_succ_val == 1)
                                if ch in self.channels:
                                    is_err = (err_channels & (1 << (ch - 1))) != 0
                                    ch_status_map[ch] = ch_status_map.get(ch, True) and ch_succ and not is_err
                                    cc_adc_map[ch] = struct.unpack('<h', struct.pack('<H', cell1_g))[0]
                                    cc_calc_map[ch] = pack_g / 1000.0
                                    self._log(f"    [DEBUG CH{ch}] cell1_g={cell1_g}, pack_g={pack_g}, bat_g={bat_g}, ch_succ_val={ch_succ_val}, is_err={is_err}")
                                    if len(raw_bytes) > 0 and mode_name == "voltage":
                                        self._log(f"    [CH{ch} RAW 0xF081 BLOCK] Hex={bytes(raw_bytes).hex(' ')}")
                                        self._log(f"    [CH{ch} RAW ADC AVG] Cell1_ADC={raw_c1_adc}, Pack_ADC={raw_pack_adc}, Bat_ADC={raw_bat_adc}")
                                    if ch_status_map[ch] and mode_name != "current":
                                        self.ch = ch
                                        self._log(f"    [CH{ch} RP2040 HW Result] PASS -> Cell1 Gain: {cell1_g}, Pack Gain: {pack_g}, Bat Gain: {bat_g}")
                                        df_b = self.read_mac_block([0x00, 0x40])
                                        if df_b:
                                            self._log(self.format_df4000_breakdown(df_b, f"CH{ch} 2. AFTER VOLTAGE CALIBRATION 0x4000 DF BLOCK"))
                                        self.emit_result("Cell 1 Gain", "Cell 1 Gain", str(cell1_g), cell1_g, is_gain=True)
                                        self.emit_result("Pack Gain", "Pack Gain", str(pack_g), pack_g, is_gain=True)
                                        self.emit_result("Bat Gain", "Bat Gain", str(bat_g), bat_g, is_gain=True)
                                        if run_mode != "all":
                                            self.post_verify()
                                    elif not ch_status_map[ch]:
                                        err_stage_map = {
                                            0xE102: "Stage 2 (CAL_EN check FAIL)",
                                            0xE104: "Stage 4 (Raw ADC Sampling FAIL - 0 samples)",
                                            0xE105: "Stage 5 (ADC Average is 0)",
                                            0xE106: "Stage 6 (0x4000 Block Write/Cache FAIL)"
                                        }
                                        stage_desc = err_stage_map.get(cell1_g, f"Unknown Stage Error 0x{cell1_g:04X}")
                                        if cell1_g == 0xE102:
                                            rx_len = pack_g & 0xFF
                                            b0 = (pack_g >> 8) & 0xFF
                                            b1 = bat_g & 0xFF
                                            b2 = (bat_g >> 8) & 0xFF
                                            self._log(f"    [CH{ch} RP2040 HW Result] FAIL -> Reason: {stage_desc} | SMBus Resp Len={rx_len}, Bytes=[{b0:02X} {b1:02X} {b2:02X}]")
                                        else:
                                            self._log(f"    [CH{ch} RP2040 HW Result] FAIL -> Reason: {stage_desc} (err_mask={bin(err_channels)})")
                            
                            if mode_name == "current":
                                for ch in self.channels:
                                    if ch_status_map.get(ch, False):
                                        self.ch = ch
                                        # Read updated 0x4000 block for THIS channel to extract IEEE 754 CC Gain & Capacity Gain
                                        df_b = self.read_mac_block([0x00, 0x40])
                                        if df_b and len(df_b) >= 16:
                                            self._log(f"    [CH{ch} 0x4000 RAW READ BACK ({len(df_b)}b)] {bytes(df_b).hex(' ')}")
                                            base = 2 if (len(df_b) >= 18 and df_b[0] == 0x00 and df_b[1] == 0x40) else 0
                                            cc_gain_read = struct.unpack_from('<f', df_b, base + 6)[0]
                                            cap_gain_read = struct.unpack_from('<f', df_b, base + 10)[0]
                                            mohm_read = 3.714528 / cc_gain_read if (cc_gain_read > 0.1 and cc_gain_read < 20.0) else 0.959
                                            
                                            calc_gain = cc_calc_map.get(ch, 0.0)
                                            calc_mohm = 3.714528 / calc_gain if calc_gain != 0 else 0
                                            avg_cc = cc_adc_map.get(ch, 0)
                                            
                                            self._log(f"    [CH{ch} RP2040 HW Result] PASS -> Avg CC ADC: {avg_cc}, CC Gain: {cc_gain_read:.6f}, Shunt Resistor: {mohm_read:.3f} mOhm")
                                            self._log(self.format_df4000_breakdown(df_b, f"CH{ch} 4. AFTER CURRENT CALIBRATION 0x4000 DF BLOCK"))
                                            
                                            self.emit_result("CC Gain", "CC Gain (mOhm)", f"{mohm_read:.3f}", mohm_read, is_gain=True)
                                            self.emit_result("Capacity Gain", "Capacity Gain (mOhm)", f"{mohm_read:.3f}", mohm_read, is_gain=True)
                            break
                        elif state == 3: # ERROR state from RP2040
                            self._log(f"    [RP2040 HW Result] RP2040 returned ERROR state (err_mask={bin(err_channels)})")
                            break
                    else:
                        self._log(f"    [DEBUG] Poll status response: cmd={st_cmd}, resp={st_resp}")

                # Ensure Relays are turned OFF after Current mode
                if mode_name == "current":
                    self._set_relay(False, mask=0)

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
        import os, csv
        from datetime import datetime
        
        path = config.get_cal_log_path()
        if not path: return
            
        ch_data = self.cal_log_buffer.get(ch, {})
        if not ch_data: return
        
        params = list(ch_data.keys())
        header_row1 = ["Timestamp", "Serial Number", "Manufacture Date"] + params + ["Overall Result"]
        header_row2 = ["", "", ""] + [ch_data[p]['range'] for p in params] + [""]
        data_row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), serial_num, mfg_date] + [ch_data[p]['value'] for p in params] + ["PASS" if overall_success else "FAIL"]
        
        write_header = False
        if not os.path.exists(path):
            write_header = True
        else:
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    reader = list(csv.reader(f))
                    last_ranges = None
                    for row in reversed(reader):
                        if len(row) > 3 and row[0] == "" and row[1] == "":
                            last_ranges = row
                            break
                    if last_ranges != header_row2:
                        write_header = True
            except Exception:
                write_header = True
                
        try:
            with open(path, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if write_header:
                    if os.path.exists(path) and os.path.getsize(path) > 0:
                        writer.writerow([])
                    writer.writerow(header_row1)
                    writer.writerow(header_row2)
                writer.writerow(data_row)
        except Exception as e:
            self._log(f"Failed to write Cal Log: {e}")
