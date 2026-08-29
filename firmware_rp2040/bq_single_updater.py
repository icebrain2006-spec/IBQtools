import argparse
import serial
import struct
import time
import sys
import os

PROTOCOL_STX = 0x02
PROTOCOL_ETX = 0x03

CMD_FW_UPDATE_RUN    = 0x40
CMD_FW_UPDATE_STATUS = 0x41
CMD_FW_UPDATE_STOP   = 0x42
RESP_OK = 0x00

UPDATER_STATE_IDLE = 0
UPDATER_STATE_RUNNING = 1
UPDATER_STATE_DELAYING = 2
UPDATER_STATE_ERROR = 3
UPDATER_STATE_DONE = 4

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
    if len(rx_data) < 7:
        return None, "Response too short"
    if rx_data[0] != PROTOCOL_STX or rx_data[-1] != PROTOCOL_ETX:
        return None, "Invalid frame boundary"
    
    length = struct.unpack(">H", rx_data[1:3])[0]
    cmd = rx_data[3]
    payload = rx_data[4:-3]
    crc_rx = struct.unpack(">H", rx_data[-3:-1])[0]
    
    crc_data = bytes([cmd]) + payload
    crc_calc = crc16_calculate(crc_data)
    if crc_calc != crc_rx:
        return None, f"CRC mismatch (rx:{crc_rx:#x} calc:{crc_calc:#x})"
    
    return payload, None

def send_and_wait(ser, packet, expected_cmd, timeout=1.0):
    ser.reset_input_buffer()
    ser.write(packet)
    
    start_time = time.time()
    rx_buf = bytearray()
    
    while time.time() - start_time < timeout:
        if ser.in_waiting > 0:
            rx_buf.extend(ser.read(ser.in_waiting))
            if len(rx_buf) >= 7 and rx_buf[0] == PROTOCOL_STX and rx_buf[-1] == PROTOCOL_ETX:
                payload, err = parse_response(rx_buf)
                if err:
                    return None
                return payload
        time.sleep(0.01)
    return None

def run_updater(port_name, channel):
    print(f"Connecting to RP2040 on {port_name}...")
    try:
        ser = serial.Serial(port_name, 115200, timeout=1.0)
    except Exception as e:
        print(f"Error opening serial port: {e}")
        return False
        
    print(f"Starting SLFS Firmware Update on Channel {channel}...")
    channel_mask = 1 << (channel - 1)
    
    # 1. Send START Command
    packet = make_packet(CMD_FW_UPDATE_RUN, bytes([channel_mask]))
    resp = send_and_wait(ser, packet, CMD_FW_UPDATE_RUN, timeout=1.0)
    
    if not resp or resp[0] != RESP_OK:
        print(f"Failed to start updater. Is there a valid SLFS file uploaded? Resp: {resp}")
        ser.close()
        return False
        
    print("Updater started on RP2040. Monitoring progress...\n")
    
    # 2. Monitor Progress
    status_packet = make_packet(CMD_FW_UPDATE_STATUS, b"")
    
    last_line = -1
    last_line_time = time.time()
    
    while True:
        resp = send_and_wait(ser, status_packet, CMD_FW_UPDATE_STATUS, timeout=1.0)
        if not resp or resp[0] != RESP_OK:
            print("\n[ERROR] Lost communication with RP2040!")
            break
            
        state = resp[1]
        current_line = struct.unpack(">I", resp[2:6])[0]
        total_lines = struct.unpack(">I", resp[6:10])[0]
        active_channels = resp[10]
        error_channels = resp[11]
        error_code = struct.unpack(">i", resp[12:16])[0]
        
        if total_lines > 0:
            progress = (current_line / total_lines) * 100
        else:
            progress = 0
            
        # Draw progress
        state_str = "RUNNING "
        if state == UPDATER_STATE_DELAYING:
            state_str = "DELAYING"
        elif state == UPDATER_STATE_ERROR:
            state_str = "ERROR   "
        elif state == UPDATER_STATE_DONE:
            state_str = "DONE    "
            
        sys.stdout.write(f"\r[{state_str}] Progress: {progress:5.1f}% [{current_line}/{total_lines}] ErrCh: 0x{error_channels:02X}")
        sys.stdout.flush()
        
        # Check Error State
        if state == UPDATER_STATE_ERROR or error_channels != 0:
            print(f"\n\n[CRITICAL ERROR] Updater reported an error! Code: {error_code}, Error Channels: 0x{error_channels:02X}")
            print("Sending STOP command...")
            ser.write(make_packet(CMD_FW_UPDATE_STOP, b""))
            break
            
        # Check Done State
        if state == UPDATER_STATE_DONE:
            print("\n\n[SUCCESS] SLFS file successfully applied to BQ40Z50!")
            break
            
        # Check Watchdog (Hang Detection)
        current_time = time.time()
        if state == UPDATER_STATE_RUNNING:
            if current_line != last_line:
                last_line = current_line
                last_line_time = current_time
            elif current_time - last_line_time > 1.0:
                print("\n\n[TIMEOUT] RP2040 hung while in RUNNING state! No line progress for > 1 second.")
                print("Sending STOP command to abort...")
                ser.write(make_packet(CMD_FW_UPDATE_STOP, b""))
                break
        elif state == UPDATER_STATE_DELAYING:
            # During an intended delay, we temporarily suspend the 1.0s watchdog by updating the last_line_time
            last_line_time = current_time
            
        time.sleep(0.05)
        
    ser.close()

def main():
    parser = argparse.ArgumentParser(description="Test BQ SLFS Updater via RP2040")
    parser.add_argument("-port", required=True, help="Serial port to connect (e.g., com7)")
    parser.add_argument("-ch", type=int, default=1, choices=range(1, 7), help="Channel number (1-6)")
    
    args = parser.parse_args()
    run_updater(args.port, args.ch)

if __name__ == "__main__":
    main()
