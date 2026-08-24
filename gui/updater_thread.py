import time
import struct
import serial
import winsound
from PySide6.QtCore import QThread, Signal

PROTOCOL_STX = 0x02
PROTOCOL_ETX = 0x03
CMD_FW_UPLOAD_START  = 0x30
CMD_FW_UPLOAD_DATA   = 0x31
CMD_FW_UPLOAD_END    = 0x32
CMD_FW_UPDATE_RUN    = 0x40
CMD_FW_UPDATE_STATUS = 0x41
CMD_FW_UPDATE_STOP   = 0x42
CMD_I2C_RAW          = 0x21
CMD_FW_GET_FILE_INFO = 0x35
CMD_SMBUS_CMD        = 0x20
CMD_SMBUS_POLL_BLOCK = 0x22
CMD_GET_VERSION      = 0x01
CMD_RELAY_SET        = 0x10
CMD_SET_LED_STATE    = 0x50
RESP_OK = 0x00

UPDATER_STATE_IDLE = 0
UPDATER_STATE_RUNNING = 1
UPDATER_STATE_DELAYING = 2
UPDATER_STATE_ERROR = 3
UPDATER_STATE_DONE = 4

def set_led_state(port, color_hex, mode, duration_sec):
    # color_hex: e.g. 0x0000FFFF (Cyan)
    # mode: 0 (Solid), 1 (Blink)
    payload = struct.pack(">I B B", color_hex, mode, duration_sec)
    packet = make_packet(CMD_SET_LED_STATE, payload)
    
    # Retry loop for COM port open to handle Windows handle delay
    ser = None
    for _ in range(10):  # Increased to 10 retries
        try:
            ser = serial.Serial(port, 115200, timeout=0.2)
            break
        except Exception:
            time.sleep(0.1)
            
    if ser is None:
        # print(f"[LED] Failed to open {port}")
        return False
        
    try:
        ser.write(packet)
        ser.timeout = 0.2
        rx = ser.read(10)
        # print(f"[LED] {port} color={color_hex:X} mode={mode} resp={rx.hex()}")
    except Exception as e:
        # print(f"[LED] Exception: {e}")
        pass
    finally:
        if ser:
            ser.close()
    return True


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
            rx = ser.read(256)
            if not rx or len(rx) < 7:
                return None
            cmd, resp = parse_response(rx)
            if cmd == CMD_FW_GET_FILE_INFO and resp[0] == RESP_OK:
                fname = resp[17:81].split(b'\x00')[0].decode('ascii', errors='ignore')
                ic_type = ""
                version = ""
                if len(resp) >= 81 + 32 + 32:
                    ic_type = resp[81:113].split(b'\x00')[0].decode('ascii', errors='ignore')
                    version = resp[113:145].split(b'\x00')[0].decode('ascii', errors='ignore')
                return (fname, ic_type, version)
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

