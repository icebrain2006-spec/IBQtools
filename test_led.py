import serial
import serial.tools.list_ports
import struct
import time

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
    header = struct.pack(">B H B", 0x02, total_len, cmd)
    crc_data = bytes([cmd]) + payload
    crc = crc16_calculate(crc_data)
    footer = struct.pack(">H B", crc, 0x03)
    return header + payload + footer

def test_led():
    ports = [p.device for p in serial.tools.list_ports.comports() if "USB" in str(p.hwid).upper()]
    if not ports:
        print("No ports found")
        return
        
    port = ports[0]
    print(f"Testing on {port}")
    
    # Send Cyan (0x0000FFFF), Blink (1), Duration (5)
    color = 0x0000FFFF
    mode = 1
    dur = 5
    payload = struct.pack(">I B B", color, mode, dur)
    print("Payload length:", len(payload))
    packet = make_packet(0x50, payload)
    print("Packet:", packet.hex())
    
    ser = serial.Serial(port, 115200, timeout=1.0)
    ser.write(packet)
    print("Sent, waiting for response...")
    rx = ser.read(10)
    print("Rx:", rx.hex())
    ser.close()

if __name__ == "__main__":
    test_led()
