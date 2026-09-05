import time
import struct
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from updater_thread import (
    make_packet, parse_response, RESP_OK, CMD_I2C_RAW,
    CMD_SMBUS_CMD, CMD_RELAY_SET, PROTOCOL_STX
)
from calibrators.utils import smbus_pec_calculate

class SMBusCommunicatorMixin:
    """Mixin class providing SMBus/I2C low-level communication and RP2040 relay control."""

    def _send_cmd(self, cmd: int, payload: bytes = b""):
        """Sends command packet to RP2040 and parses response packet."""
        if not hasattr(self, 'ser') or not self.ser or not self.ser.is_open:
            return None, None
        packet = make_packet(cmd, payload)
        self.ser.reset_input_buffer()
        self.ser.write(packet)
        rx = self._read_packet()
        return parse_response(rx)

    def _read_packet(self):
        """Reads raw bytes from serial until valid protocol STX packet is received."""
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

    def smbus_write_word(self, reg, val):
        """Writes 16-bit word to SMBus register."""
        payload = struct.pack('<BBBBBBH', self.ch, self.addr, reg, 0, 2, 0, val)
        cmd, resp = self._send_cmd(CMD_SMBUS_CMD, payload)
        return isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK

    def smbus_write_block_raw(self, cmd_reg, data_bytes, use_pec=True):
        """Writes raw block bytes with optional SMBus PEC checksum."""
        tx_data = bytearray([cmd_reg, len(data_bytes)]) + bytearray(data_bytes)
        if use_pec:
            pec_data = bytearray([(self.addr << 1)]) + tx_data
            pec = smbus_pec_calculate(pec_data)
            tx_data.append(pec)
            
        payload = bytes([self.ch, self.addr, len(tx_data), 0]) + tx_data
        cmd, resp = self._send_cmd(CMD_I2C_RAW, payload)
        return isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK

    def smbus_read_word(self, cmd_reg):
        """Reads 16-bit word from SMBus register."""
        payload = bytes([self.ch, self.addr, cmd_reg, 1, 2, 0, 0])
        cmd, resp = self._send_cmd(CMD_SMBUS_CMD, payload)
        if isinstance(resp, (bytes, bytearray)) and len(resp) > 0 and resp[0] == RESP_OK:
            return resp[1:3]
        return None

    def smbus_read_block(self, cmd_reg):
        """Reads block bytes from SMBus register with retry mechanism."""
        resp = None
        for attempt in range(10):
            if hasattr(self, '_running') and not self._running:
                return None
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
                if hasattr(self, '_log'):
                    self._log(f"    -> Comm Lost: 0x{err_code:02x}, Detail: {detail}")
            else:
                if hasattr(self, '_log'):
                    self._log(f"    -> Comm Lost: {resp}")
            if hasattr(self, 'clear_ch_signal'):
                self.clear_ch_signal.emit(self.ch)
        return None

    def read_mac_block(self, sub_cmd_bytes):
        """Writes sub-command bytes to 0x44 and reads back response block."""
        self.smbus_write_block_raw(0x44, sub_cmd_bytes)
        time.sleep(0.05)
        return self.smbus_read_block(0x44)

    def _set_relay(self, on: bool, mask: int = None):
        """Sets RP2040 channel relay state."""
        if mask is None:
            mask = (1 << (self.ch - 1)) if on else 0
        elif not on:
            mask = 0

        self._send_cmd(CMD_RELAY_SET, bytes([mask]))
        if hasattr(self, '_log'):
            self._log(f"    [Relay] {'ON' if on else 'OFF'} (mask: 0x{mask:02X})")
        time.sleep(0.1)

    def _exit_rom_mode(self):
        """Exits ROM bootloader mode to return BQ IC to normal firmware mode."""
        payload = bytes([self.ch, 0x0B, 1, 0, 0x08])
        self._send_cmd(CMD_I2C_RAW, payload)
        time.sleep(0.01)

    def _read_mfg_info(self):
        """Reads manufacture date (0x1B) and serial number (0x1C)."""
        serial_num = "Unknown"
        mfg_date = "Unknown"
        try:
            m_data = self.smbus_read_word(0x1B)
            if not m_data or len(m_data) < 2:
                self._exit_rom_mode()
                time.sleep(0.1)
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
            if hasattr(self, '_log'):
                self._log(f"Error reading Mfg Info: {e}")
        return serial_num, mfg_date

    def _find_header(self, data, header_bytes):
        """Locates header_bytes inside SMBus response data to prevent byte-shift errors."""
        if not data or len(data) < len(header_bytes):
            return -1
        return bytes(data).find(bytes(header_bytes))