class GlobalPreflightWorker(QThread):
    finished_check = Signal(bool, object) # (success, dict_of_errors {board_id: [channels]})
    log_msg = Signal(str)
    
    def __init__(self, board_configs, parent=None):
        super().__init__(parent)
        self.board_configs = board_configs # list of dicts: {'board_id': id, 'port': port, 'channels': [1,2,3]}
        self.is_running = True
        
    def _read_smbus_word(self, ser, ch, addr, reg):
        payload = bytes([ch, addr, reg, 1, 2, 0, 0])
        packet = make_packet(CMD_SMBUS_CMD, payload)
        ser.reset_input_buffer()
        ser.write(packet)
        
        start_time = time.time()
        buf = b""
        old_timeout = ser.timeout
        ser.timeout = 0.05
        
        try:
            while time.time() - start_time < 0.5:
                rx = ser.read(128)
                if rx: 
                    buf += rx
                
                stx_idx = buf.find(PROTOCOL_STX)
                if stx_idx != -1 and len(buf) >= stx_idx + 7:
                    length = struct.unpack(">H", buf[stx_idx+1:stx_idx+3])[0]
                    expected_total = length + 6
                    if len(buf) >= stx_idx + expected_total:
                        pkt_chunk = buf[stx_idx:stx_idx+expected_total]
                        cmd, resp = parse_response(pkt_chunk)
                        
                        if cmd == CMD_SMBUS_CMD:
                            self.log_msg.emit(f"    [RAW IO] TX({len(packet)}b): {packet.hex(' ')} | RX({len(pkt_chunk)}b): {pkt_chunk.hex(' ')}")
                            return resp and resp[0] == RESP_OK
                        buf = buf[stx_idx+expected_total:]
                        continue
        finally:
            ser.timeout = old_timeout
        return False

    def _read_sbd_info(self, ser, ch):
        date_ok = self._read_smbus_word(ser, ch, 0x0B, 0x1B)
        serial_ok = self._read_smbus_word(ser, ch, 0x0B, 0x1C)
        return date_ok and serial_ok

    def _exit_rom_mode(self, ser, ch):
        # ROM mode exit command: Write 0x08 to 0x0B (0 data bytes)
        payload = bytes([ch, 0x0B, 1, 0, 0x08])
        packet = make_packet(CMD_I2C_RAW, payload)
        ser.reset_input_buffer()
        ser.write(packet)
        time.sleep(0.01)

    def run(self):
        self.log_msg.emit("[INFO] Starting Global Pre-flight SMBus Check...")
        all_errors = {}
        
        for cfg in self.board_configs:
            if not self.is_running:
                break
                
            b_id = cfg['board_id']
            port = cfg['port']
            channels = cfg['channels']
            
            if not channels:
                continue
                
            ser = None
            for _ in range(5):
                try:
                    ser = serial.Serial(port, 115200, timeout=1.5)
                    break
                except Exception:
                    time.sleep(0.1)
                    
            if ser is None:
                try:
                    # One final attempt to capture the actual exception
                    ser = serial.Serial(port, 115200, timeout=1.5)
                except Exception as e:
                    self.log_msg.emit(f"[ERROR] Global Check Failed: Cannot open {port} for Board {b_id}: {e}")
                    all_errors[b_id] = channels
                    continue
                
            ch_errors = []
            
            # -- Exit ROM Mode before pre-flight --
            for ch in channels:
                if not self.is_running:
                    ser.close()
                    return
                self._exit_rom_mode(ser, ch)
                
            time.sleep(0.5) # Wait for BQ to boot into firmware mode
            
            for ch in channels:
                if not self.is_running:
                    ser.close()
                    return
                    
                if not self._read_sbd_info(ser, ch):
                    ch_errors.append(ch)
                    
            ser.close()
            
            if ch_errors:
                self.log_msg.emit(f"[ERROR] Global Pre-flight Check failed on Board {b_id}, CH: {ch_errors}")
                all_errors[b_id] = ch_errors
                
        if self.is_running:
            if all_errors:
                self.finished_check.emit(False, all_errors)
            else:
                self.log_msg.emit("[SUCCESS] All boards passed Global Pre-flight Check.")
                time.sleep(0.5) # Wait for Windows COM port handles to fully release
                self.finished_check.emit(True, {})


