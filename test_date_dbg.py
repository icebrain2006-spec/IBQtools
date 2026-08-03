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

def parse_response(data):
    if not data: return None, None
    if len(data) < 6 or data[0] != 0x02:
        return None, None
    total_len = struct.unpack(">H", data[1:3])[0]
    cmd = data[3]
    payload = data[4: 4 + total_len - 1]
    return cmd, payload

def date_to_int(year, month, day):
    return day + (month * 32) + ((year - 1980) * 512)

def int_to_date(val):
    day = val & 0x1F
    month = (val >> 5) & 0x0F
    year = 1980 + (val >> 9)
    return f"{year}-{month:02d}-{day:02d}"

def test_date():
    ports = [p.device for p in serial.tools.list_ports.comports() if "USB" in str(p.hwid).upper()]
    if not ports:
        print("No ports found")
        return
        
    port = ports[0]
    print(f"Testing on {port}")
    
    ser = serial.Serial(port, 115200, timeout=1.0)
    
    reg = 0x1B
    
    found = False
    for ch in range(1, 4):
        for addr in [0x0B, 0x16]:
            print(f"--- Channel {ch}, Addr 0x{addr:02X} ---")
            payload_read = bytes([ch, addr, reg, 1, 2, 0, 0])
            pkt = make_packet(0x20, payload_read)
            ser.reset_input_buffer()
            ser.write(pkt)
            time.sleep(0.1)
            rx = ser.read(30)
            cmd, resp = parse_response(rx)
            if resp and resp[0] == 0:
                found = True
                val = resp[1] | (resp[2] << 8)
                print("Original Date:", int_to_date(val), f"({val})")
                
                # Write new date
                new_year, new_month, new_day = 2024, 3, 5
                print(f"Writing New Date: {new_year}-{new_month:02d}-{new_day:02d}")
                new_val = date_to_int(new_year, new_month, new_day)
                val_lo = new_val & 0xFF
                val_hi = (new_val >> 8) & 0xFF
                payload_write = bytes([ch, addr, reg, 0, 2, 0, val_lo, val_hi])
                pkt = make_packet(0x20, payload_write)
                ser.reset_input_buffer()
                ser.write(pkt)
                time.sleep(0.1)
                rx = ser.read(30)
                cmd, wresp = parse_response(rx)
                if wresp and wresp[0] == 0:
                    print("Write OK")
                else:
                    print(f"Write FAILED: {wresp.hex() if wresp else 'None'}")
                    
                # Read back
                ser.reset_input_buffer()
                ser.write(make_packet(0x20, payload_read))
                time.sleep(0.1)
                rx = ser.read(30)
                cmd, rresp = parse_response(rx)
                if rresp and rresp[0] == 0:
                    val = rresp[1] | (rresp[2] << 8)
                    print("Read Back Date:", int_to_date(val), f"({val})")
                else:
                    print("Failed to read back date")
                break
            else:
                print(f"Failed to read date (Err: {resp.hex() if resp else 'None'})")
        if found:
            break

    ser.close()

if __name__ == "__main__":
    test_date()
