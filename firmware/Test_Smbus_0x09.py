import argparse
import serial
import struct
import time
import sys

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

def run_test(port_name, ch=1, iterations=100, delay_ms=500):
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
    print("-" * 50)
    print(f"Starting {iterations} iterations of Voltage Read (CH{ch}, 0x09) with {delay_ms}ms delay...")
    print("-" * 50)
        
    # CMD_SMBUS_CMD Payload for CH(ch) Voltage Read
    payload = bytes([ch, 0x0B, 0x09, 1, 2, 0, 0])
    packet = make_packet(CMD_SMBUS_CMD, payload)
    
    success_count = 0
    fail_count = 0
    
    for i in range(1, iterations + 1):
        ser.reset_input_buffer()
        ser.write(packet)
        
        # Give firmware enough time to execute bit-banging I2C
        time.sleep(0.1) 
        
        rx_data = ser.read(128)
        
        if not rx_data:
            print(f"[{i:03d}/{iterations}] Error: No response (Timeout)")
            fail_count += 1
        else:
            cmd, resp_payload = parse_response(rx_data)
            if cmd is None:
                print(f"[{i:03d}/{iterations}] Failed parsing: {resp_payload}")
                fail_count += 1
            elif cmd == CMD_SMBUS_CMD:
                status = resp_payload[0]
                if status == RESP_OK and len(resp_payload) >= 3:
                    val = resp_payload[1] | (resp_payload[2] << 8)
                    print(f"[{i:03d}/{iterations}] SUCCESS: {val} mV ({val/1000:.3f} V)")
                    success_count += 1
                else:
                    detail = resp_payload[1] if len(resp_payload) > 1 else 0
                    print(f"[{i:03d}/{iterations}] Firmware Error: status={status:#x}, detail={detail:#x}")
                    fail_count += 1
            else:
                print(f"[{i:03d}/{iterations}] Unexpected command: {cmd:#x}")
                fail_count += 1
                
        # Wait for the remaining delay time (delay_ms minus the 0.1s we already waited)
        remaining_delay = (delay_ms / 1000.0) - 0.1
        if remaining_delay > 0 and i < iterations:
            time.sleep(remaining_delay)
            
    ser.close()
    
    print("-" * 50)
    print("Test Completed!")
    print(f"Total Attempts: {iterations}")
    print(f"Successful:     {success_count}")
    print(f"Failed:         {fail_count}")
    print(f"Reliability:    {(success_count/iterations)*100:.1f}%")
    print("-" * 50)

def main():
    parser = argparse.ArgumentParser(description="Test SMBus 0x09 Read Command via RP2040 Serial Bridge")
    parser.add_argument("-port", required=True, help="Serial port to connect (e.g., com7 or COM7)")
    parser.add_argument("-ch", type=int, default=1, choices=range(1, 7), help="Channel number (1-6)")
    
    args = parser.parse_args()
    run_test(args.port, args.ch)

if __name__ == "__main__":
    main()