class UpdaterWorker(QThread):
    log_msg = Signal(str)
    progress_updated = Signal(int, int) # (ch_idx, pct)
    status_updated = Signal(int, str)   # (ch_idx, text)
    verify_updated = Signal(int, str, int)   # (ch_idx, date_str, sn_int)
    finished = Signal(bool)
    
    def __init__(self, port, channels, loop_count=1, get_expected_cb=None, skip_preflight=False, parent=None):
        super().__init__(parent)
        self.port = port
        self.channels = channels
        self.loop_count = loop_count
        self.get_expected_cb = get_expected_cb
        self.skip_preflight = skip_preflight
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
        payload = bytes([ch, addr, reg, 0, 2, 1, val_lo, val_hi])  # Set use_pec=1
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
                            self.log_msg.emit(f"    [RAW IO] TX({len(packet)}b): {packet.hex(' ')} | RX({len(pkt_chunk)}b): {pkt_chunk.hex(' ')}")
                            if resp and resp[0] == RESP_OK and len(resp) >= 3:
                                return struct.unpack("<H", resp[1:3])[0]
                            return None
                                
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

    def _exit_rom_mode(self, ch):
        # ROM mode exit command: Write 0x08 to 0x0B (0 data bytes)
        payload = bytes([ch, 0x0B, 1, 0, 0x08])
        packet = make_packet(CMD_I2C_RAW, payload)
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        time.sleep(0.01)

    def run(self):
        self.log_msg.emit(f"[INFO] Connecting to RP2040 on {self.port}...")
        self.ser = None
        for _ in range(5):
            try:
                self.ser = serial.Serial(self.port, 115200, timeout=1.5)
                break
            except Exception:
                time.sleep(0.1)
                
        if self.ser is None:
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
            
            # --- Pre-flight SMBus Check ---
            if not self.skip_preflight:
                self.log_msg.emit("[INFO] Pre-flight SMBus check (Waking up BQ...)")
                
                # -- Exit ROM Mode before pre-flight --
                for ch in self.channels:
                    if not self.is_running:
                        break
                    self._exit_rom_mode(ch)
                    
                if not self.is_running:
                    break
                    
                time.sleep(0.5) # Wait for BQ to boot into firmware mode
                
                ch_errors = []
                for ch in self.channels:
                    if not self.is_running:
                        break
                    self.status_updated.emit(ch, "Checking SMBus...")
                    date_str, sn_val = self._read_sbd_info(ch)
                    if date_str is None or sn_val is None:
                        ch_errors.append(ch)
                        self.status_updated.emit(ch, "SMBus Error")
                    else:
                        self.status_updated.emit(ch, "SMBus OK")
                        
                if not self.is_running:
                    break
                    
                if ch_errors:
                    self.log_msg.emit(f"[ERROR] Pre-flight check failed on CH: {ch_errors}. Aborting board.")
                    # Mark healthy channels as Aborted so they don't stay on "SMBus OK"
                    for ch in self.channels:
                        if ch not in ch_errors:
                            self.status_updated.emit(ch, "Aborted")
                    overall_success = False
                    break
            # ------------------------------
            
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
                    for ch in self.channels:
                        self.verify_updated.emit(ch, "", -1)
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
                                exp_date, exp_sn_int, fmt, should_write_sn, should_write_date = self.get_expected_cb(ch)
                                
                                if should_write_date:
                                    try:
                                        y, m, d = map(int, exp_date.split('-'))
                                        date_val = d + (m * 32) + ((y - 1980) * 512)
                                        self.log_msg.emit(f"[CH {ch}] Writing Expected Date: {exp_date} (0x{date_val:04X})")
                                        ok = self._write_smbus_word(ch, 0x0B, 0x1B, date_val)
                                        if not ok:
                                            self.log_msg.emit(f"[CH {ch}] Write Date FAILED!")
                                        time.sleep(0.1)
                                    except Exception as e:
                                        self.log_msg.emit(f"[CH {ch}] Failed to parse Date: {e}")
                                        
                                if should_write_sn:
                                    write_val = exp_sn_int
                                    if fmt == "DEC":
                                        try:
                                            write_val = int(str(exp_sn_int), 16)
                                        except ValueError:
                                            pass
                                    self.log_msg.emit(f"[CH {ch}] Writing Serial Number: {exp_sn_int} (0x{write_val:04X})")
                                    ok = self._write_smbus_word(ch, 0x0B, 0x1C, write_val)
                                    if not ok:
                                        self.log_msg.emit(f"[CH {ch}] Write Serial Number FAILED!")
                                    time.sleep(0.1) # allow time for DF save
                                    
                            date_str, sn_val = self._read_sbd_info(ch)
                            self.verify_updated.emit(ch, date_str or "", sn_val if sn_val is not None else -1)
                            
                            if date_str and sn_val is not None:
                                if fmt == "HEX":
                                    sn_str = f"0x{sn_val:04X}"
                                else:
                                    try:
                                        sn_str = str(int(f"{sn_val:X}", 10))
                                    except ValueError:
                                        sn_str = f"INVALID_BCD_0x{sn_val:04X}"
                                self.log_msg.emit(f"[CH {ch}] M: {date_str}, SN: {sn_str}")
                            else:
                                self.log_msg.emit(f"[CH {ch}] Verify Failed")
                        else:
                            self.log_msg.emit(f"[CH {ch}] Skipped verify due to flash error.")
                            self.verify_updated.emit(ch, "", -1)
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
    def __init__(self, port, channels, fmt="DEC", parent=None):
        super().__init__(port, channels, loop_count=1, get_expected_cb=None, parent=parent)
        self.fmt = fmt
        
    def run(self):
        self.log_msg.emit(f"[INFO] Connecting to {self.port} for Serial Check...")
        self.ser = None
        for _ in range(5):
            try:
                self.ser = serial.Serial(self.port, 115200, timeout=1.5)
                break
            except Exception:
                time.sleep(0.1)
                
        if self.ser is None:
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
                if self.fmt == "HEX":
                    sn_str = sn_hex
                else:
                    try:
                        sn_str = str(int(f"{sn_val:X}", 10))
                    except ValueError:
                        sn_str = f"INVALID_BCD_{sn_hex}"
                
                self.log_msg.emit(f"[CH {ch}] READ -> M: {date_str}, SN: {sn_str} ({sn_hex})")
                self.status_updated.emit(ch, f"Read: {sn_str} ({sn_hex})")
            else:
                self.log_msg.emit(f"[CH {ch}] READ -> Failed to read from chip.")
                self.status_updated.emit(ch, "Read Failed")
                
        if self.ser:
            self.ser.close()
            
        self.finished.emit(True)

