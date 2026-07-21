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
    if len(rx_data) < 7:
        return None, "Response too short"
    if rx_data[0] != PROTOCOL_STX or rx_data[-1] != PROTOCOL_ETX:
        return None, "Invalid frame boundary"
    cmd = rx_data[3]
    payload = rx_data[4:-3]
    crc_rx = struct.unpack(">H", rx_data[-3:-1])[0]
    crc_calc = crc16_calculate(bytes([cmd]) + payload)
    if crc_calc != crc_rx:
        return None, "CRC mismatch"
    return cmd, payload

class UpdaterWorker(QThread):
    log_msg = Signal(str)
    progress_updated = Signal(int, int) # (ch_idx, pct)
    status_updated = Signal(int, str)   # (ch_idx, text)
    finished = Signal(bool)
    
    def __init__(self, port, channels, loop_count=1, parent=None):
        super().__init__(parent)
        self.port = port
        self.channels = channels
        self.loop_count = loop_count
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
                    time.sleep(0.5)
                    continue
                    
                state, current_line, total_lines, active, err_mask, err_code = status
                
                pct = int((current_line / total_lines * 100)) if total_lines > 0 else 0
                self.log_msg.emit(f"Progress: {pct}% [{current_line}/{total_lines}] | ErrMask: {err_mask:#04x}")
                
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
                    self.log_msg.emit("[SUCCESS] Firmware update completed.")
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
