import time
import struct
import serial

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
CMD_SMBUS_POLL_BLOCK = 0x23
CMD_GET_VERSION      = 0x01
CMD_RELAY_SET        = 0x10
CMD_SET_LED_STATE    = 0x50
RESP_OK = 0x00

UPDATER_STATE_IDLE = 0
UPDATER_STATE_RUNNING = 1
UPDATER_STATE_DELAYING = 2
UPDATER_STATE_ERROR = 3
UPDATER_STATE_DONE = 4


def crc16_calculate(data: bytes) -> int:
    """Calculates CRC16-Modbus / CCITT for serial framing."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def make_packet(cmd: int, payload: bytes) -> bytes:
    """Constructs a binary serial packet: STX | LEN | CMD | PAYLOAD | CRC | ETX."""
    total_len = 1 + len(payload)
    header = struct.pack(">B H B", PROTOCOL_STX, total_len, cmd)
    crc_data = bytes([cmd]) + payload
    crc = crc16_calculate(crc_data)
    footer = struct.pack(">H B", crc, PROTOCOL_ETX)
    return header + payload + footer


def parse_response(rx_data: bytes):
    """Parses and validates serial response packet."""
    stx_idx = rx_data.find(PROTOCOL_STX)
    if stx_idx == -1:
        return None, "No STX found"
        
    rx_data = rx_data[stx_idx:]
    if len(rx_data) < 7:
        return None, "Response too short"
        
    length = struct.unpack(">H", rx_data[1:3])[0]
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


def get_file_info(port: str):
    """Queries RP2040 board for loaded SLFS file metadata."""
    packet = make_packet(CMD_FW_GET_FILE_INFO, b'')
    ser = None
    for _ in range(5):
        try:
            ser = serial.Serial(port, 115200, timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    if ser is None:
        return None

    try:
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
    finally:
        try:
            ser.close()
        except Exception:
            pass
    return None


def get_fw_version(port: str):
    """Queries RP2040 firmware version string."""
    packet = make_packet(CMD_GET_VERSION, b'')
    ser = None
    for _ in range(5):
        try:
            ser = serial.Serial(port, 115200, timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    if ser is None:
        return None

    try:
        ser.write(packet)
        rx = ser.read(128)
        if not rx or len(rx) < 7:
            return None
        cmd, resp = parse_response(rx)
        if cmd == CMD_GET_VERSION and resp[0] == RESP_OK:
            return resp[1:].split(b'\x00')[0].decode('ascii', errors='ignore')
    except Exception:
        pass
    finally:
        try:
            ser.close()
        except Exception:
            pass
    return None