class ScanWorker(QThread):
    finished = Signal(list)
    progress_updated = Signal(int)
    log_msg = Signal(str)

    def __init__(self, ports, parent=None):
        super().__init__(parent)
        self.ports = ports
        self.is_running = True

    def run(self):
        valid_ports = []
        total = len(self.ports)
        if total == 0:
            self.finished.emit([])
            return

        for i, port in enumerate(self.ports):
            if not self.is_running:
                break
            self.log_msg.emit(f"Scanning {port}...")
            version = get_fw_version(port)
            if version:
                self.log_msg.emit(f"  -> Found RP2040 ({version}) on {port}")
                valid_ports.append(port)
            else:
                self.log_msg.emit(f"  -> No RP2040 response on {port}")
            self.progress_updated.emit(int((i + 1) / total * 100))
            
        self.finished.emit(valid_ports)
        
    def stop(self):
        self.is_running = False

class DisconnectionMonitor(QThread):
    channel_disconnected = Signal(int)
    log_msg = Signal(str)

    def __init__(self, port, channels, parent=None):
        super().__init__(parent)
        self.port = port
        self.channels_to_monitor = list(channels)
        self.is_running = True

    def _read_smbus_word(self, ser, ch, addr, reg):
        # 똑같은 로직의 SMBus Read 패킷 생성
        payload = bytes([ch, addr, reg, 1, 2, 0, 0])
        packet = make_packet(CMD_SMBUS_CMD, payload)
        ser.reset_input_buffer()
        ser.write(packet)
        
        start_time = time.time()
        buf = b""
        old_timeout = ser.timeout
        ser.timeout = 0.05
        
        try:
            while time.time() - start_time < 0.3:
                rx = ser.read(128)
                if rx: 
                    buf += rx
                
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
            ser.timeout = old_timeout
        return False

    def run(self):
        self.log_msg.emit(f"[INFO] Started Disconnection Monitor on {self.port} for channels {self.channels_to_monitor}")
        ser = None
        for _ in range(5):
            try:
                ser = serial.Serial(self.port, 115200, timeout=0.5)
                break
            except Exception:
                time.sleep(0.1)
                
        if ser is None:
            self.log_msg.emit("[WARN] Disconnection Monitor failed to open COM port.")
            return

        try:
            while self.is_running and self.channels_to_monitor:
                channels_to_remove = []
                for ch in self.channels_to_monitor:
                    if not self.is_running:
                        break
                    
                    # 0x0B 주소의 0x1C (Serial Number) 읽기 시도
                    success = self._read_smbus_word(ser, ch, 0x0B, 0x1C)
                    if not success:
                        # 한 번 더 확인 (노이즈로 인한 일시적 통신 실패 대비)
                        time.sleep(0.1)
                        success_retry = self._read_smbus_word(ser, ch, 0x0B, 0x1C)
                        if not success_retry:
                            self.log_msg.emit(f"[CH {ch}] Board disconnection detected.")
                            self.channel_disconnected.emit(ch)
                            channels_to_remove.append(ch)
                            
                for ch in channels_to_remove:
                    self.channels_to_monitor.remove(ch)
                    
                time.sleep(0.5)
        finally:
            if ser and ser.is_open:
                ser.close()
        
        if not self.channels_to_monitor:
            self.log_msg.emit("[INFO] All monitored channels disconnected. Monitor stopped.")

    def stop(self):
        self.is_running = False

