import time
import struct
import serial
from PySide6.QtCore import QThread, Signal

PROTOCOL_STX = 0x02
PROTOCOL_ETX = 0x03
CMD_FW_UPDATE_RUN    = 0x40
CMD_FW_UPDATE_STATUS = 0x41
CMD_FW_UPDATE_STOP   = 0x42
CMD_I2C_RAW          = 0x21
CMD_FW_GET_FILE_INFO = 0x35
CMD_SMBUS_CMD        = 0x20
CMD_GET_VERSION      = 0x01
RESP_OK = 0x00

UPDATER_STATE_IDLE = 0
UPDATER_STATE_RUNNING = 1
UPDATER_STATE_DELAYING = 2
UPDATER_STATE_ERROR = 3
UPDATER_STATE_DONE = 4

def crc16_calculate(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def make_packet(cmd, payload):
    total_len = 1 + len(payload)
    header = struct.pack(">B H B", PROTOCOL_STX, total_len, cmd)
    crc_data = bytes([cmd]) + payload
    crc = crc16_calculate(crc_data)
    footer = struct.pack(">H B", crc, PROTOCOL_ETX)
    return header + payload + footer

def parse_response(rx_data):
    # Search for STX
    stx_idx = rx_data.find(PROTOCOL_STX)
    if stx_idx == -1:
        return None, "No STX found"
        
    rx_data = rx_data[stx_idx:]
    if len(rx_data) < 7:
        return None, "Response too short"
        
    length = struct.unpack(">H", rx_data[1:3])[0]
    expected_total = length + 4 # STX(1) + LEN(2) + PAYLOAD(length-1) + CMD(1) is in length + CRC(2) + ETX(1)
    
    # Actually: length = 1 (CMD) + payload_len
    # So total bytes from STX to ETX = 1(STX) + 2(LEN) + length + 2(CRC) + 1(ETX) = length + 6
    expected_total = length + 6
    
    if len(rx_data) < expected_total:
        return None, "Incomplete packet"
        
    if rx_data[expected_total - 1] != PROTOCOL_ETX:
        return None, "Invalid ETX"
        
    cmd = rx_data[3]
    payload = rx_data[4:expected_total-3]
    crc_rx = struct.unpack(">H", rx_data[expected_total-3:expected_total-1])[0]
    
    crc_calc = crc16_calculate(bytes([cmd]) + payload)
    if crc_calc != crc_rx:
        return None, "CRC mismatch"
    return cmd, payload

def get_file_info(port):
    packet = make_packet(CMD_FW_GET_FILE_INFO, b'')
    try:
        with serial.Serial(port, 115200, timeout=0.5) as ser:
            ser.write(packet)
            rx = ser.read(128)
            if not rx or len(rx) < 7:
                return None
            cmd, resp = parse_response(rx)
            if cmd == CMD_FW_GET_FILE_INFO and resp[0] == RESP_OK:
                fname = resp[17:81].split(b'\x00')[0].decode('ascii', errors='ignore')
                return fname
    except Exception:
        pass
    return None

def get_fw_version(port):
    packet = make_packet(CMD_GET_VERSION, b'')
    try:
        with serial.Serial(port, 115200, timeout=0.5) as ser:
            ser.write(packet)
            rx = ser.read(128)
            if not rx or len(rx) < 7:
                return None
            cmd, resp = parse_response(rx)
            if cmd == CMD_GET_VERSION and resp[0] == RESP_OK:
                return resp[1:].split(b'\x00')[0].decode('ascii', errors='ignore')
    except Exception:
        pass
    return None

class UpdaterWorker(QThread):
    log_msg = Signal(str)
    progress_updated = Signal(int, int) # (ch_idx, pct)
    status_updated = Signal(int, str)   # (ch_idx, text)
    verify_updated = Signal(int, str, int)   # (ch_idx, date_str, sn_int)
    finished = Signal(bool)
    
    def __init__(self, port, channels, loop_count=1, get_expected_cb=None, parent=None):
        super().__init__(parent)
        self.port = port
        self.channels = channels
        self.loop_count = loop_count
        self.get_expected_cb = get_expected_cb
        self.is_running = True
        self.ser = None

    def _start_updater_multi(self):
        ch_mask = 0
        for ch in self.channels:
            ch_mask |= (1 << (ch - 1))
        packet = make_packet(CMD_FW_UPDATE_RUN, bytes([ch_mask]))
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        time.sleep(0.1)
        rx = self.ser.read(64)
        if not rx:
            return False, "Timeout"
        cmd, payload = parse_response(rx)
        if cmd == CMD_FW_UPDATE_RUN and payload[0] == RESP_OK:
            return True, "OK"
        return False, f"Failed or Busy: {payload[0]:#x}"

    def _check_status(self):
        packet = make_packet(CMD_FW_UPDATE_STATUS, b"")
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        
        header = self.ser.read(4)
        if len(header) < 4 or header[0] != PROTOCOL_STX:
            return None
            
        length = struct.unpack(">H", header[1:3])[0]
        payload_len = length - 1
        remaining_bytes = payload_len + 3 
        
        rest = self.ser.read(remaining_bytes)
        if len(rest) < remaining_bytes:
            return None
            
        rx = header + rest
        res = parse_response(rx)
        if res[0] is None:
            return None
            
        cmd, payload = res
        if cmd == CMD_FW_UPDATE_STATUS and payload[0] == RESP_OK:
            state = payload[1]
            current_line = struct.unpack(">I", payload[2:6])[0]
            total_lines = struct.unpack(">I", payload[6:10])[0]
            active_channels = payload[10]
            error_channels = payload[11]
            error_code = struct.unpack(">b", bytes([payload[12]]))[0]
            return (state, current_line, total_lines, active_channels, error_channels, error_code)
        return None

    def _stop_updater(self):
        if self.ser and self.ser.is_open:
            packet = make_packet(CMD_FW_UPDATE_STOP, b"")
            self.ser.reset_input_buffer()
            self.ser.write(packet)
            time.sleep(0.1)

    def _read_smbus_word(self, ch, addr, reg):
        payload = bytes([ch, addr, reg, 1, 2, 0, 0])
        packet = make_packet(CMD_SMBUS_CMD, payload)
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        
        # Read multiple times if necessary to skip garbage
        start_time = time.time()
        buf = b""
        raw_rx = b""
        
        # Temporarily reduce timeout to prevent blocking for 1.5s per read
        old_timeout = self.ser.timeout
        self.ser.timeout = 0.05
        
        try:
            while time.time() - start_time < 1.0:
                rx = self.ser.read(128)
                if rx: 
                    raw_rx += rx
                    buf += rx
                    # Workaround for Pico SDK stdout CRLF conversion
                    buf = buf.replace(b'\r\n', b'\n')
                
                stx_idx = buf.find(PROTOCOL_STX)
                if stx_idx != -1 and len(buf) >= stx_idx + 7:
                    length = struct.unpack(">H", buf[stx_idx+1:stx_idx+3])[0]
                    expected_total = length + 6
                    if len(buf) >= stx_idx + expected_total:
                        pkt_chunk = buf[stx_idx:stx_idx+expected_total]
                        cmd, resp = parse_response(pkt_chunk)
                        
                        if cmd == CMD_SMBUS_CMD:
                            if resp and resp[0] == RESP_OK:
                                return resp[1] | (resp[2] << 8)
                            else:
                                # It's an SMBus response, but not OK
                                self.log_msg.emit(f"[DEBUG] SMBus Error Resp: {resp.hex() if resp else 'None'}")
                                return None
                                
                        # Discard this packet and continue looking
                        buf = buf[stx_idx+expected_total:]
                        continue
        finally:
            self.ser.timeout = old_timeout
                    
        self.log_msg.emit(f"[DEBUG] _read_smbus_word Timeout. Raw RX: {raw_rx.hex()}")
        return None
        
    def _write_smbus_word(self, ch, addr, reg, word_val):
        val_lo = word_val & 0xFF
        val_hi = (word_val >> 8) & 0xFF
        payload = bytes([ch, addr, reg, 0, 2, 0, val_lo, val_hi])
        packet = make_packet(CMD_SMBUS_CMD, payload)
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        
        start_time = time.time()
        buf = b""
        
        old_timeout = self.ser.timeout
        self.ser.timeout = 0.05
        
        try:
            while time.time() - start_time < 1.0:
                rx = self.ser.read(128)
                if rx: 
                    buf += rx
                    buf = buf.replace(b'\r\n', b'\n')
                
                stx_idx = buf.find(PROTOCOL_STX)
                if stx_idx != -1 and len(buf) >= stx_idx + 7:
                    length = struct.unpack(">H", buf[stx_idx+1:stx_idx+3])[0]
                    expected_total = length + 6
                    if len(buf) >= stx_idx + expected_total:
                        pkt_chunk = buf[stx_idx:stx_idx+expected_total]
                        cmd, resp = parse_response(pkt_chunk)
                        
                        if cmd == CMD_SMBUS_CMD:
                            return resp and resp[0] == RESP_OK
                                
                        buf = buf[stx_idx+expected_total:]
                        continue
        finally:
            self.ser.timeout = old_timeout
            
        return False

    def _read_sbd_info(self, ch):
        # 0x1B: Manufacture Date, 0x1C: Serial Number
        date_val = self._read_smbus_word(ch, 0x0B, 0x1B)
        serial_val = self._read_smbus_word(ch, 0x0B, 0x1C)
        
        if date_val is None or serial_val is None:
            return None, None
            
        year = (date_val >> 9) + 1980
        month = (date_val >> 5) & 0x0F
        day = date_val & 0x1F
        
        return f"{year}-{month:02d}-{day:02d}", serial_val

    def run(self):
        self.log_msg.emit(f"[INFO] Connecting to RP2040 on {self.port}...")
        try:
            self.ser = serial.Serial(self.port, 115200, timeout=1.5)
        except Exception as e:
            self.log_msg.emit(f"[ERROR] Failed to open {self.port}: {e}")
            self.finished.emit(False)
            return

        overall_success = True
        
        for loop in range(self.loop_count):
            if not self.is_running:
                break
                
            self.log_msg.emit(f"\n[INFO] Starting Loop {loop + 1}/{self.loop_count}")
            ok, msg = self._start_updater_multi()
            if not ok:
                self.log_msg.emit(f"[ERROR] Failed to start updater: {msg}")
                overall_success = False
                break
                
            self.log_msg.emit("[INFO] Updater running on RP2040. Monitoring...")
            
            last_line = -1
            hang_counter = 0
            
            while self.is_running:
                status = self._check_status()
                if status is None:
                    hang_counter += 1
                    if hang_counter > 10: # 5 seconds
                        self.log_msg.emit("[ERROR] RP2040 not responding to status poll (Hardware/I2C Hang).")
                        overall_success = False
                        break
                    time.sleep(0.5)
                    continue
                    
                hang_counter = 0
                    
                state, current_line, total_lines, active, err_mask, err_code = status
                
                pct = int((current_line / total_lines * 100)) if total_lines > 0 else 0
                # self.log_msg.emit(f"Progress: {pct}% [{current_line}/{total_lines}] | ErrMask: {err_mask:#04x}")
                
                # Update UI
                for ch in self.channels:
                    # Check if channel had an error
                    is_err = err_mask & (1 << (ch - 1))
                    if is_err:
                        self.status_updated.emit(ch, f"ERROR (Code {err_code})")
                        self.progress_updated.emit(ch, 0)
                    else:
                        if state == UPDATER_STATE_DONE:
                            self.progress_updated.emit(ch, 100)
                            self.status_updated.emit(ch, "DONE")
                        else:
                            self.progress_updated.emit(ch, pct)
                            self.status_updated.emit(ch, "Flashing...")
                
                if state == UPDATER_STATE_ERROR:
                    self.log_msg.emit(f"[CRITICAL] Updater Error Code: {err_code}")
                    self._stop_updater()
                    overall_success = False
                    break
                    
                if state == UPDATER_STATE_DONE:
                    self.log_msg.emit("[SUCCESS] Firmware update completed. Waiting for BQ chips to reboot...")
                    self._stop_updater()
                    time.sleep(1.0)
                    self.ser.reset_input_buffer()
                    
                    for ch in self.channels:
                        if not (err_mask & (1 << (ch - 1))):
                            # If callback is provided, we can fetch the SN to write
                            fmt = "DEC"
                            if self.get_expected_cb:
                                exp_date, exp_sn_int, fmt, should_write = self.get_expected_cb(ch)
                                if should_write:
                                    self.log_msg.emit(f"[CH {ch}] Writing Serial Number: {exp_sn_int} (0x{exp_sn_int:04X})")
                                    ok = self._write_smbus_word(ch, 0x0B, 0x1C, exp_sn_int)
                                    if not ok:
                                        self.log_msg.emit(f"[CH {ch}] Write Serial Number FAILED!")
                                    time.sleep(0.1) # allow time for DF save
                                    
                            date_str, sn_val = self._read_sbd_info(ch)
                            self.verify_updated.emit(ch, date_str or "", sn_val if sn_val is not None else -1)
                            
                            if date_str and sn_val is not None:
                                sn_str = f"0x{sn_val:04X}" if fmt == "HEX" else str(sn_val)
                                self.log_msg.emit(f"[CH {ch}] M: {date_str}, SN: {sn_str}")
                            else:
                                self.log_msg.emit(f"[CH {ch}] Verify Failed")
                    break
                    
                if current_line == last_line and state != UPDATER_STATE_DELAYING:
                    hang_counter += 1
                    if hang_counter > 15:
                        self.log_msg.emit("[TIMEOUT] Hang detected. Stopping...")
                        self._stop_updater()
                        overall_success = False
                        break
                else:
                    hang_counter = 0
                    
                last_line = current_line
                time.sleep(1.0)
                
            if not self.is_running:
                self.log_msg.emit("[WARN] Aborted by user.")
                self._stop_updater()
                overall_success = False
                break
                
            if loop < self.loop_count - 1:
                time.sleep(2.0)
                
        if self.ser:
            self.ser.close()
            
        self.finished.emit(overall_success)

    def stop(self):
        self.is_running = False
        self.log_msg.emit("[INFO] Stop requested...")

class SerialCheckWorker(UpdaterWorker):
    def __init__(self, port, channels, parent=None):
        super().__init__(port, channels, loop_count=1, get_expected_cb=None, parent=parent)
        
    def run(self):
        self.log_msg.emit(f"[INFO] Connecting to {self.port} for Serial Check...")
        try:
            self.ser = serial.Serial(self.port, 115200, timeout=1.5)
        except Exception as e:
            self.log_msg.emit(f"[ERROR] Failed to open {self.port}: {e}")
            self.finished.emit(False)
            return

        self.ser.reset_input_buffer()
        
        for ch in self.channels:
            if not self.is_running:
                break
                
            self.status_updated.emit(ch, "Reading...")
            date_str, sn_val = self._read_sbd_info(ch)
            
            if date_str and sn_val is not None:
                sn_hex = f"0x{sn_val:04X}"
                sn_dec = str(sn_val)
                self.log_msg.emit(f"[CH {ch}] READ -> M: {date_str}, SN: {sn_dec} ({sn_hex})")
                self.status_updated.emit(ch, f"Read: {sn_hex}")
            else:
                self.log_msg.emit(f"[CH {ch}] READ -> Failed to read from chip.")
                self.status_updated.emit(ch, "Read Failed")
                
        if self.ser:
            self.ser.close()
            
        self.finished.emit(True)
