import os
import sys
import time
import struct
from PySide6.QtCore import QThread, Signal, Slot

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from updater_thread import make_packet, parse_response, RESP_OK, CMD_I2C_RAW, CMD_SMBUS_CMD, CMD_SMBUS_POLL_BLOCK, CMD_RELAY_SET, PROTOCOL_STX
from calibrators.utils import detect_dataflash_offset, load_calibration_offsets

def crc8_smbus_byte(crc, data):
    crc ^= data
    for _ in range(8):
        if crc & 0x80:
            crc = (crc << 1) ^ 0x07
        else:
            crc = (crc << 1)
        crc &= 0xFF
    return crc

def smbus_pec_calculate(data_bytes):
    crc = 0
    for b in data_bytes:
        crc = crc8_smbus_byte(crc, b)
    return crc

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
        self.addr = 0x0B
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
        
            
    @Slot(dict)
    def on_limits_updated(self, new_limits):
        self.limits = new_limits
        self._log(f"DEBUG THREAD: Received new limits via signal: V_Cell 2={self.limits.get('V_Cell 2')}")
        
    def emit_result(self, param_key, param_name, raw_adc, val, is_gain=False, suffix=""):
        raw_status = "PASS" if is_gain else "INFO"
        ch_limits = self.limits_per_ch.get(self.ch, self.limits)
        if param_key in ch_limits:
            min_val, max_val = ch_limits[param_key]
            if min_val <= val <= max_val:
                raw_status = "PASS"
            else:
                raw_status = "FAIL"
                
        if is_gain:
            if raw_status == "FAIL":
                self._log(f"FAIL: {param_key} val={val} limits=({min_val}, {max_val})")
            # For gain rows, show the calculated gain value
            self.row_signal.emit(param_name, self.ch, str(raw_adc), raw_status)
        else:
            # Apply 5-history sliding window for Voltage/Temp monitoring
            if param_name not in self.history:
                self.history[param_name] = {}
            if self.ch not in self.history[param_name]:
                self.history[param_name][self.ch] = []
                
            ch_hist = self.history[param_name][self.ch]
            ch_hist.append(raw_status)
            if len(ch_hist) > 5:
                ch_hist.pop(0)
                
            # Final status is FAIL if ANY of the last 5 measurements failed (except for BQ78350 V_Cell)
            if "BQ78350" in self.ic_name.upper() and param_key.startswith("V_Cell"):
                pass_count = ch_hist.count("PASS")
                fail_count = ch_hist.count("FAIL")
                if len(ch_hist) >= 3:
                    if pass_count >= 3:
                        final_status = "PASS"
                    elif fail_count >= 3:
                        final_status = "FAIL"
                    else:
                        final_status = "PASS" if pass_count >= fail_count else "FAIL"
                else:
                    final_status = raw_status
            else:
                final_status = "FAIL" if "FAIL" in ch_hist else raw_status
            
            if raw_status == "FAIL":
                if final_status == "PASS":
                    self._log(f"    (Filtered Noise) {param_key} val={val} limits=({min_val}, {max_val}) - Ignored due to majority PASS")
                else:
                    self._log(f"FAIL: {param_key} val={val} limits=({min_val}, {max_val})")
                    
            # For validation rows, show the measured voltage/temp/current
            self.row_signal.emit(param_name, self.ch, f"{val}{suffix}", final_status)
            
        if self.ch not in self.cal_log_buffer:
            self.cal_log_buffer[self.ch] = {}
        min_v, max_v = self.limits.get(param_key, (None, None))
        range_str = f"{min_v}{suffix} - {max_v}{suffix}" if min_v is not None and max_v is not None else "0 - 65535"
        if is_gain: range_str = "0 - 65535"
        
        # The stored value should be raw_adc (if it's a gain row) or val (if it's a measurement)
        stored_val = raw_adc if is_gain else val
        self.cal_log_buffer[self.ch][param_key] = {
            'value': f"{stored_val}{suffix}",
            'range': range_str
        }
            
    def stop(self):
        self._running = False
        
    def _set_relay(self, on: bool):
        mask = (1 << (self.ch - 1)) if on else 0
        payload = bytes([mask])
        packet = make_packet(CMD_RELAY_SET, payload)
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        # MUST read response to avoid UART buffer desync for subsequent commands!
        rx = self._read_packet() 
        self._log(f"    [Relay] {'ON' if on else 'OFF'} for CH{self.ch} (mask: 0x{mask:02X})")
        time.sleep(0.1) # Command process delay
        
    def _log(self, msg):
        self.log_signal.emit(f"[CH{self.ch}] {msg}")

    def enqueue_relay(self, ch, on):
        self.relay_queue.append((ch, on))
        
    def _float_to_xemics(self, v):
        import math
        if v == 0.0: return [0, 0, 0, 0]
        exp = int(math.floor(math.log(abs(v), 2))) + 1
        mant = int((abs(v) / (2**exp)) * (2**24))
        exp += 128
        b0 = exp
        b1 = (mant >> 16) & 0x7F
        if v < 0: b1 |= 0x80
        b2 = (mant >> 8) & 0xFF
        b3 = mant & 0xFF
        return [b0, b1, b2, b3]

    def _xemics_to_float(self, data):
        if not data or len(data) < 4: return 0.0
        b0, b1, b2, b3 = data[0], data[1], data[2], data[3]
        if b0 == 0 and b1 == 0 and b2 == 0 and b3 == 0: return 0.0
        exp = b0 - 128
        mant = (((b1 & 0x7F) | 0x80) << 16) | (b2 << 8) | b3
        v = (mant / (2**24)) * (2**exp)
        if b1 & 0x80: v = -v
        return v
        
    def parse_val(self, s):
        if s.lower().startswith('0x'):
            return int(s, 16)
        return int(s)

    def smbus_write_word(self, reg, val):
        payload = struct.pack('<BBBBBBH', self.ch, self.addr, reg, 0, 2, 0, val)
        tx_pkt = make_packet(CMD_SMBUS_CMD, payload)
        self.ser.write(tx_pkt)
        rx = self._read_packet()
        self._log(f"    [RAW IO] TX({len(tx_pkt)}b): {tx_pkt.hex(' ')} | RX({len(rx)}b): {rx.hex(' ')}")
        cmd, resp = parse_response(rx)
        return isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK
        
    def smbus_write_block_raw(self, cmd_reg, data_bytes, use_pec=True):
        tx_data = bytearray([cmd_reg, len(data_bytes)]) + bytearray(data_bytes)
        if use_pec:
            pec_data = bytearray([(self.addr << 1)]) + tx_data
            pec = smbus_pec_calculate(pec_data)
            tx_data.append(pec)
            
        payload = bytes([self.ch, self.addr, len(tx_data), 0]) + tx_data
        tx_pkt = make_packet(CMD_I2C_RAW, payload)
        self.ser.write(tx_pkt)
        rx = self._read_packet()
        self._log(f"    [RAW IO] TX({len(tx_pkt)}b): {tx_pkt.hex(' ')} | RX({len(rx)}b): {rx.hex(' ')}")
        cmd, resp = parse_response(rx)
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
                    buf = buf.replace(b'\r\n', b'\n')
                
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
        tx_pkt = make_packet(CMD_SMBUS_CMD, payload)
        self.ser.reset_input_buffer()
        self.ser.write(tx_pkt)
        rx = self._read_packet()
        self._log(f"    [RAW IO] TX({len(tx_pkt)}b): {tx_pkt.hex(' ')} | RX({len(rx)}b): {rx.hex(' ')}")
        cmd, resp = parse_response(rx)
        if isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK:
            return resp[1:3]
        return None

    def smbus_read_block(self, cmd_reg):
        resp = None
        for attempt in range(10):
            if not self._running: return None
            payload = bytes([self.ch, self.addr, cmd_reg, 1, 32, 0, 0])
            tx_pkt = make_packet(CMD_SMBUS_CMD, payload)
            self.ser.reset_input_buffer()
            self.ser.write(tx_pkt)
            rx = self._read_packet()
            self._log(f"    [RAW IO] Attempt {attempt+1} TX({len(tx_pkt)}b): {tx_pkt.hex(' ')} | RX({len(rx)}b): {rx.hex(' ')}")
            cmd, resp = parse_response(rx)
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
        tx_pkt = make_packet(CMD_I2C_RAW, payload)
        self.ser.reset_input_buffer()
        self.ser.write(tx_pkt)
        self._read_packet()
        time.sleep(0.01)

    def _read_mfg_info(self):
        import struct
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

    def detect_firmware_and_config(self):
        # 1. Read MAC 0x0002
        self.smbus_write_block_raw(0x44, [0x02, 0x00])
        time.sleep(0.05)
        data = self.smbus_read_block(0x44)
        
        if not data:
            self._log("Failed to detect firmware version (0x0002).")
            return False
            
        self._log(f"MAC 0x0002 Raw Read: {data.hex(' ')}")
        
        # Find the echo of 0x02 0x00
        idx = -1
        for i in range(len(data) - 1):
            if data[i] == 0x02 and data[i+1] == 0x00:
                idx = i
                break
                
        if idx == -1 or idx + 5 < len(data):
            # Fallback to index 0 if echo is somehow not found or at the end
            if idx == -1:
                self._log("Warning: 0x0002 echo not found, using index 0")
                idx = 0
            
            # MAC 0x0002 returns Device and Version in Big Endian (or Byte-wise: [Major, Minor])
            device = struct.unpack_from('>H', data, idx + 2)[0]
            
            major = data[idx + 4]
            minor = data[idx + 5]
            version = (major << 8) | minor
            
            self._log(f"Detected Firmware: Device 0x{device:04X}, Version V{major}.{minor:02d}")
        else:
            self._log("Failed to parse firmware version due to invalid length.")
            return False
            
        # 2. Look up DataFlash offset
        offset, csv_name = detect_dataflash_offset(self.ic_name, version, "DA Configuration")
        if offset is None:
            self._log(f"Warning: Could not find DA Configuration offset for {self.ic_name} V{major}.{minor:02d}. Defaulting to 0x4000.")
            da_addr = 0x4000
        else:
            self.csv_name = csv_name
            self.df_offsets = load_calibration_offsets(csv_name)
            self._log(f"Loaded CSV: {csv_name}, DA Config Offset: {offset}")
            # All these gauges (BQ40Z50, BQ78350) use 0x4000 as the base for DataFlash access
            da_addr = 0x4000 + offset
                
        # 3. Read DA Configuration
        self._log(f"Reading DA Configuration at 0x{da_addr:04X}...")
        addr_bytes = [da_addr & 0xFF, (da_addr >> 8) & 0xFF]
        self.smbus_write_block_raw(0x44, addr_bytes)
        time.sleep(0.05)
        da_data = self.smbus_read_block(0x44)
        
        if da_data:
            self._log(f"DA Config Raw Read: {da_data.hex(' ')}")
            
            # Find the echo of our address (e.g., 0x84 0x4F)
            echo_bytes = bytes(addr_bytes)
            idx = -1
            for i in range(len(da_data) - 1):
                if da_data[i] == echo_bytes[0] and da_data[i+1] == echo_bytes[1]:
                    idx = i
                    break
                    
            if idx == -1 and len(da_data) >= 4:
                self._log("Warning: Address echo not found in DA Config read, falling back to index 0.")
                idx = 0
                    
            if idx != -1 and idx + 3 < len(da_data):
                # Data starts right after the echo
                da_val = struct.unpack_from('<H', da_data, idx + 2)[0]
                if "BQ78350" in self.ic_name.upper():
                    # For BQ78350, DA Config is 1 byte, AFE Cell Map is the next 2 bytes (Big Endian)
                    da_val = struct.unpack_from('>H', da_data, idx + 3)[0]
                    self.afe_cell_map = da_val
                    self.active_cells = bin(da_val).count('1')
                    self._log(f"Parsed AFE Cell Map: 0x{da_val:04X} -> Detected {self.active_cells} active cells.")
                else:
                    cc0 = (da_val >> 0) & 1
                    cc1 = (da_val >> 1) & 1
                    # Bits: cc1 cc0 -> 00=1 cell, 01=2 cells, 10=3 cells, 11=4 cells
                    self.active_cells = ((cc1 << 1) | cc0) + 1
                    self._log(f"Parsed DA_VAL: 0x{da_val:04X} -> Detected {self.active_cells} active cells (CC1={cc1}, CC0={cc0}).")
                return True
            else:
                self._log("Failed to locate address echo in DA Config read.")
                
        self._log("Failed to read DA Configuration. Assuming 4 cells.")
        self.active_cells = 4
        return True

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
        if not self.cached_4000 or len(self.cached_4000) < 34:
            self._log("Warning: Failed to cache 0x4000 block at start. It may be read as zeros later.")
        else:
            self._log("0x4000 Calibration Block cached successfully.")
            
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
                                cell1_sum = 0
                                pack_sum = 0
                                batt_sum = 0
                                valid_count = 0
                                for blk in blocks:
                                    if len(blk) >= 14:
                                        cell1_sum += struct.unpack_from('<H', blk, 6)[0]
                                        pack_sum += struct.unpack_from('<H', blk, 14)[0]
                                        batt_sum += struct.unpack_from('<H', blk, 16)[0]
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
                                    if len(blk) >= 28:
                                        int_sum += struct.unpack_from('<H', blk, 18)[0]
                                        ts1_sum += struct.unpack_from('<H', blk, 20)[0]
                                        ts2_sum += struct.unpack_from('<H', blk, 22)[0]
                                        ts3_sum += struct.unpack_from('<H', blk, 24)[0]
                                        ts4_sum += struct.unpack_from('<H', blk, 26)[0]
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
                                    if len(blk) >= 7:
                                        # Raw CC is a 16-bit signed integer at offset 4 (after 1A 81 F0 BE 01)
                                        cc_sum += struct.unpack_from('<h', blk, 4)[0]
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
                        
                        struct.pack_into('<HHH', df_bytes, 0, cell1_g, pack_g, bat_g)
                        
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
                # Read DAStatus1 (0x0071) for BQ40Z50
                self.smbus_write_block_raw(0x44, [0x71, 0x00])
                time.sleep(0.05)
                data = self.smbus_read_block(0x44)
                if data and len(data) >= 34:
                    # 0: 0x71, 1: 0x00
                    cell1 = struct.unpack_from('<H', data, 2)[0]
                    cell2 = struct.unpack_from('<H', data, 4)[0]
                    cell3 = struct.unpack_from('<H', data, 6)[0]
                    cell4 = struct.unpack_from('<H', data, 8)[0]
                    bat = struct.unpack_from('<H', data, 10)[0]
                    pack = struct.unpack_from('<H', data, 12)[0]
                    
                    cells = [cell1, cell2, cell3, cell4]
                    if show_voltage:
                        for i in range(self.active_cells):
                            self.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1} (0x0071)", "-", cells[i], suffix=" mV")
                            
                        self.emit_result("V_Bat", "V_Bat (0x0071)", "-", bat, suffix=" mV")
                        self.emit_result("V_Pack", "V_Pack (0x0071)", "-", pack, suffix=" mV")
                
                self.smbus_write_block_raw(0x44, [0x72, 0x00])
                time.sleep(0.05)
                data2 = self.smbus_read_block(0x44)
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
                        
                if not data and not data2:
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
                modes_to_run = ["voltage", "temp", "current"]
            else:
                modes_to_run = [run_mode]
            
            ch_status_map = {}
            mode_code = 0 if run_mode == "voltage" else (1 if run_mode == "current" else 2)
            
            ch_mask = 0
            for ch in self.channels:
                ch_mask |= (1 << (ch - 1))

            target_cell1 = int(self.targets.get('cell1mv', 3200))
            target_pack = int(self.targets.get('packmv', 12780))
            target_bat = int(self.targets.get('batmv', 12780))

            self._log(f"--- Sending Hardware Calibration Command to RP2040 (Channels: {self.channels}) ---")
            
            # Send CMD_CALIB_RUN (0x60) packet
            payload = struct.pack(">B B H H H", ch_mask, mode_code, target_cell1, target_pack, target_bat)
            pkt = make_packet(0x60, payload)
            self.ser.reset_input_buffer()
            self.ser.write(pkt)
            
            # Read ACK response
            rx = self._read_packet()
            cmd, resp = parse_response(rx)
            if not isinstance(resp, (bytes, bytearray)) or len(resp) == 0 or resp[0] != RESP_OK:
                err_code = resp[0] if isinstance(resp, (bytes, bytearray)) and len(resp) > 0 else resp
                self._log(f"Error: RP2040 rejected hardware calibration start command. (Resp Code: {err_code}, Cmd: {cmd}, RAW: {rx.hex(' ') if rx else 'Empty'})")
                self.finished_signal.emit(False)
                return

            # Poll CMD_CALIB_STATUS (0x61) until state becomes 2 (DONE) or 3 (ERROR)
            calib_done = False
            for _ in range(60): # Max 6 seconds poll timeout
                if not self._running: break
                time.sleep(0.1)
                
                pkt_status = make_packet(0x61, b"")
                self.ser.reset_input_buffer()
                self.ser.write(pkt_status)
                
                rx_st = self._read_packet()
                st_cmd, st_resp = parse_response(rx_st)
                if isinstance(st_resp, (bytes, bytearray)) and st_resp[0] == RESP_OK:
                    state = st_resp[1]
                    err_channels = st_resp[3]
                    if state == 2: # DONE
                        calib_done = True
                        idx = 4
                        for ch in range(1, 7):
                            cell1_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
                            pack_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
                            bat_g = struct.unpack('<H', st_resp[idx:idx+2])[0]; idx += 2
                            ch_succ = (st_resp[idx] == 1); idx += 1
                            if ch in self.channels:
                                is_err = (err_channels & (1 << (ch - 1))) != 0
                                ch_status_map[ch] = ch_succ and not is_err
                                if ch_status_map[ch]:
                                    self._log(f"    [CH{ch} RP2040 HW Result] PASS -> Cell1 Gain: {cell1_g}, Pack Gain: {pack_g}, Bat Gain: {bat_g}")
                                    self.emit_result("Cell 1 Gain", "Cell 1 Gain", str(cell1_g), cell1_g, is_gain=True)
                                    self.emit_result("Pack Gain", "Pack Gain", str(pack_g), pack_g, is_gain=True)
                                    self.emit_result("Bat Gain", "Bat Gain", str(bat_g), bat_g, is_gain=True)
                                else:
                                    self._log(f"    [CH{ch} RP2040 HW Result] FAIL (ch_succ={ch_succ}, err_mask={bin(err_channels)})")
                        break
                    elif state == 3: # ERROR state from RP2040
                        self._log(f"    [RP2040 HW Result] RP2040 returned ERROR state (err_mask={bin(err_channels)})")
                        break
                else:
                    self._log(f"    [DEBUG] Poll status response: cmd={st_cmd}, resp={st_resp}")

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
                        if consecutive_fails[ch] >= 3:
                            continue # Skip checking this channel if it's already dead
                            
                        if not self.post_verify():
                            consecutive_fails[ch] += 1
                            if consecutive_fails[ch] >= 3:
                                self._log(f"Error: Communication lost on CH{ch} during monitoring.")
                        else:
                            consecutive_fails[ch] = 0
                            any_ch_alive = True
                            
                    if not any_ch_alive:
                        self._log("All channels lost communication. Exiting monitoring mode.")
                        break
                        
                    time.sleep(0.5)
            
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
