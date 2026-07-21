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

def read_channel(ser, ch):
    payload = bytes([ch, 0x0B, 0x09, 1, 2, 0, 0])
    packet = make_packet(CMD_SMBUS_CMD, payload)
    
    ser.reset_input_buffer()
    ser.write(packet)
    
    # Give firmware enough time to execute bit-banging I2C
    time.sleep(0.05) 
    
    rx_data = ser.read(128)
    
    if not rx_data:
        return None, "Timeout"
    
    cmd, resp_payload = parse_response(rx_data)
    if cmd is None:
        return None, f"Parse Error: {resp_payload}"
    elif cmd == CMD_SMBUS_CMD:
        status = resp_payload[0]
        if status == RESP_OK and len(resp_payload) >= 3:
            val = resp_payload[1] | (resp_payload[2] << 8)
            return val, "OK"
        else:
            detail = resp_payload[1] if len(resp_payload) > 1 else 0
            return None, f"FW Error {status:#x} (det: {detail:#x})"
    else:
        return None, f"Unexpected CMD: {cmd:#x}"

def run_test(port_name, iterations=100, delay_ms=500):
    print(f"Connecting to RP2040 on {port_name}...")
    try:
        ser = serial.Serial(port_name, 115200, timeout=1.5)
    except Exception as e:
        print(f"Error opening serial port {port_name}: {e}")
        return
        
    print("-" * 50)
    print(f"Starting Multi-Channel Voltage Read (CH1 & CH2, 0x09)")
    print(f"Iterations: {iterations}, Delay: {delay_ms}ms")
    print("-" * 50)
    
    success_ch1 = 0
    success_ch2 = 0
    fail_ch1 = 0
    fail_ch2 = 0
    
    for i in range(1, iterations + 1):
        # Read CH1
        val1, msg1 = read_channel(ser, 1)
        if val1 is not None:
            success_ch1 += 1
            str_ch1 = f"{val1} mV"
        else:
            fail_ch1 += 1
            str_ch1 = f"ERR ({msg1})"
            
        # Read CH2
        val2, msg2 = read_channel(ser, 2)
        if val2 is not None:
            success_ch2 += 1
            str_ch2 = f"{val2} mV"
        else:
            fail_ch2 += 1
            str_ch2 = f"ERR ({msg2})"
            
        print(f"[{i:03d}/{iterations}] CH1: {str_ch1:<15} | CH2: {str_ch2}")
                
        # Delay
        time.sleep(delay_ms / 1000.0)
            
    ser.close()
    
    print("-" * 50)
    print("Test Completed!")
    print(f"CH1 Reliability: {(success_ch1/iterations)*100:.1f}% ({success_ch1}/{iterations})")
    print(f"CH2 Reliability: {(success_ch2/iterations)*100:.1f}% ({success_ch2}/{iterations})")
    print("-" * 50)

def main():
    parser = argparse.ArgumentParser(description="Test Multi-Channel (CH1/CH2) SMBus 0x09 Read")
    parser.add_argument("-port", required=True, help="Serial port to connect (e.g., com7 or COM7)")
    
    args = parser.parse_args()
    run_test(args.port)

if __name__ == "__main__":
    main()
