import time
import struct
import serial
from PySide6.QtCore import QThread, Signal

from gui.protocol import (
    make_packet, parse_response, get_fw_version, CMD_SMBUS_CMD, 
    CMD_I2C_RAW, PROTOCOL_STX, RESP_OK
)


class ScanWorker(QThread):
    """Background worker scanning available COM ports for RP2040 boards."""
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


class GlobalPreflightWorker(QThread):
    """Worker performing global pre-flight SMBus health check across multi-board setups."""
    finished_check = Signal(bool, object)  # (success, dict_of_errors {board_id: [channels]})
    log_msg = Signal(str)
    
    def __init__(self, board_configs, parent=None):
        super().__init__(parent)
        self.board_configs = board_configs
        self.is_running = True
        
    def _read_smbus_word(self, ser, ch: int, addr: int, reg: int) -> bool:
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
                            return bool(resp and resp[0] == RESP_OK)
                        buf = buf[stx_idx+expected_total:]
                        continue
        finally:
            ser.timeout = old_timeout
        return False

    def _read_sbd_info(self, ser, ch: int) -> bool:
        date_ok = self._read_smbus_word(ser, ch, 0x0B, 0x1B)
        serial_ok = self._read_smbus_word(ser, ch, 0x0B, 0x1C)
        return date_ok and serial_ok

    def _exit_rom_mode(self, ser, ch: int):
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
                    ser = serial.Serial(port, 115200, timeout=1.5)
                except Exception as e:
                    self.log_msg.emit(f"[ERROR] Global Check Failed: Cannot open {port} for Board {b_id}: {e}")
                    all_errors[b_id] = channels
                    continue
                
            ch_errors = []
            
            for ch in channels:
                if not self.is_running:
                    ser.close()
                    return
                self._exit_rom_mode(ser, ch)
                
            time.sleep(0.5)
            
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
                time.sleep(0.5)
                self.finished_check.emit(True, {})
