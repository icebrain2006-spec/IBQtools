import time
import struct
import serial
from PySide6.QtCore import QThread, Signal

from gui.protocol import (
    make_packet, parse_response, CMD_SET_LED_STATE, CMD_SMBUS_CMD, 
    PROTOCOL_STX, RESP_OK
)


def set_led_state(port: str, color_hex: int, mode: int, duration_sec: int) -> bool:
    """Sends LED color state configuration packet to RP2040 board."""
    payload = struct.pack(">I B B", color_hex, mode, duration_sec)
    packet = make_packet(CMD_SET_LED_STATE, payload)
    
    ser = None
    for _ in range(10):
        try:
            ser = serial.Serial(port, 115200, timeout=0.2)
            break
        except Exception:
            time.sleep(0.1)
            
    if ser is None:
        return False
        
    try:
        ser.write(packet)
        ser.timeout = 0.2
        _ = ser.read(10)
    except Exception:
        pass
    finally:
        if ser:
            ser.close()
    return True


class DisconnectionMonitor(QThread):
    """Monitors channel disconnection status by polling SMBus registers."""

    channel_disconnected = Signal(int)
    log_msg = Signal(str)

    def __init__(self, port: str, channels, parent=None):
        super().__init__(parent)
        self.port = port
        self.channels_to_monitor = list(channels)
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
                            return bool(resp and resp[0] == RESP_OK)
                        buf = buf[stx_idx+expected_total:]
                        continue
        finally:
            ser.timeout = old_timeout
        return False

    def run(self):
        ser = None
        for _ in range(5):
            try:
                ser = serial.Serial(self.port, 115200, timeout=0.5)
                break
            except Exception:
                time.sleep(0.1)

        if ser is None:
            return

        while self.is_running and self.channels_to_monitor:
            for ch in list(self.channels_to_monitor):
                if not self.is_running:
                    break

                ok = self._read_smbus_word(ser, ch, 0x0B, 0x1C)
                if not ok:
                    time.sleep(0.05)
                    ok = self._read_smbus_word(ser, ch, 0x0B, 0x1C)
                if not ok:
                    self.log_msg.emit(f"[MON] Disconnection detected on CH {ch}")
                    self.channel_disconnected.emit(ch)
                    self.channels_to_monitor.remove(ch)

            time.sleep(0.5)

        if ser:
            ser.close()

    def stop(self):
        self.is_running = False
