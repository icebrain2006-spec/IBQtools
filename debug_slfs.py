import serial
import struct
import time

PROTOCOL_STX = 0x02
PROTOCOL_ETX = 0x03
CMD_FW_GET_FILE_INFO = 0x35

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
    stx_idx = rx_data.find(PROTOCOL_STX)
    if stx_idx == -1:
        return None, "No STX"
    rx_data = rx_data[stx_idx:]
    if len(rx_data) < 7:
        return None, "Too short"
    length = struct.unpack(">H", rx_data[1:3])[0]
    expected = length + 6
    if len(rx_data) < expected:
        return None, f"Incomplete: {len(rx_data)} < {expected}"
    if rx_data[expected-1] != PROTOCOL_ETX:
        return None, "No ETX"
    cmd = rx_data[3]
    payload = rx_data[4:expected-3]
    crc_rx = struct.unpack(">H", rx_data[expected-3:expected-1])[0]
    crc_calc = crc16_calculate(bytes([cmd]) + payload)
    if crc_calc != crc_rx:
        return None, "CRC mismatch"
    return cmd, payload

# Use the port from the screenshot (COM6)
try:
    with serial.Serial("COM6", 115200, timeout=1.0) as ser:
        packet = make_packet(CMD_FW_GET_FILE_INFO, b'')
        ser.write(packet)
        rx = ser.read(512)
        print(f"Read {len(rx)} bytes: {rx.hex()}")
        res = parse_response(rx)
        print("Parse result:", res)
except Exception as e:
    print("Error:", e)
