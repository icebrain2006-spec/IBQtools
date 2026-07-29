import os
import sys
import time
import struct
from PySide6.QtCore import QThread, Signal, Slot

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from updater_thread import make_packet, parse_response, RESP_OK, CMD_I2C_RAW, CMD_SMBUS_CMD, CMD_SMBUS_POLL_BLOCK
from calibrators.utils import detect_dataflash_offset

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
    finished_signal = Signal(bool)
    
    limits_update_signal = Signal(dict)
    
    def __init__(self, port, channels, script_dir, script_base, targets, ic_name, limits=None):
        super().__init__()
        self.port = port
        self.channels = channels
        self.ch = channels[0] if channels else 1
        self.addr = 0x0B
        self.script_dir = script_dir
        self.script_base = script_base
        self.targets = targets
        self.ic_name = ic_name
        self.limits = limits if limits is not None else {}
        self.ser = None
        self._running = True
        
        self.limits_update_signal.connect(self.on_limits_updated)
        
        self.active_cells = 4 # Default
        with open("scratch/limits_debug.txt", "w") as f:
            f.write(f"INIT LIMITS: {self.limits}\n")
            
    @Slot(dict)
    def on_limits_updated(self, new_limits):
        self.limits = new_limits
        self._log(f"DEBUG THREAD: Received new limits via signal: V_Cell 2={self.limits.get('V_Cell 2')}")
        
    def emit_result(self, param_key, param_name, raw_adc, val, is_gain=False, suffix=""):
        status = "INFO"
        if param_key in self.limits:
            min_val, max_val = self.limits[param_key]
            if min_val <= val <= max_val:
                status = "PASS"
            else:
                status = "FAIL"
                # Log exactly what the thread sees
                self._log(f"FAIL: {param_key} val={val} limits=({min_val}, {max_val})")
                
        if is_gain:
            # For gain rows, show the calculated gain value
            self.row_signal.emit(param_name, self.ch, str(raw_adc), status)
        else:
            # For validation rows, show the measured voltage/temp/current
            self.row_signal.emit(param_name, self.ch, f"{val}{suffix}", status)
            
    def stop(self):
        self._running = False
        
    def _log(self, msg):
        self.log_signal.emit(f"[CH{self.ch}] {msg}")
        
    def parse_val(self, s):
        if s.lower().startswith('0x'):
            return int(s, 16)
        return int(s)

    def smbus_write_word(self, reg, val):
        payload = struct.pack('<BBBBBBH', self.ch, self.addr, reg, 0, 2, 0, val)
        self.ser.write(make_packet(CMD_SMBUS_CMD, payload))
        rx = self._read_packet()
        cmd, resp = parse_response(rx)
        return resp and resp[0] == RESP_OK
        
    def smbus_write_block_raw(self, cmd_reg, data_bytes, use_pec=True):
        tx_data = bytearray([cmd_reg, len(data_bytes)]) + bytearray(data_bytes)
        if use_pec:
            pec_data = bytearray([(self.addr << 1)]) + tx_data
            pec = smbus_pec_calculate(pec_data)
            tx_data.append(pec)
            
        payload = struct.pack('<BBBB', self.ch, self.addr, len(tx_data), 0) + tx_data
        self.ser.write(make_packet(CMD_I2C_RAW, payload))
        rx = self._read_packet()
        cmd, resp = parse_response(rx)
        return resp and resp[0] == RESP_OK

    def _read_packet(self):
        rx = bytearray()
        while True:
            b = self.ser.read(1)
            if not b: return rx # Timeout
            if b[0] == 0x02:
                rx.extend(b)
                break
                
        len_bytes = self.ser.read(2)
        rx.extend(len_bytes)
        if len(len_bytes) < 2: return rx
        
        length = struct.unpack(">H", len_bytes)[0]
        rx.extend(self.ser.read(length + 3))
        return rx

    def smbus_read_word(self, cmd_reg):
        payload = struct.pack('<BBBBBB', self.ch, self.addr, cmd_reg, 1, 2, 1)
        self.ser.write(make_packet(CMD_SMBUS_CMD, payload))
        rx = self._read_packet()
        cmd, resp = parse_response(rx)
        if resp and resp[0] == RESP_OK:
            return resp[1:3]
        return None

    def smbus_read_block(self, cmd_reg):
        for attempt in range(10):
            if not self._running: return None
            payload = struct.pack('<BBBBBB', self.ch, self.addr, cmd_reg, 1, 32, 1)
            self.ser.write(make_packet(CMD_SMBUS_CMD, payload))
            rx = self._read_packet()
            cmd, resp = parse_response(rx)
            if cmd is None:
                time.sleep(0.05)
                continue
            if resp and resp[0] == RESP_OK:
                return resp[2:2+resp[1]]
            if resp and resp[0] == 0x04 and resp[1] == 0x04:
                time.sleep(0.05)
                continue
            break
        if resp:
            self._log(f"    -> Read Error: 0x{resp[0]:02x}, Detail: {resp[1] if len(resp)>1 else 'None'}")
        return None

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
            self._log(f"Loaded CSV: {csv_name}, DA Config Offset: {offset}")
            # Add 0x4000 base address for BQ40Z50
            if "BQ40Z50" in self.ic_name.upper() or "BQ4050" in self.ic_name.upper():
                da_addr = 0x4000 + offset
            else:
                da_addr = offset # May need adjustment for other ICs
                
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
                    
            if idx != -1 and idx + 3 < len(da_data):
                # Data starts right after the echo
                da_val = struct.unpack_from('<H', da_data, idx + 2)[0]
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
        
        new_gains = []
        
        for i, line in enumerate(lines):
            if not self._running:
                self._log("Calibration aborted.")
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
                    return False
                    
            elif cmd == 'B':
                reg = self.parse_val(parts[1])
                data_bytes = [self.parse_val(x) for x in parts[2:]]
                if self.smbus_write_block_raw(reg, data_bytes):
                    self._log("  => OK")
                else:
                    self._log("  => FAIL")
                    return False
                    
            elif cmd == 'X':
                delay = self.parse_val(parts[1])
                time.sleep(delay / 1000.0)
                self._log("  => OK")
                
            elif cmd == 'RW':
                reg = self.parse_val(parts[1])
                data = self.smbus_read_word(reg)
                if data:
                    self._log("  => OK: " + data.hex(' '))
                else:
                    self._log("  => FAIL")
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
                    if data and len(data) >= 4:
                        cal_en = (data[3] & 0x80) != 0
                        if (cal_en and expected == 1) or (not cal_en and expected == 0):
                            success = True
                            break
                if success:
                    self._log(f"  => OK (CAL_EN == {expected})")
                else:
                    self._log(f"  => FAIL (CAL_EN did not become {expected})")
                    return False
                    
            elif cmd == 'A':
                reg = self.parse_val(parts[1])
                interval = self.parse_val(parts[2])
                count = self.parse_val(parts[3])
                
                blocks = []
                for _ in range(count):
                    if not self._running: break
                    b = self.smbus_read_block(reg)
                    if b: blocks.append(b)
                    time.sleep(interval / 1000.0)
                    
                if blocks:
                    self._log(f"  => OK ({len(blocks)} blocks)")
                    if len(blocks) > 0 and self.targets:
                        # Logic changes based on mode
                        if mode_name == "voltage":
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
                            # TODO: Parse F082 temp format based on TRM
                            pass
                            
                        elif mode_name == "current":
                            # Parse F081 for CC
                            cc_sum = 0
                            valid_count = 0
                            for blk in blocks:
                                if len(blk) >= 6:
                                    cc_sum += struct.unpack_from('<i', blk, 2)[0]
                                    valid_count += 1
                                    
                            if valid_count > 0:
                                cc_avg = cc_sum / float(valid_count)
                                self._log(f"    Avg CC ADC -> {cc_avg:.2f}")
                                # Current Gain logic
                else:
                    self._log("  => FAIL")
                    return False
                    
            elif cmd == 'S':
                # Custom Save command for BQ40Z50
                if mode_name == "voltage":
                    if not new_gains or len(new_gains) < 3:
                        self._log("  => FAIL: Not enough gain data calculated!")
                        return False
                        
                    reg = self.parse_val(parts[1])
                    df_addr_bytes = [reg & 0xFF, (reg >> 8) & 0xFF]

                    self.smbus_write_block_raw(0x44, df_addr_bytes)
                    time.sleep(0.05)
                    old_data = self.smbus_read_block(0x44)
                    
                    if old_data and len(old_data) >= 34:
                        df_bytes = bytearray(old_data[2:34])
                    else:
                        self._log("  => FAIL: Could not read old calibration block")
                        return False
                        
                    cell1_g = new_gains[0]
                    pack_g = new_gains[1]
                    bat_g = new_gains[2]
                    
                    struct.pack_into('<HHH', df_bytes, 0, cell1_g, pack_g, bat_g)
                    
                    full_payload = df_addr_bytes + list(df_bytes)
                    
                    if self.smbus_write_block_raw(0x44, full_payload):
                        self._log("  => OK (Wrote Voltage Calibration Block)")
                    else:
                        self._log("  => FAIL writing block")
                        return False

        return True

    def post_verify(self):
        try:
            # Read DAStatus1 (0x0071)
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
                for i in range(self.active_cells):
                    self.emit_result(f"V_Cell {i+1}", f"V_Cell {i+1} (0x0071)", "-", cells[i], suffix=" mV")
                    
                self.emit_result("V_Bat", "V_Bat (0x0071)", "-", bat, suffix=" mV")
                self.emit_result("V_Pack", "V_Pack (0x0071)", "-", pack, suffix=" mV")
            
            self.smbus_write_block_raw(0x44, [0x72, 0x00])
            time.sleep(0.05)
            data = self.smbus_read_block(0x44)
            if data and len(data) >= 16:
                int_temp = struct.unpack_from('<H', data, 2)[0] * 0.1 - 273.15
                ts1 = struct.unpack_from('<H', data, 4)[0] * 0.1 - 273.15
                ts2 = struct.unpack_from('<H', data, 6)[0] * 0.1 - 273.15
                ts3 = struct.unpack_from('<H', data, 8)[0] * 0.1 - 273.15
                ts4 = struct.unpack_from('<H', data, 10)[0] * 0.1 - 273.15
                
                if self.targets.get("inttempcen", False):
                    self.emit_result("Int Temp", "Int Temp (0x0072)", "-", int_temp, suffix=" °C")
                if self.targets.get("ts1tempcen", False):
                    self.emit_result("TS1 Temp", "TS1 Temp (0x0072)", "-", ts1, suffix=" °C")
                if self.targets.get("ts2tempcen", False):
                    self.emit_result("TS2 Temp", "TS2 Temp (0x0072)", "-", ts2, suffix=" °C")
                if self.targets.get("ts3tempcen", False):
                    self.emit_result("TS3 Temp", "TS3 Temp (0x0072)", "-", ts3, suffix=" °C")
                if self.targets.get("ts4tempcen", False):
                    self.emit_result("TS4 Temp", "TS4 Temp (0x0072)", "-", ts4, suffix=" °C")
                    
                return True
            return False
        except Exception as e:
            self._log(f"CRASH in post_verify: {e}")
            return False

    def run(self):
        import serial
        try:
            self.ser = serial.Serial(self.port, 115200, timeout=0.1)
            time.sleep(0.5)
        except Exception as e:
            self._log(f"Error opening port: {e}")
            self.finished_signal.emit(False)
            return

        run_mode = self.targets.get("run_mode", "voltage")
        
        # 1. Detect Firmware and Configuration & 2. Run requested modes
        modes_to_run = []
        if run_mode == "all":
            modes_to_run = ["voltage", "temp", "current"]
        else:
            modes_to_run = [run_mode]
            
        success = True
        
        for ch in self.channels:
            if not self._running:
                break
            self.ch = ch
            self._log(f"--- Processing Calibration for Channel {ch} ---")
            
            if not self.detect_firmware_and_config():
                self._log("Warning: Could not detect configuration, proceeding with defaults.")
                
            for m in modes_to_run:
                script_path = os.path.join(self.script_dir, f"{self.script_base}_{m}.calib")
                if not self.execute_script(script_path, m):
                    success = False
                    break
                    
        # 3. Verification & Continuous Monitoring
        if success:
            self._log("--- Entering Continuous Monitoring Mode ---")
            consecutive_fails = {ch: 0 for ch in self.channels}
            while self._running:
                for ch in self.channels:
                    if not self._running:
                        break
                    self.ch = ch
                    if not self.post_verify():
                        consecutive_fails[ch] += 1
                        if consecutive_fails[ch] >= 3:
                            self._log(f"Error: Communication lost during monitoring.")
                    else:
                        consecutive_fails[ch] = 0
                time.sleep(0.5)
            
        self._log("--- Calibration Sequence Completed ---")
        self.finished_signal.emit(success)