class UploadWorker(QThread):
    finished = Signal(bool)
    progress_updated = Signal(int)
    log_msg = Signal(str)

    def __init__(self, port, file_path, parent=None):
        super().__init__(parent)
        self.port = port
        self.file_path = file_path
        self.is_running = True
        
    def send_and_wait(self, ser, packet, expected_cmd, timeout=2.0):
        ser.reset_input_buffer()
        ser.write(packet)
        
        start_time = time.time()
        rx_buf = bytearray()
        
        while time.time() - start_time < timeout:
            if not self.is_running:
                return None
            if ser.in_waiting:
                rx_buf.extend(ser.read(ser.in_waiting))
                if len(rx_buf) >= 7 and rx_buf[0] == PROTOCOL_STX and rx_buf[-1] == PROTOCOL_ETX:
                    cmd, payload = parse_response(rx_buf)
                    if cmd == expected_cmd:
                        return payload
            time.sleep(0.01)
        return None

    def run(self):
        import os, zlib
        self.log_msg.emit(f"[INFO] Connecting to {self.port} for SLFS Upload...")
        
        if not os.path.exists(self.file_path):
            self.log_msg.emit(f"[ERROR] File '{self.file_path}' not found.")
            self.finished.emit(False)
            return
            
        try:
            with open(self.file_path, 'rb') as f:
                file_data = f.read()
        except Exception as e:
            self.log_msg.emit(f"[ERROR] Failed to read file: {e}")
            self.finished.emit(False)
            return
            
        file_size = len(file_data)
        file_crc = zlib.crc32(file_data) & 0xFFFFFFFF
        file_timestamp = int(os.path.getmtime(self.file_path)) & 0xFFFFFFFF
        filename_str = os.path.basename(self.file_path)[:63]
        
        ic_type_str = "Unknown"
        version_str = "Unknown"
        
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in range(10):
                    line = f.readline().strip()
                    if line.startswith("; IC Type:"):
                        ic_type_str = line.split(":", 1)[1].strip()[:31]
                    elif line.startswith("; Version:"):
                        version_str = line.split(":", 1)[1].strip()[:31]
        except Exception as e:
            self.log_msg.emit(f"[WARN] Could not parse SLFS header - {e}")
        
        try:
            ser = serial.Serial(self.port, 115200, timeout=1.0)
        except Exception as e:
            self.log_msg.emit(f"[ERROR] Failed to open {self.port}: {e}")
            self.finished.emit(False)
            return

        self.log_msg.emit(f"[INFO] File Size: {file_size} bytes, CRC32: 0x{file_crc:08X}")
        
        # 0. Check Existing
        self.log_msg.emit("0. Checking existing file on board...")
        packet = make_packet(CMD_FW_GET_FILE_INFO, b"")
        resp = self.send_and_wait(ser, packet, CMD_FW_GET_FILE_INFO, timeout=1.0)
        
        if resp and resp[0] == RESP_OK and len(resp) >= 81:
            board_magic = struct.unpack(">I", resp[1:5])[0]
            if board_magic == 0x534C4653:
                board_size = struct.unpack(">I", resp[5:9])[0]
                board_crc = struct.unpack(">I", resp[9:13])[0]
                board_ts = struct.unpack(">I", resp[13:17])[0]
                board_fn = resp[17:81].split(b'\x00')[0].decode('utf-8', errors='ignore')
                
                board_ic_type = "Unknown"
                board_version = "Unknown"
                if len(resp) >= 81 + 32 + 32:
                    board_ic_type = resp[81:113].split(b'\x00')[0].decode('utf-8', errors='ignore')
                    board_version = resp[113:145].split(b'\x00')[0].decode('utf-8', errors='ignore')
                
                self.log_msg.emit(f"   -> Board has: {board_fn} ({board_size} bytes, CRC:0x{board_crc:08X})")
                self.log_msg.emit(f"      [IC: {board_ic_type} | Ver: {board_version}]")
                if board_size == file_size and board_crc == file_crc and board_ts == file_timestamp and board_fn == filename_str:
                    if board_ic_type == ic_type_str and board_version == version_str:
                        self.log_msg.emit("   [SUCCESS] Identical file already exists on board. Skipping upload!")
                        ser.close()
                        self.progress_updated.emit(100)
                        self.finished.emit(True)
                        return
                    else:
                        self.log_msg.emit("   [INFO] Metadata differs. Forcing re-upload...")
            else:
                self.log_msg.emit("   -> No valid SLFS file found on board.")
        else:
            self.log_msg.emit("   -> Failed to query board file info or none exists.")

        if not self.is_running:
            ser.close()
            self.finished.emit(False)
            return

        # 1. Start Upload
        self.log_msg.emit("1. Sending FW_UPLOAD_START...")
        payload = struct.pack(">I", file_size)
        packet = make_packet(CMD_FW_UPLOAD_START, payload)
        resp = self.send_and_wait(ser, packet, CMD_FW_UPLOAD_START, timeout=4.0)
        
        if not resp or resp[0] != RESP_OK:
            self.log_msg.emit("[ERROR] Failed to start upload (Flash Erase timeout/error).")
            ser.close()
            self.finished.emit(False)
            return
            
        self.log_msg.emit("   -> Flash Erase and Start OK")
        
        # 2. Upload Data in Chunks
        chunk_size = 256
        offset = 0
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        chunk_idx = 1
        
        self.log_msg.emit("2. Uploading Data...")
        while offset < file_size:
            if not self.is_running:
                break
                
            remain = file_size - offset
            length = min(chunk_size, remain)
            chunk = file_data[offset:offset+length]
            
            payload = struct.pack(">I H", offset, length) + chunk
            packet = make_packet(CMD_FW_UPLOAD_DATA, payload)
            
            resp = self.send_and_wait(ser, packet, CMD_FW_UPLOAD_DATA, timeout=1.0)
            if not resp or resp[0] != RESP_OK:
                self.log_msg.emit(f"[ERROR] Failed at chunk {chunk_idx}/{total_chunks} (Offset: {offset}).")
                ser.close()
                self.finished.emit(False)
                return
                
            progress = int((offset + length) / file_size * 100)
            self.progress_updated.emit(progress)
            
            offset += length
            chunk_idx += 1

        if not self.is_running:
            ser.close()
            self.finished.emit(False)
            return
            
        self.log_msg.emit("   -> Data Upload Complete")
        
        # 3. End Upload & Verify
        self.log_msg.emit("3. Sending FW_UPLOAD_END (CRC Check)...")
        fn_bytes = filename_str.encode('utf-8').ljust(64, b'\x00')
        ic_bytes = ic_type_str.encode('utf-8').ljust(32, b'\x00')
        ver_bytes = version_str.encode('utf-8').ljust(32, b'\x00')
        
        payload = struct.pack(">I I", file_crc, file_timestamp) + fn_bytes + ic_bytes + ver_bytes
        packet = make_packet(CMD_FW_UPLOAD_END, payload)
        resp = self.send_and_wait(ser, packet, CMD_FW_UPLOAD_END, timeout=2.0)
        
        if not resp or resp[0] != RESP_OK:
            self.log_msg.emit("[ERROR] Upload verification failed! CRC mismatch or write error.")
            ser.close()
            self.finished.emit(False)
            return
            
        self.log_msg.emit("[SUCCESS] Verification OK! SLFS file successfully stored in RP2040 Flash.")
        ser.close()
        self.finished.emit(True)
        
    def stop(self):
        self.is_running = False
        self.log_msg.emit("[INFO] Stop requested...")
