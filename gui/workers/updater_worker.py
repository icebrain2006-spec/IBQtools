import time
import struct
import serial
from PySide6.QtCore import QThread, Signal

from gui.protocol import (
    make_packet, parse_response, PROTOCOL_STX, RESP_OK,
    CMD_FW_UPDATE_RUN, CMD_FW_UPDATE_STATUS, CMD_FW_UPDATE_STOP, 
    CMD_SMBUS_CMD, CMD_I2C_RAW,
    UPDATER_STATE_DONE, UPDATER_STATE_ERROR, UPDATER_STATE_DELAYING
)


class UpdaterWorker(QThread):
    """Background worker for executing multi-board BQ40Z50 firmware flashing and SMBus verification."""

    log_msg = Signal(str)
    progress_updated = Signal(int, int)  # (ch_idx, pct)
    status_updated = Signal(int, str)    # (ch_idx, text)
    verify_updated = Signal(int, str, int)  # (ch_idx, date_str, sn_int)
    finished = Signal(bool)
    
    def __init__(self, port: str, channels: list, loop_count: int = 1, get_expected_cb=None, skip_preflight: bool = False, parent=None):
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
        self.log_msg.emit(f"    [RUN TX({len(packet)}b)] {packet.hex(' ')}")
        time.sleep(0.1)
        rx = self.ser.read(64)
        if not rx:
            self.log_msg.emit("    [RUN RX] Timeout (0 bytes)")
            return False, "Timeout"
        self.log_msg.emit(f"    [RUN RX({len(rx)}b)] {rx.hex(' ')}")
        cmd, payload = parse_response(rx)
        if cmd == CMD_FW_UPDATE_RUN and payload and payload[0] == RESP_OK:
            return True, "OK"
        err_code = payload[0] if payload else -1
        return False, f"Failed or Busy: {err_code:#x}"

    def _check_status(self):
        packet = make_packet(CMD_FW_UPDATE_STATUS, b"")
        self.ser.write(packet)
        
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
                        pkt_chunk = buf[stx_idx:stx_idx+expected_total]
                        cmd, payload = parse_response(pkt_chunk)
                        if cmd == CMD_FW_UPDATE_STATUS and isinstance(payload, (bytes, bytearray)) and len(payload) >= 13 and payload[0] == RESP_OK:
                            state = payload[1]
                            current_line = struct.unpack(">I", payload[2:6])[0]
                            total_lines = struct.unpack(">I", payload[6:10])[0]
                            active_channels = payload[10]
                            error_channels = payload[11]
                            error_code = struct.unpack(">i", payload[12:16])[0] if len(payload) >= 16 else struct.unpack(">b", bytes([payload[12]]))[0]
                            self.log_msg.emit(f"    [STATUS OK] state={state}, line={current_line}/{total_lines}, active={active_channels:#04x}, err_mask={error_channels:#04x}, err_code={error_code}")
                            return (state, current_line, total_lines, active_channels, error_channels, error_code)
                        else:
                            self.log_msg.emit(f"    [STATUS PARSE MISMATCH] cmd={cmd}, payload={payload.hex() if isinstance(payload, (bytes, bytearray)) else payload}")
                        buf = buf[stx_idx+expected_total:]
        finally:
            self.ser.timeout = old_timeout
        if buf:
            self.log_msg.emit(f"    [STATUS TIMEOUT] buf({len(buf)}b)={buf.hex(' ')}")
        else:
            self.log_msg.emit("    [STATUS TIMEOUT] No data received from RP2040")
        return None

    def _stop_updater(self):
        if self.ser and self.ser.is_open:
            packet = make_packet(CMD_FW_UPDATE_STOP, b"")
            self.ser.reset_input_buffer()
            self.ser.write(packet)
            time.sleep(0.1)

    def _read_smbus_word(self, ch: int, addr: int, reg: int):
        payload = bytes([ch, addr, reg, 1, 2, 0, 0])
        packet = make_packet(CMD_SMBUS_CMD, payload)
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        
        start_time = time.time()
        buf = b""
        raw_rx = b""
        old_timeout = self.ser.timeout
        self.ser.timeout = 0.05
        
        try:
            while time.time() - start_time < 1.0:
                rx = self.ser.read(128)
                if rx: 
                    raw_rx += rx
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
                            if resp and resp[0] == RESP_OK:
                                return resp[1] | (resp[2] << 8)
                            else:
                                self.log_msg.emit(f"[DEBUG] SMBus Error Resp: {resp.hex() if resp else 'None'}")
                                return None
                                
                        buf = buf[stx_idx+expected_total:]
                        continue
        finally:
            self.ser.timeout = old_timeout
                    
        self.log_msg.emit(f"[DEBUG] _read_smbus_word Timeout. Raw RX: {raw_rx.hex()}")
        return None
        
    def _write_smbus_word(self, ch: int, addr: int, reg: int, word_val: int) -> bool:
        val_lo = word_val & 0xFF
        val_hi = (word_val >> 8) & 0xFF
        payload = bytes([ch, addr, reg, 0, 2, 1, val_lo, val_hi])
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
                
                stx_idx = buf.find(PROTOCOL_STX)
                if stx_idx != -1 and len(buf) >= stx_idx + 7:
                    length = struct.unpack(">H", buf[stx_idx+1:stx_idx+3])[0]
                    expected_total = length + 6
                    if len(buf) >= stx_idx + expected_total:
                        pkt_chunk = buf[stx_idx:stx_idx+expected_total]
                        cmd, resp = parse_response(pkt_chunk)
                        
                        if cmd == CMD_SMBUS_CMD:
                            self.log_msg.emit(f"    [RAW IO] TX({len(packet)}b): {packet.hex(' ')} | RX({len(pkt_chunk)}b): {pkt_chunk.hex(' ')}")
                            return bool(resp and resp[0] == RESP_OK and len(resp) >= 2)
                                
                        buf = buf[stx_idx+expected_total:]
                        continue
        finally:
            self.ser.timeout = old_timeout
            
        return False

    def _read_sbd_info(self, ch: int):
        date_val = self._read_smbus_word(ch, 0x0B, 0x1B)
        serial_val = self._read_smbus_word(ch, 0x0B, 0x1C)
        
        if date_val is None or serial_val is None:
            return None, None
            
        year = (date_val >> 9) + 1980
        month = (date_val >> 5) & 0x0F
        day = date_val & 0x1F
        
        return f"{year}-{month:02d}-{day:02d}", serial_val

    def _exit_rom_mode(self, ch: int):
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
                for ch in self.channels:
                    if not self.is_running:
                        break
                    self._exit_rom_mode(ch)
                    
                if not self.is_running:
                    break
                    
                time.sleep(0.5)
                
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
                    for ch in self.channels:
                        if ch not in ch_errors:
                            self.status_updated.emit(ch, "Aborted")
                    overall_success = False
                    break
            
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
                    if hang_counter > 10:
                        self.log_msg.emit("[ERROR] RP2040 not responding to status poll (Hardware/I2C Hang).")
                        overall_success = False
                        break
                    time.sleep(0.5)
                    continue
                    
                hang_counter = 0
                state, current_line, total_lines, active, err_mask, err_code = status
                pct = int((current_line / total_lines * 100)) if total_lines > 0 else 0
                
                for ch in self.channels:
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
                    
                time.sleep(0.1)
                
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
                            fmt = "DEC"
                            should_toggle_led = False
                            if self.get_expected_cb:
                                res = self.get_expected_cb(ch)
                                exp_date, exp_sn_int, fmt, should_write_sn, should_write_date = res[0], res[1], res[2], res[3], res[4]
                                should_toggle_led = res[5] if len(res) >= 6 else False
                                
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
                                    time.sleep(0.1)
                                    
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

                            if should_toggle_led:
                                self.log_msg.emit(f"[CH {ch}] Executing LED Toggle command (0x002B)...")
                                ok_led = self._write_smbus_word(ch, 0x0B, 0x00, 0x002B)
                                if ok_led:
                                    self.log_msg.emit(f"[CH {ch}] LED Toggle SUCCESS (0x002B)")
                                else:
                                    self.log_msg.emit(f"[CH {ch}] LED Toggle FAILED!")
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
    """Worker reading SN & Manufacture Date via SMBus without flashing firmware."""

    def __init__(self, port: str, channels: list, fmt: str = "DEC", toggle_led: bool = False, parent=None):
        super().__init__(port, channels, loop_count=1, get_expected_cb=None, parent=parent)
        self.fmt = fmt
        self.toggle_led = toggle_led
        
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

            if self.toggle_led:
                self.log_msg.emit(f"[CH {ch}] Executing LED Toggle command (0x002B)...")
                ok_led = self._write_smbus_word(ch, 0x0B, 0x00, 0x002B)
                if ok_led:
                    self.log_msg.emit(f"[CH {ch}] LED Toggle SUCCESS (0x002B)")
                else:
                    self.log_msg.emit(f"[CH {ch}] LED Toggle FAILED!")
                
        if self.ser:
            self.ser.close()
            
        self.finished.emit(True)
