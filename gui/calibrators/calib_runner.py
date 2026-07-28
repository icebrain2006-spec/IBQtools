import time
import struct
from PySide6.QtCore import QThread, Signal
from updater_thread import make_packet, parse_response, RESP_OK, CMD_I2C_RAW, CMD_SMBUS_CMD, CMD_SMBUS_POLL_BLOCK

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
    row_signal = Signal(str, str, str, str) # param, raw, measured, status
    finished_signal = Signal(bool)
    
    def __init__(self, port, ch, script_path, targets):
        super().__init__()
        self.port = port
        self.ch = ch
        self.addr = 0x0B
        self.script_path = script_path
        self.targets = targets
        self.ser = None
        self._running = True
        
    def stop(self):
        self._running = False
        
    def _log(self, msg):
        self.log_signal.emit(msg)
        
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
        
    def _read_packet(self):
        """Reads exactly one packet to eliminate timeout delays."""
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
        payload = struct.pack('<BBBBBB', self.ch, self.addr, cmd_reg, 1, 2, 1) # use_pec=1
        self.ser.write(make_packet(CMD_SMBUS_CMD, payload))
        rx = self._read_packet()
        cmd, resp = parse_response(rx)
        if resp and resp[0] == RESP_OK:
            return resp[1:3]
        return None

    def smbus_read_block(self, cmd_reg):
        for attempt in range(10):
            if not self._running: return None
            payload = struct.pack('<BBBBBB', self.ch, self.addr, cmd_reg, 1, 32, 1) # use_pec=1
            self.ser.write(make_packet(CMD_SMBUS_CMD, payload))
            rx = self._read_packet()
            cmd, resp = parse_response(rx)
            if cmd is None:
                time.sleep(0.05)
                continue
            if resp and resp[0] == RESP_OK:
                return resp[2:2+resp[1]]
            if resp and resp[0] == 0x04 and resp[1] == 0x04:
                # NACK, device is busy. Retry!
                time.sleep(0.05)
                continue
            break
        if resp:
            self._log(f"    -> Read Error: 0x{resp[0]:02x}, Detail: {resp[1] if len(resp)>1 else 'None'}")
        return None

    def smbus_poll_block(self, cmd_reg, interval_ms, count):
        payload = struct.pack('<BBBBB', self.ch, self.addr, cmd_reg, interval_ms, count)
        self.ser.write(make_packet(CMD_SMBUS_POLL_BLOCK, payload))
        rx = self._read_packet()
        cmd, resp = parse_response(rx)
        if not resp or resp[0] != RESP_OK:
            return resp, []
            
        idx = 1
        blocks = []
        while idx < len(resp):
            rx_len = resp[idx]
            idx += 1
            if rx_len == 0 or idx + rx_len > len(resp):
                break
            blocks.append(resp[idx:idx+rx_len])
            idx += rx_len
        return resp, blocks

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

    def run(self):
        import serial
        try:
            self.ser = serial.Serial(self.port, 115200, timeout=0.1)
            time.sleep(0.5)
        except Exception as e:
            self._log(f"Error opening port: {e}")
            self.finished_signal.emit(False)
            return

        try:
            with open(self.script_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            self._log(f"--- Running Calibration Script: {self.script_path} ---")
            
            # State to hold calculated gains
            new_gains = []
            
            for i, line in enumerate(lines):
                if not self._running:
                    self._log("Calibration aborted.")
                    break
                    
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
                        self.finished_signal.emit(False)
                        return
                        
                elif cmd == 'B':
                    reg = self.parse_val(parts[1])
                    data_bytes = [self.parse_val(x) for x in parts[2:]]
                    if self.smbus_write_block_raw(reg, data_bytes):
                        self._log("  => OK")
                    else:
                        self._log("  => FAIL")
                        self.finished_signal.emit(False)
                        return
                        
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
                        self.finished_signal.emit(False)
                        return

                elif cmd == 'R':
                    reg = self.parse_val(parts[1])
                    data = self.smbus_read_block(reg)
                    if data:
                        self._log("  => OK: " + data.hex(' '))
                    else:
                        self._log("  => FAIL")
                        self.finished_signal.emit(False)
                        return
                        
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
                            # data[0]=0x57, data[1]=0x00, data[2]=LSB, data[3]=MSB
                            # Bit 15 is CAL_EN (0x80 in MSB)
                            cal_en = (data[3] & 0x80) != 0
                            if (cal_en and expected == 1) or (not cal_en and expected == 0):
                                success = True
                                break
                    if success:
                        self._log(f"  => OK (CAL_EN == {expected})")
                    else:
                        self._log(f"  => FAIL (CAL_EN did not become {expected})")
                        self.finished_signal.emit(False)
                        return

                elif cmd == 'A':
                    reg = self.parse_val(parts[1])
                    interval = self.parse_val(parts[2])
                    count = self.parse_val(parts[3])
                    
                    # Python-side polling to avoid firmware buffer limits
                    blocks = []
                    for _ in range(count):
                        if not self._running: break
                        b = self.smbus_read_block(reg)
                        if b: blocks.append(b)
                        time.sleep(interval / 1000.0)
                        
                    if blocks:
                        self._log(f"  => OK ({len(blocks)} blocks)")
                        self._log(f"  => First block RAW: {blocks[0].hex(' ')}")
                        
                        self._log(f"    Found {len(blocks)} ADC samples!")
                        if len(blocks) > 0 and self.targets:
                            cell1_sum = 0
                            pack_sum = 0
                            batt_sum = 0
                            
                            # Average all collected valid blocks
                            valid_count = 0
                            for blk in blocks:
                                if len(blk) >= 14:
                                    # 0xF081 format:
                                    # 0-1: MAC echo (81 F0)
                                    # 2-5: CC Raw Data (4 bytes)
                                    # 6-7: Cell 1 RAW
                                    # 8-9: Cell 2 RAW
                                    # 10-11: Cell 3 RAW
                                    # 12-13: Cell 4 RAW
                                    # 14-15: Pack RAW
                                    # 16-17: Bat RAW
                                    cell1_sum += struct.unpack_from('<H', blk, 6)[0]
                                    pack_sum += struct.unpack_from('<H', blk, 14)[0]
                                    batt_sum += struct.unpack_from('<H', blk, 16)[0]
                                    valid_count += 1
                                    
                            if valid_count > 0:
                                cell1_avg = cell1_sum / float(valid_count)
                                batt_avg = batt_sum / float(valid_count)
                                pack_avg = pack_sum / float(valid_count)
                                
                                self._log(f"    Average ADC ({valid_count} samples) -> Cell1: {cell1_avg:.2f}, Pack: {pack_avg:.2f}, Batt: {batt_avg:.2f}")
                                # Calculate Gains
                                if cell1_avg > 0:
                                    g = int((self.targets.get('cell1', 3200) / cell1_avg) * 65536)
                                    g = max(0, min(65535, g))
                                    new_gains.append(g)
                                    self._log(f"    New Cell 1 Gain = {g}")
                                    self.row_signal.emit("Cell 1 Voltage", f"{cell1_avg:.1f}", str(self.targets.get('cell1')), "PASS")
                                if pack_avg > 0:
                                    g = int((self.targets.get('pack', 12780) / pack_avg) * 65536)
                                    g = max(0, min(65535, g))
                                    new_gains.append(g)
                                    self._log(f"    New Pack Gain = {g}")
                                    self.row_signal.emit("Pack Voltage", f"{pack_avg:.1f}", str(self.targets.get('pack')), "PASS")
                                if batt_avg > 0:
                                    g = int((self.targets.get('batt', 12780) / batt_avg) * 65536)
                                    g = max(0, min(65535, g))
                                    new_gains.append(g)
                                    self._log(f"    New Batt Gain = {g}")
                                    self.row_signal.emit("Bat Voltage", f"{batt_avg:.1f}", str(self.targets.get('batt')), "PASS")
                    else:
                        self._log("  => FAIL")
                        self.finished_signal.emit(False)
                        return
                        
                elif cmd == 'S':
                    # Custom Save command for BQ40Z50 Voltage Calibration
                    # S 0x4000
                    if not new_gains or len(new_gains) < 3:
                        self._log("  => FAIL: Not enough gain data calculated!")
                        self.finished_signal.emit(False)
                        return
                        
                    reg = self.parse_val(parts[1])
                    df_addr_bytes = [reg & 0xFF, (reg >> 8) & 0xFF]

                    # 1. Read Old Block
                    self.smbus_write_block_raw(0x44, df_addr_bytes)
                    time.sleep(0.05)
                    old_data = self.smbus_read_block(0x44)
                    
                    if old_data and len(old_data) >= 34:
                        df_bytes = bytearray(old_data[2:34])
                    else:
                        self._log("  => FAIL: Could not read old calibration block")
                        self.finished_signal.emit(False)
                        return
                        
                    # 2. Modify ONLY Voltage Gains (starts at offset 0 in Class 104)
                    cell1_g = new_gains[0]
                    pack_g = new_gains[1]
                    bat_g = new_gains[2]
                    
                    # 0:Cell Gain (shared for all cells), 2:Pack Gain, 4:Bat Gain
                    struct.pack_into('<HHH', df_bytes, 0, cell1_g, pack_g, bat_g)
                    
                    # 3. Write Back
                    full_payload = df_addr_bytes + list(df_bytes)
                    
                    if self.smbus_write_block_raw(0x44, full_payload):
                        self._log("  => OK (Wrote Calibration Block)")
                    else:
                        self._log("  => FAIL writing block")
                        self.finished_signal.emit(False)
                        return
                        
            self._log("--- Calibration Sequence Completed ---")
            self.finished_signal.emit(True)
            
        except Exception as e:
            self._log(f"Exception during calibration: {e}")
            self.finished_signal.emit(False)
        finally:
            if self.ser:
                self.ser.close()
