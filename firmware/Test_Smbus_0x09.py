import argparse
import serial
import struct
import time

PROTOCOL_STX = 0x02
PROTOCOL_ETX = 0x03
CMD_GET_VERSION = 0x01
CMD_SMBUS_CMD = 0x20
RESP_OK = 0x00

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
    # total_len: cmd(1) + payload
    total_len = 1 + len(payload)
    
    header = struct.pack(">B H B", PROTOCOL_STX, total_len, cmd)
    crc_data = bytes([cmd]) + payload
    crc = crc16_calculate(crc_data)
    footer = struct.pack(">H B", crc, PROTOCOL_ETX)
    
    return header + payload + footer

def parse_response(rx_data):
    if len(rx_data) < 7: # STX(1) + LEN(2) + CMD(1) + PAYLOAD(min 1) + CRC(2) + ETX(1)
        return None, "Response too short"
    
    if rx_data[0] != PROTOCOL_STX or rx_data[-1] != PROTOCOL_ETX:
        return None, "Invalid frame boundary (missing STX/ETX)"
    
    length = struct.unpack(">H", rx_data[1:3])[0]
    cmd = rx_data[3]
    payload = rx_data[4:-3]
    crc_rx = struct.unpack(">H", rx_data[-3:-1])[0]
    
    crc_data = bytes([cmd]) + payload
    crc_calc = crc16_calculate(crc_data)
    if crc_calc != crc_rx:
        return None, f"CRC mismatch: rx={crc_rx:#x}, calc={crc_calc:#x}"
        
    return cmd, payload

def run_test(port_name):
    print(f"Connecting to RP2040 on {port_name}...")
    try:
        ser = serial.Serial(port_name, 115200, timeout=1.5)
    except Exception as e:
        print(f"Error opening serial port {port_name}: {e}")
        return
        
    # 1. Query Firmware Version
    ver_packet = make_packet(CMD_GET_VERSION, b"")
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(ver_packet)
    time.sleep(0.05)
    rx_ver = ser.read(64)
    firmware_ver = "Unknown"
    if rx_ver:
        cmd, resp_payload = parse_response(rx_ver)
        if cmd == CMD_GET_VERSION and resp_payload[0] == RESP_OK:
            firmware_ver = resp_payload[1:].decode("utf-8", errors="ignore")
        else:
            firmware_ver = "Legacy or Error"
    print(f"Firmware Version on Board: {firmware_ver}")
    print("-" * 40)
        
    # CMD_SMBUS_CMD Payload:
    # ch=1 (1 byte)
    # addr=0x0B (1 byte, bq40z50)
    # cmd_reg=0x09 (1 byte, Voltage)
    # rw=1 (1 byte, Read)
    # len=2 (1 byte, Read 2 bytes)
    # use_pec=0 (1 byte, No PEC)
    # data=0 (1 byte dummy for padding)
    payload = bytes([1, 0x0B, 0x09, 1, 2, 0, 0])
    packet = make_packet(CMD_SMBUS_CMD, payload)
    
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    print(f"Sending read request packet: {packet.hex().upper()}")
    ser.write(packet)
    
    time.sleep(0.1)
    rx_data = ser.read(128)
    ser.close()
    
    if not rx_data:
        print("Error: No response received from RP2040 (Timeout).")
        return
        
    print(f"Received raw data: {rx_data.hex().upper()}")
    cmd, resp_payload = parse_response(rx_data)
    if cmd is None:
        print(f"Failed parsing: {resp_payload}")
        return
        
    if cmd == CMD_SMBUS_CMD:
        status = resp_payload[0]
        if status == RESP_OK:
            if len(resp_payload) >= 3:
                # Value is in Little Endian format
                val = resp_payload[1] | (resp_payload[2] << 8)
                print("\n" + "="*40)
                print(" SMBus Read SUCCESS")
                print("="*40)
                print(f"Channel:     CH1")
                print(f"Device Addr: 0x0B")
                print(f"Register:    0x09 (Voltage)")
                print(f"Read Value:  {val} mV ({val/1000:.3f} V)")
                print("="*40)
            else:
                print(f"Error: Invalid payload size: {resp_payload.hex().upper()}")
        else:
            detail = resp_payload[1] if len(resp_payload) > 1 else 0
            print(f"RP2040 error response status: {status:#x}, detail={detail:#x}")
    else:
        print(f"Unexpected command response: {cmd:#x}")

def main():
    parser = argparse.ArgumentParser(description="Test SMBus 0x09 Read Command via RP2040 Serial Bridge")
    parser.add_argument("-port", required=True, help="Serial port to connect (e.g., com7 or COM7)")
    
    args = parser.parse_args()
    run_test(args.port)

if __name__ == "__main__":
    main()
