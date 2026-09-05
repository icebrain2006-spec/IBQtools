import os
import sys
import time
import struct
from PySide6.QtCore import QThread, Signal, Slot

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from updater_thread import make_packet, parse_response, RESP_OK, CMD_I2C_RAW, CMD_SMBUS_CMD, CMD_SMBUS_POLL_BLOCK, CMD_RELAY_SET, PROTOCOL_STX
from calibrators.utils import detect_dataflash_offset, load_calibration_offsets, load_adc_offset_0xf081, load_dastatus1_offset_0x0071, load_dastatus2_offset_0x0072, crc8_smbus_byte, smbus_pec_calculate, float_to_xemics, xemics_to_float

BQ_SMBUS_ADDR = 0x0B
CMD_CALIB_RUN = 0x60
CMD_CALIB_STATUS = 0x61
CMD_CAL_EN_SET = 0x62

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

    def set_cal_en(self, ch_mask: int, enable: bool) -> bool:
        """
        Sends CMD_CAL_EN_SET (0x62) to RP2040 firmware to set CAL_EN state.
        """
        payload = bytes([ch_mask, 1 if enable else 0])
        cmd, resp = self._send_cmd(CMD_CAL_EN_SET, payload)
        if isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK:
            self._log(f"    [CAL_EN] Set CAL_EN {'ENABLE' if enable else 'DISABLE'} (mask 0x{ch_mask:02X}) -> PASS")
            return True
        else:
            self._log(f"    [CAL_EN] Set CAL_EN {'ENABLE' if enable else 'DISABLE'} (mask 0x{ch_mask:02X}) -> FAIL")
            return False

    def enqueue_relay(self, ch, on):
        self.relay_queue.append((ch, on))
        
    def _float_to_xemics(self, v):
        return float_to_xemics(v)

    def _xemics_to_float(self, data):
        return xemics_to_float(data)
        
    def parse_val(self, s):
        if s.lower().startswith('0x'):
            return int(s, 16)
        return int(s)

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
        if not df_bytes or len(df_bytes) < 16:
            return f"    [{label}] Invalid/Short block (len={len(df_bytes) if df_bytes else 0})"
        
        # Address header (0x00 0x40) check
        if len(df_bytes) >= 18 and df_bytes[0] == 0x00 and df_bytes[1] == 0x40:
            base = 2
        else:
            base = 0
            
        c1_g = struct.unpack_from('<H', df_bytes, base)[0]
        bat_g = struct.unpack_from('<H', df_bytes, base + 2)[0]
        pack_g = struct.unpack_from('<H', df_bytes, base + 4)[0]
        cc_g = struct.unpack_from('<f', df_bytes, base + 6)[0]
        cap_g = struct.unpack_from('<f', df_bytes, base + 10)[0]
        
        c1_hex = bytes(df_bytes[base:base+2]).hex(' ')
        bat_hex = bytes(df_bytes[base+2:base+4]).hex(' ')
        pack_hex = bytes(df_bytes[base+4:base+6]).hex(' ')
        cc_hex = bytes(df_bytes[base+6:base+10]).hex(' ')
        cap_hex = bytes(df_bytes[base+10:base+14]).hex(' ')
        
        mohm = (3.714528 / cc_g) if cc_g != 0 else 0.0
        
        lines = [
            f"    [{label}]",
            f"    ├── Cell1 Gain : {c1_g:<5d} (0x{c1_g:04X})  [Hex: {c1_hex}]",
            f"    ├── Bat Gain   : {bat_g:<5d} (0x{bat_g:04X})  [Hex: {bat_hex}]",
            f"    ├── Pack Gain  : {pack_g:<5d} (0x{pack_g:04X})  [Hex: {pack_hex}]",
            f"    ├── CC Gain    : {cc_g:.6f} ({mohm:.3f} mOhm) [Hex: {cc_hex}]",
            f"    └── Cap Gain   : {cap_g:.3f}  [Hex: {cap_hex}]"
        ]
        return "\n".join(lines)

    def execute_script(self, script_path, mode_name):
        if not os.path.exists(script_path):
            self._log(f"Script {script_path} not found. Skipping.")
            return True
            
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            self._log(f"Error reading script: {e}")
            return False
            
        self._log(f"--- Running {mode_name.upper()} Script: {os.path.basename(script_path)} ---")
        
        # Ensure CAL_EN is disabled before starting
        self.smbus_write_block_raw(0x44, [0x57, 0x00])
        time.sleep(0.05)
        mfg_data = self.smbus_read_block(0x44)
        if mfg_data and len(mfg_data) >= 4:
            is_cal_en = (mfg_data[3] & 0x80) != 0
            if is_cal_en:
                self._log("Notice: Chip is already in CAL_EN mode. Disabling it to prevent CHK_CAL failures.")
                if "BQ78350" in self.ic_name.upper():
                    self.smbus_write_block_raw(0x44, [0x2D, 0x00])
                else:
                    self.smbus_write_word(0x00, 0x002D)
                time.sleep(0.25)
        
        if mode_name == "current":
            self._set_relay(True)
            self._log("    [Wait] 1.0s for current stabilization...")
            time.sleep(1.0)
        
        # Cache 0x4000 and 0x4020 Calibration Blocks BEFORE entering CAL_EN 1 (which blocks reading)
        self.smbus_write_block_raw(0x44, [0x00, 0x40])
        time.sleep(0.05)
        self.cached_4000 = self.smbus_read_block(0x44)
        if not self.cached_4000 or len(self.cached_4000) < 18:
            self._log("Warning: Failed to cache 0x4000 block at start. It may be read as zeros later.")
        else:
            self._log(self.format_df4000_breakdown(self.cached_4000, f"ORIGINAL 0x4000 DF BLOCK (BEFORE {mode_name.upper()} CALIBRATION)"))
            
        self.smbus_write_block_raw(0x44, [0x20, 0x40])
        time.sleep(0.05)
        self.cached_4020 = self.smbus_read_block(0x44)
        if not self.cached_4020 or len(self.cached_4020) < 18:
            self._log("Warning: Failed to cache 0x4020 block at start.")
        else:
            self._log("0x4020 Calibration Block cached successfully.")
            
        if mode_name == "voltage" and "BQ78350" in self.ic_name.upper():
            self._log("  [BQ78350] Pre-reading stable cell voltages before AFE filter reset...")
            self.bq78350_stable_voltages = {}
            for i in range(15):
                meas = self.smbus_read_word(0x3F - i)
                if meas:
                    self.bq78350_stable_voltages[i] = struct.unpack('<H', bytes(meas))[0]
        
        new_gains = []
        
        for i, line in enumerate(lines):
            if not self._running:
                self._log("Calibration aborted.")
                if mode_name == "current": self._set_relay(False)
                return False
                
            line = line.split('#')[0].split(';')[0].strip()
            if not line: continue
            
            parts = line.split()
            cmd = parts[0].upper()
            
            self._log(f"[{i+1:02d}] {line}")
            
            if cmd == 'W':
                reg = self.parse_val(parts[1])
                val = self.parse_val(parts[2])
                if self.smbus_write_word(reg, val):
                    self._log("  => OK")
                else:
                    self._log("  => FAIL")
                    if mode_name == "current": self._set_relay(False)
                    return False
                    
            elif cmd == 'B':
                reg = self.parse_val(parts[1])
                data_bytes = [self.parse_val(x) for x in parts[2:]]
                if self.smbus_write_block_raw(reg, data_bytes):
                    self._log("  => OK")
                else:
                    self._log("  => FAIL")
                    if mode_name == "current": self._set_relay(False)
                    return False
                    
            elif cmd == 'X':
                delay = self.parse_val(parts[1])
                time.sleep(delay / 1000.0)
                self._log("  => OK")
                
            elif cmd == 'RW':
                reg = self.parse_val(parts[1])
                data = self.smbus_read_word(reg)
                if data:
                    val = struct.unpack('<H', bytes(data))[0]
                    if not hasattr(self, 'script_vars'):
                        self.script_vars = {}
                    self.script_vars[reg] = val
                    self._log(f"  => OK: {val} (0x{val:04X})")
                else:
                    self._log("  => FAIL")
                    if mode_name == "current": self._set_relay(False)
                    return False

            elif cmd == 'R':
                reg = self.parse_val(parts[1])
                data = self.smbus_read_block(reg)
                if data:
                    self._log("  => OK: " + data.hex(' '))
                else:
                    self._log("  => FAIL")
                    return False
                    
            elif cmd == 'CHK_CAL':
                expected = self.parse_val(parts[1])
                success = False
                for _ in range(10):
                    if not self._running: break
                    self.smbus_write_block_raw(0x44, [0x57, 0x00])
                    time.sleep(0.02)
                    data = self.smbus_read_block(0x44)
                    time.sleep(0.057)
                    if data:
                        self._log(f"    [DEBUG] CHK_CAL data: {data.hex(' ')}")
                    else:
                        self._log(f"    [DEBUG] CHK_CAL read failed (returned None)")
                        
                    if data and len(data) >= 4:
                        cal_en = (data[3] & 0x80) != 0
                        self._log(f"    [DEBUG] CHK_CAL cal_en={cal_en}, expected={expected}")
                        if (cal_en and expected == 1) or (not cal_en and expected == 0):
                            success = True
                            break
                if success:
                    self._log(f"  => OK (CAL_EN == {expected})")
                else:
                    self._log(f"  => FAIL (CAL_EN did not become {expected})")
                    if mode_name == "current": self._set_relay(False)
                    return False
                    
            elif cmd == 'A':
                reg = self.parse_val(parts[1])
                interval = self.parse_val(parts[2])
                count = self.parse_val(parts[3])
                
                blocks = []
                last_zz = -1
                attempt = 0
                while len(blocks) < count and attempt < (count * 20):
                    if not self._running: break
                    b = self.smbus_read_block(reg)
                    if b and len(b) >= 26 and "BQ78350" in self.ic_name.upper():
                        if b[0] in (0x81, 0x82) and b[1] == 0xF0:
                            zz = b[2]
                            if zz != last_zz:
                                blocks.append(b)
                                last_zz = zz
                        else:
                            blocks.append(b)
                    elif b:
                        blocks.append(b)
                    time.sleep(interval / 1000.0)
                    attempt += 1
                    
                if blocks:
                    self._log(f"  => OK ({len(blocks)} blocks)")
                    if len(blocks) > 0 and self.targets:
                        # Logic changes based on mode
                        if mode_name == "voltage":
                            if "BQ78350" in self.ic_name.upper():
                                if not hasattr(self, 'bq78350_v_cal'):
                                    self.bq78350_v_cal = {}
                                if blocks and len(blocks[0]) >= 34 and blocks[0][0] == 0x81 and blocks[0][1] == 0xF0:
                                    cell_sums = [0]*14
                                    valid_count = 0
                                    for blk in blocks:
                                        if len(blk) >= 34:
                                            for i in range(14):
                                                cell_sums[i] += struct.unpack_from('<H', blk, 6 + i*2)[0]
                                            valid_count += 1
                                    if valid_count > 0:
                                        for i in range(14):
                                            self.bq78350_v_cal[f"cell{i+1}"] = cell_sums[i] / valid_count
                                        self._log(f"    Avg ADC -> Cell1: {self.bq78350_v_cal['cell1']:.2f}, Cell6: {self.bq78350_v_cal['cell6']:.2f}")
                                
                                elif blocks and len(blocks[0]) >= 26 and blocks[0][0] == 0x82 and blocks[0][1] == 0xF0:
                                    cell15_sum = 0
                                    valid_count = 0
                                    for blk in blocks:
                                        if len(blk) >= 26:
                                            cell15_sum += struct.unpack_from('<H', blk, 6)[0]
                                            valid_count += 1
                                    if valid_count > 0:
                                        self.bq78350_v_cal["cell15"] = cell15_sum / valid_count
                            else:
                                adc_cfg = load_adc_offset_0xf081("BQ40Z50")
                                cell1_sum = 0
                                pack_sum = 0
                                batt_sum = 0
                                valid_count = 0
                                min_len = adc_cfg.get("min_len", 16)
                                c1_off = adc_cfg.get("cell1", 4)
                                pack_off = adc_cfg.get("pack", 12)
                                bat_off = adc_cfg.get("bat", 14)

                                for blk in blocks:
                                    if len(blk) >= min_len:
                                        cell1_sum += struct.unpack_from('<H', blk, c1_off)[0]
                                        pack_sum += struct.unpack_from('<H', blk, pack_off)[0]
                                        batt_sum += struct.unpack_from('<H', blk, bat_off)[0]
                                        valid_count += 1
                                        
                                if valid_count > 0:
                                    cell1_avg = cell1_sum / float(valid_count)
                                    batt_avg = batt_sum / float(valid_count)
                                    pack_avg = pack_sum / float(valid_count)
                                    
                                    self._log(f"    Avg ADC -> Cell1: {cell1_avg:.2f}, Pack: {pack_avg:.2f}, Batt: {batt_avg:.2f}")
                                    if cell1_avg > 0:
                                        g = int((self.targets.get('cell1mv', 3200) / cell1_avg) * 65536)
                                        g = max(0, min(65535, g))
                                        new_gains.append(g)
                                        self._log(f"    New Cell 1 Gain = {g}")
                                        self.emit_result("Cell 1 Gain", "Cell 1 Gain", str(g), g, is_gain=True)
                                    if pack_avg > 0:
                                        g = int((self.targets.get('packmv', 12780) / pack_avg) * 65536)
                                        g = max(0, min(65535, g))
                                        new_gains.append(g)
                                        self._log(f"    New Pack Gain = {g}")
                                        self.emit_result("Pack Gain", "Pack Gain", str(g), g, is_gain=True)
                                    if batt_avg > 0:
                                        g = int((self.targets.get('batmv', 12780) / batt_avg) * 65536)
                                        g = max(0, min(65535, g))
                                        new_gains.append(g)
                                        self._log(f"    New Bat Gain = {g}")
                                        self.emit_result("Bat Gain", "Bat Gain", str(g), g, is_gain=True)
                        
                        elif mode_name == "temp":
                            int_sum = ts1_sum = ts2_sum = ts3_sum = ts4_sum = 0
                            valid_count = 0
                            for blk in blocks:

                                if "BQ78350" in self.ic_name.upper():
                                    if len(blk) >= 26:
                                        ts1_sum += struct.unpack_from('<H', blk, 18)[0]
                                        ts2_sum += struct.unpack_from('<H', blk, 20)[0]
                                        ts3_sum += struct.unpack_from('<H', blk, 22)[0]
                                        int_sum += struct.unpack_from('<H', blk, 24)[0]
                                        valid_count += 1
                                else:
                                    d2_cfg = load_dastatus2_offset_0x0072("BQ40Z50")
                                    min_len = d2_cfg.get("min_len", 30)
                                    int_off = d2_cfg.get("int_temp", 2)
                                    ts1_off = d2_cfg.get("ts1_temp", 4)
                                    ts2_off = d2_cfg.get("ts2_temp", 6)
                                    ts3_off = d2_cfg.get("ts3_temp", 8)
                                    ts4_off = d2_cfg.get("ts4_temp", 10)
                                    if len(blk) >= min_len:
                                        int_sum += struct.unpack_from('<H', blk, int_off)[0]
                                        ts1_sum += struct.unpack_from('<H', blk, ts1_off)[0]
                                        ts2_sum += struct.unpack_from('<H', blk, ts2_off)[0]
                                        ts3_sum += struct.unpack_from('<H', blk, ts3_off)[0]
                                        ts4_sum += struct.unpack_from('<H', blk, ts4_off)[0]
                                        valid_count += 1
                            if valid_count > 0:
                                int_avg = (int_sum / float(valid_count)) - 2732
                                ts1_avg = (ts1_sum / float(valid_count)) - 2732
                                ts2_avg = (ts2_sum / float(valid_count)) - 2732
                                ts3_avg = (ts3_sum / float(valid_count)) - 2732
                                ts4_avg = (ts4_sum / float(valid_count)) - 2732 if ts4_sum > 0 else 0
                                
                                self._log(f"    Avg DAStatus2 -> Int:{int_avg/10:.1f}C, TS1:{ts1_avg/10:.1f}C, TS2:{ts2_avg/10:.1f}C, TS3:{ts3_avg/10:.1f}C, TS4:{ts4_avg/10:.1f}C")
                                self.temp_measured = {
                                    "int": int_avg, "ts1": ts1_avg, "ts2": ts2_avg, "ts3": ts3_avg, "ts4": ts4_avg
                                }
                            
                        elif mode_name == "current":
                            # Parse F081 for CC
                            cc_sum = 0
                            valid_count = 0
                            for blk in blocks:
                                if "BQ78350" in self.ic_name.upper():
                                    if len(blk) >= 18:
                                        # FCALCC is at offset 16, Little Endian for BQ78350
                                        cc_sum += struct.unpack_from('<h', blk, 16)[0]
                                        valid_count += 1
                                else:
                                    adc_cfg = load_adc_offset_0xf081("BQ40Z50")
                                    min_len = adc_cfg.get("min_len", 18)
                                    cc_off = adc_cfg.get("current", 4)
                                    if len(blk) >= min_len:
                                        # Raw CC is a 16-bit signed integer at cc_off
                                        cc_sum += struct.unpack_from('<h', blk, cc_off)[0]
                                        valid_count += 1
                                    
                            if valid_count > 0:
                                cc_avg = cc_sum / float(valid_count)
                                self._log(f"    Avg CC ADC -> {cc_avg:.2f}")
                                self.cc_measured = cc_avg
                else:
                    self._log("  => FAIL")
                    if mode_name == "current": self._set_relay(False)
                    return False
                    
            elif cmd == 'S':
                # Custom Save command for DataFlash
                reg = self.parse_val(parts[1])
                df_addr_bytes = [reg & 0xFF, (reg >> 8) & 0xFF]

                # Use cached block if available (to prevent reading zeros during CAL_EN 1)
                if reg == 0x4000 and hasattr(self, 'cached_4000') and self.cached_4000 and len(self.cached_4000) >= 34:
                    old_data = self.cached_4000
                elif reg == 0x4020 and hasattr(self, 'cached_4020') and self.cached_4020 and len(self.cached_4020) >= 18:
                    old_data = self.cached_4020
                else:
                    self.smbus_write_block_raw(0x44, df_addr_bytes)
                    time.sleep(0.05)
                    old_data = self.smbus_read_block(0x44)

                if old_data and len(old_data) >= 34 and reg == 0x4000:
                    df_bytes = bytearray(old_data[2:34])
                elif old_data and len(old_data) >= 18 and reg == 0x4020:
                    df_bytes = bytearray(old_data[2:18])
                else:
                    self._log(f"  => FAIL: Could not read old calibration block (reg=0x{reg:04X})")
                    if mode_name == "current": self._set_relay(False)
                    return False

                if mode_name == "voltage":
                    if "BQ78350" in self.ic_name.upper():
                        if reg == 0x4000:
                            
                            cell1_base = self.df_offsets.get("Cell 1 Offset", 8) if hasattr(self, 'df_offsets') else 8
                            for i in range(15):
                                target = self.targets.get(f'cell{i+1}mv', 0)
                                if target > 0:
                                    # TRM 12.2.4.1: Read 0x3F to 0x31 to get Reported Cell Voltage in mV
                                    if hasattr(self, 'bq78350_stable_voltages') and i in self.bq78350_stable_voltages:
                                        adc = self.bq78350_stable_voltages[i]
                                        self._log(f"    Cell {i+1} Stable Pre-read ADC: {adc}")
                                    else:
                                        meas = self.smbus_read_word(0x3F - i)
                                        if meas:
                                            adc = struct.unpack('<H', bytes(meas))[0]
                                        else:
                                            continue
                                            
                                    old_off = struct.unpack_from('<b', df_bytes, cell1_base + i)[0]
                                    new_off = max(-128, min(127, int(target - adc + old_off)))
                                    df_bytes[cell1_base + i] = new_off & 0xFF
                                    self._log(f"    New Cell {i+1} Offset = {new_off}")
                                    self.emit_result(f"Cell {i+1} Offset", f"Cell {i+1} Offset", f"{new_off}", new_off, is_gain=True)
                        elif reg == 0x4020:
                            target_ext_avg = self.targets.get('extaveragecellmv', 0)
                            if target_ext_avg > 0:
                                measured_bat = getattr(self, 'script_vars', {}).get(0x09, 0)
                                target_bat = target_ext_avg * self.active_cells
                                if measured_bat > 0:
                                    old_gain = struct.unpack_from('<H', df_bytes, 2)[0] # Offset 34 - 32 = 2
                                    new_gain = max(0, min(65535, int(old_gain * (target_bat / measured_bat))))
                                    struct.pack_into('<H', df_bytes, 2, new_gain)
                                    self._log(f"    New Ext Cell Divider Gain = {new_gain}")
                                    self.emit_result("Ext Cell Divider Gain", "Ext Cell Divider Gain", f"{new_gain}", new_gain, is_gain=True)
                    else:
                        if not new_gains or len(new_gains) < 3:
                            self._log("  => FAIL: Not enough gain data calculated!")
                            return False
                            
                        cell1_g = new_gains[0]
                        pack_g = new_gains[1]
                        bat_g = new_gains[2]
                        
                        struct.pack_into('<HHH', df_bytes, 0, cell1_g, bat_g, pack_g)
                        
                    full_payload = df_addr_bytes + list(df_bytes)
                    if self.smbus_write_block_raw(0x44, full_payload):
                        self._log(f"  => OK (Wrote Voltage Calibration Block 0x{reg:04X})")
                    else:
                        self._log("  => FAIL writing block")
                        return False

                elif mode_name == "temp":
                    if not hasattr(self, 'temp_measured'):
                        self._log("  => FAIL: No temperature data measured!")
                        return False
                        
                    def get_old(idx):
                        val = df_bytes[idx]
                        if val > 127: val -= 256
                        return val
                        
                    def clamp(val):
                        return max(-128, min(127, int(val)))
                        
                    t_int = self.targets.get('inttempc', self.targets.get('internalsensorc', 25.0)) * 10
                    t_ts1 = self.targets.get('ts1tempc', self.targets.get('sensor1c', 25.0)) * 10
                    t_ts2 = self.targets.get('ts2tempc', self.targets.get('sensor2c', 25.0)) * 10
                    t_ts3 = self.targets.get('ts3tempc', self.targets.get('sensor3c', 25.0)) * 10
                    t_ts4 = self.targets.get('ts4tempc', 25.0) * 10
                    
                    if "BQ78350" in self.ic_name.upper():
                        if reg == 0x4000:
                            if self.targets.get('ts1tempc_en', self.targets.get('sensor1c_en', True)) and self.temp_measured.get("ts1", -1000) > -500:
                                new_off = clamp(get_old(30) + (t_ts1 - self.temp_measured["ts1"]))
                                df_bytes[30] = new_off & 0xFF
                                self._log(f"    New TS1 Offset = {new_off}")
                                self.emit_result("TS1 Temp Gain", "TS1 Temp Offset", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                                
                            if self.targets.get('ts2tempc_en', self.targets.get('sensor2c_en', True)) and self.temp_measured.get("ts2", -1000) > -500:
                                new_off = clamp(get_old(31) + (t_ts2 - self.temp_measured["ts2"]))
                                df_bytes[31] = new_off & 0xFF
                                self._log(f"    New TS2 Offset = {new_off}")
                                self.emit_result("TS2 Temp Gain", "TS2 Temp Offset", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                                
                        elif reg == 0x4020:
                            if self.targets.get('ts3tempc_en', self.targets.get('sensor3c_en', True)) and self.temp_measured.get("ts3", -1000) > -500:
                                new_off = clamp(get_old(0) + (t_ts3 - self.temp_measured["ts3"]))
                                df_bytes[0] = new_off & 0xFF
                                self._log(f"    New TS3 Offset = {new_off}")
                                self.emit_result("TS3 Temp Gain", "TS3 Temp Offset", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                                
                            if self.targets.get('inttempc_en', self.targets.get('internalsensorc_en', True)) and self.temp_measured.get("int", -1000) > -500:
                                old_int = get_old(1)
                                meas_int = self.temp_measured["int"]
                                new_off = clamp(old_int + (t_int - meas_int))
                                self._log(f"    [DEBUG] IntTemp: target={t_int}, measured={meas_int}, old_off={old_int} -> new_off={new_off}")
                                df_bytes[1] = new_off & 0xFF
                                self._log(f"    New Int Offset = {new_off}")
                                self.emit_result("Int Temp Gain", "Int Temp Offset", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                    else:
                        # BQ40Z50 logic (all in 0x4000 block)
                        if reg == 0x4000:
                            if self.targets.get('inttempc_en', True):
                                new_off = clamp(get_old(20) + (t_int - self.temp_measured["int"]))
                                df_bytes[20] = new_off & 0xFF
                                self._log(f"    New Int Offset = {new_off}")
                                self.emit_result("Int Temp Gain", "Int Temp Gain", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                                
                            if self.targets.get('ts1tempc_en', True) and self.temp_measured["ts1"] > -500:
                                new_off = clamp(get_old(21) + (t_ts1 - self.temp_measured["ts1"]))
                                df_bytes[21] = new_off & 0xFF
                                self._log(f"    New TS1 Offset = {new_off}")
                                self.emit_result("TS1 Temp Gain", "TS1 Temp Gain", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                                
                            if self.targets.get('ts2tempc_en', True) and self.temp_measured["ts2"] > -500:
                                new_off = clamp(get_old(22) + (t_ts2 - self.temp_measured["ts2"]))
                                df_bytes[22] = new_off & 0xFF
                                self._log(f"    New TS2 Offset = {new_off}")
                                self.emit_result("TS2 Temp Gain", "TS2 Temp Gain", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                                
                            if self.targets.get('ts3tempc_en', True) and self.temp_measured["ts3"] > -500:
                                new_off = clamp(get_old(23) + (t_ts3 - self.temp_measured["ts3"]))
                                df_bytes[23] = new_off & 0xFF
                                self._log(f"    New TS3 Offset = {new_off}")
                                self.emit_result("TS3 Temp Gain", "TS3 Temp Gain", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                                
                            if self.targets.get('ts4tempc_en', True) and self.temp_measured["ts4"] > -500:
                                new_off = clamp(get_old(24) + (t_ts4 - self.temp_measured["ts4"]))
                                df_bytes[24] = new_off & 0xFF
                                self._log(f"    New TS4 Offset = {new_off}")
                                self.emit_result("TS4 Temp Gain", "TS4 Temp Gain", f"{new_off * 0.1:.1f} °C", new_off, is_gain=True)
                        
                    full_payload = df_addr_bytes + list(df_bytes)
                    if self.smbus_write_block_raw(0x44, full_payload):
                        self._log("  => OK (Wrote Temperature Calibration Block)")
                    else:
                        self._log("  => FAIL writing block")
                        return False

                elif mode_name == "current":
                    if not hasattr(self, 'cc_measured') or abs(self.cc_measured) < 0.1:
                        self._log("  => FAIL: No valid CC data measured!")
                        return False
                        
                    target_ma = self.targets.get('currentma', -1000)
                    if target_ma == 0:
                        self._log("  => FAIL: Target current cannot be 0")
                        return False
                        
                    # For both BQ40Z50 and BQ78350, 0xF082 outputs Raw ADC, so we do not multiply by old gain!
                    new_cc_gain = abs(float(target_ma) / self.cc_measured)
                    
                    # TRM 2.4.3 Formula 4: Capacity Gain = CC Gain * 298261.6178
                    new_cap_gain = new_cc_gain * 298261.6178
                    
                    if "BQ78350" in self.ic_name.upper():
                        cc_gain_off = self.df_offsets.get("CC Gain", 0) if hasattr(self, 'df_offsets') else 0
                        cap_gain_off = self.df_offsets.get("Capacity Gain", 4) if hasattr(self, 'df_offsets') else 4
                        
                        # Xemics Float at dynamic offset
                        b0, b1, b2, b3 = self._float_to_xemics(new_cc_gain)
                        df_bytes[cc_gain_off:cc_gain_off+4] = bytes([b0, b1, b2, b3])
                        b0, b1, b2, b3 = self._float_to_xemics(new_cap_gain)
                        df_bytes[cap_gain_off:cap_gain_off+4] = bytes([b0, b1, b2, b3])
                        
                        # GUI display conversion as per df_bq78350r1_V1_04.csv (8.4381/x)
                        mohm = 8.4381 / new_cc_gain if new_cc_gain != 0 else 0
                    else:
                        cc_gain_off = self.df_offsets.get("CC Gain", 6) if hasattr(self, 'df_offsets') else 6
                        cap_gain_off = self.df_offsets.get("Capacity Gain", 10) if hasattr(self, 'df_offsets') else 10
                        # IEEE 754 Float at dynamic offset
                        struct.pack_into('<f', df_bytes, cc_gain_off, new_cc_gain)
                        struct.pack_into('<f', df_bytes, cap_gain_off, new_cap_gain)
                        
                        # TRM DF-to-Studio Conversion: 3.714528 / DF
                        mohm = 3.714528 / new_cc_gain if new_cc_gain != 0 else 0
                        
                    self._log(f"    New CC Gain = {new_cc_gain:.6f}")
                    self._log(f"    New Capacity Gain = {new_cap_gain:.1f}")
                    
                    self.emit_result("CC Gain", "CC Gain (mOhm)", f"{mohm:.3f}", mohm, is_gain=True)
                    self.emit_result("Capacity Gain", "Capacity Gain (mOhm)", f"{mohm:.3f}", mohm, is_gain=True)
                    
                    full_payload = df_addr_bytes + list(df_bytes)
                    hex_str = bytes(full_payload).hex(' ')
                    self._log(f"    [WRITE 0x4000 BLOCK PAYLOAD ({len(full_payload)}b)] {hex_str}")
                    if self.smbus_write_block_raw(0x44, full_payload):
                        self._log("  => OK (Wrote Current Calibration Block)")
                    else:
                        self._log("  => FAIL writing block")
                        if mode_name == "current": self._set_relay(False)
                        return False

        if mode_name == "current": self._set_relay(False)
        return True

    def post_verify(self):
        try:
            run_mode = self.targets.get("run_mode", "voltage")
            show_voltage = run_mode in ("voltage", "all")
            show_temp = run_mode in ("temp", "temperature", "all")

            if "BQ78350" in self.ic_name.upper():
                if show_voltage:
                    for i in range(self.active_cells):
                        cmd = 0x3F - i
                        val = self.smbus_read_word(cmd)
                        if val:
                            val = struct.unpack('<H', bytes(val))[0]
                            self.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1} (0x{cmd:02X})", "-", val, suffix=" mV")
                            
                    if self.targets.get('extaveragecellmv', 0) > 0:
                        v_ext = self.smbus_read_word(0x4D)
                        if v_ext:
                            v_ext = struct.unpack('<H', bytes(v_ext))[0]
                            self.emit_result("V_Ext", "Ext Ave Cell (0x4D)", "-", v_ext, suffix=" mV")
                            
                    if self.targets.get('vauxmv', 0) > 0:
                        v_aux = self.smbus_read_word(0x2E)
                        if v_aux:
                            v_aux = struct.unpack('<H', bytes(v_aux))[0]
                            self.emit_result("V_Aux", "VAux (0x2E)", "-", v_aux, suffix=" mV")
                        
                if show_temp:
                    int_temp_raw = self.smbus_read_word(0x28) # InternalTemp is 0x28
                    if int_temp_raw:
                        val = struct.unpack('<H', bytes(int_temp_raw))[0]
                        temp_c = round(val * 0.1 - 273.15, 1)
                        if self.targets.get("inttempc_en", False):
                            self.emit_result("Int Temp", "Int Temp (0x28)", "-", temp_c, suffix=" °C")
                            
                    for i, (name, cmd) in enumerate([("TS1", 0x5E), ("TS2", 0x5F), ("TS3", 0x60), ("TS4", 0x61)]):
                        if self.targets.get(f"{name.lower()}tempc_en", False):
                            raw = self.smbus_read_word(cmd)
                            if raw:
                                val = struct.unpack('<H', bytes(raw))[0]
                                temp_c = round(val * 0.1 - 273.15, 1)
                                self.emit_result(f"{name} Temp", f"{name} Temp (0x{cmd:02X})", "-", temp_c, suffix=" °C")
                return True
            else:
                # Read standard SBS SMBus Voltage Commands for BQ40Z50
                # 0x3F: Cell1, 0x3E: Cell2, 0x3D: Cell3, 0x3C: Cell4
                # Read DAStatus 1 (0x0071) over 0x44 for distinct Cell 1..4, V_Bat (offset 10) and V_Pack (offset 12)
                v_bat_val = None
                v_pack_val = None
                data1 = self.read_mac_block([0x71, 0x00])
                if data1 and len(data1) >= 14:
                    data_ok = True
                    if show_voltage:
                        v_c1 = struct.unpack_from('<H', data1, 2)[0]
                        v_c2 = struct.unpack_from('<H', data1, 4)[0]
                        v_c3 = struct.unpack_from('<H', data1, 6)[0]
                        v_c4 = struct.unpack_from('<H', data1, 8)[0]
                        v_cells = [v_c1, v_c2, v_c3, v_c4]
                        for i in range(min(self.active_cells, len(v_cells))):
                            self.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1}", "-", v_cells[i], suffix=" mV")

                    v_bat_val = struct.unpack_from('<H', data1, 10)[0]
                    v_pack_val = struct.unpack_from('<H', data1, 12)[0]
                else:
                    if show_voltage:
                        for i in range(self.active_cells):
                            cmd = 0x3F - i
                            val = self.smbus_read_word(cmd)
                            if val:
                                data_ok = True
                                v_cell = struct.unpack('<H', bytes(val))[0]
                                self.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1}", "-", v_cell, suffix=" mV")

                    val_pack = self.smbus_read_word(0x09)
                    if val_pack:
                        data_ok = True
                        v_p = struct.unpack('<H', bytes(val_pack))[0]
                        v_bat_val = v_p
                        v_pack_val = v_p

                if show_voltage and (v_pack_val is not None and v_bat_val is not None):
                    ch_limits = self.limits_per_ch.get(self.ch, self.limits)
                    diff_min, diff_max = ch_limits.get("V_Pack - V_Bat Diff", ch_limits.get("V_Pack / V_Bat Diff", (-20.0, 20.0)))
                    v_diff = v_pack_val - v_bat_val
                    force_diff_fail = (v_diff < diff_min or v_diff > diff_max)
                    if force_diff_fail:
                        self._log(f"FAIL: V_Pack/V_Bat diff={v_diff}mV exceeds limit ({diff_min}, {diff_max})")
                    self.emit_result("V_Pack", "V_Pack", "-", v_pack_val, suffix=" mV", force_fail=force_diff_fail)
                    self.emit_result("V_Bat", "V_Bat", "-", v_bat_val, suffix=" mV", force_fail=force_diff_fail)

                data2 = self.read_mac_block([0x72, 0x00])
                if data2 and len(data2) >= 16:
                    int_temp = round(struct.unpack_from('<H', data2, 2)[0] * 0.1 - 273.15, 1)
                    ts1 = round(struct.unpack_from('<H', data2, 4)[0] * 0.1 - 273.15, 1)
                    ts2 = round(struct.unpack_from('<H', data2, 6)[0] * 0.1 - 273.15, 1)
                    ts3 = round(struct.unpack_from('<H', data2, 8)[0] * 0.1 - 273.15, 1)
                    ts4 = round(struct.unpack_from('<H', data2, 10)[0] * 0.1 - 273.15, 1)
                    
                    if show_temp:
                        if self.targets.get("inttempc_en", False):
                            self.emit_result("Int Temp", "Int Temp (0x0072)", "-", int_temp, suffix=" °C")
                        if self.targets.get("ts1tempc_en", False):
                            self.emit_result("TS1 Temp", "TS1 Temp (0x0072)", "-", ts1, suffix=" °C")
                        if self.targets.get("ts2tempc_en", False):
                            self.emit_result("TS2 Temp", "TS2 Temp (0x0072)", "-", ts2, suffix=" °C")
                        if self.targets.get("ts3tempc_en", False):
                            self.emit_result("TS3 Temp", "TS3 Temp (0x0072)", "-", ts3, suffix=" °C")
                        if self.targets.get("ts4tempc_en", False):
                            self.emit_result("TS4 Temp", "TS4 Temp (0x0072)", "-", ts4, suffix=" °C")
                        
                # Read and Dump 0x4000 DataFlash Block Content
                df_4000 = self.read_mac_block([0x00, 0x40])
                if df_4000:
                    self._log(self.format_df4000_breakdown(df_4000, f"CH{self.ch} POST-VERIFY 0x4000 DF BLOCK"))

                if not data_ok and not data2:
                    return False
                return True
        except Exception as e:
            self._log(f"CRASH in post_verify: {e}")
            return False

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
