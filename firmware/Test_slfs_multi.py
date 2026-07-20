import argparse
import serial
import struct
import time
import sys

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
    cmd = rx_data[3]
    payload = rx_data[4:-3]
    crc_rx = struct.unpack(">H", rx_data[-3:-1])[0]
    crc_calc = crc16_calculate(bytes([cmd]) + payload)
    if crc_calc != crc_rx:
        return None, "CRC mismatch"
    return cmd, payload

def start_updater_multi(ser, channels):
    ch_mask = 0
    for ch in channels:
        ch_mask |= (1 << (ch - 1))
    
    packet = make_packet(CMD_FW_UPDATE_RUN, bytes([ch_mask]))
    ser.reset_input_buffer()
    ser.write(packet)
    time.sleep(0.1)
    rx = ser.read(64)
    if not rx:
        return False, "Timeout"
    cmd, payload = parse_response(rx)
    if cmd == CMD_FW_UPDATE_RUN and payload[0] == RESP_OK:
        return True, "OK"
    return False, f"Failed or Busy: {payload[0]:#x}"

def check_status(ser):
    packet = make_packet(CMD_FW_UPDATE_STATUS, b"")
    ser.reset_input_buffer()
    ser.write(packet)
    
    # Read STX + LEN + CMD (4 bytes)
    header = ser.read(4)
    if len(header) < 4 or header[0] != PROTOCOL_STX:
        return None
        
    length = struct.unpack(">H", header[1:3])[0]
    # We need to read (length - 1) bytes for payload, plus CRC(2) and ETX(1)
    # length includes CMD(1) + PAYLOAD
    payload_len = length - 1
    remaining_bytes = payload_len + 3 # payload + CRC(2) + ETX(1)
    
    rest = ser.read(remaining_bytes)
    if len(rest) < remaining_bytes:
        return None
        
    rx = header + rest
    res = parse_response(rx)
    if res[0] is None:
        return None
        
    cmd, payload = res
    if cmd == CMD_FW_UPDATE_STATUS and payload[0] == RESP_OK:
        state = payload[1]
        current_line = struct.unpack(">I", payload[2:6])[0]
        total_lines = struct.unpack(">I", payload[6:10])[0]
        active_channels = payload[10]
        error_channels = payload[11]
        error_code = struct.unpack(">b", bytes([payload[12]]))[0] # signed byte
        return (state, current_line, total_lines, active_channels, error_channels, error_code)
    return None

def stop_updater(ser):
    packet = make_packet(CMD_FW_UPDATE_STOP, b"")
    ser.reset_input_buffer()
    ser.write(packet)
    time.sleep(0.1)

def format_channels(mask):
    chs = []
    for i in range(6):
        if mask & (1 << i):
            chs.append(f"CH{i+1}")
    return ",".join(chs) if chs else "None"

def run_monitor(port_name, channels):
    print(f"Connecting to RP2040 on {port_name}...")
    try:
        ser = serial.Serial(port_name, 115200, timeout=1.5)
    except Exception as e:
        print(f"Error opening serial port: {e}")
        return

    ch_str = ",".join([f"CH{ch}" for ch in channels])
    print(f"Starting SLFS Firmware Update simultaneously on: {ch_str}")
    
    ok, msg = start_updater_multi(ser, channels)
    if not ok:
        print(f"Failed to start updater: {msg}")
        ser.close()
        return
        
    print("Updater started on RP2040. Monitoring progress...\n")
    
    last_line = -1
    last_line_time = time.time()
    last_success_time = time.time()
    warning_printed = False
    hang_counter = 0
    
    while True:
        status = check_status(ser)
        current_time = time.time()
        
        if status is None:
            elapsed_wait = current_time - last_success_time
            if elapsed_wait > 3.0:
                print(f"\n[WARNING ] No response to status query for {elapsed_wait:.1f}s. Retrying...")
                warning_printed = True
            time.sleep(0.5)
            continue
            
        # If we recovered from a warning
        if warning_printed:
            print(f"\n[INFO    ] Connection recovered after {current_time - last_success_time:.1f}s.")
            warning_printed = False
            
        last_success_time = current_time
        state, current_line, total_lines, active, err_mask, err_code = status
        
        # Calculate percentage
        pct = (current_line / total_lines * 100) if total_lines > 0 else 0.0
        
        # State String
        if state == UPDATER_STATE_IDLE: state_str = "IDLE    "
        elif state == UPDATER_STATE_RUNNING: state_str = "RUNNING "
        elif state == UPDATER_STATE_DELAYING: state_str = "DELAYING"
        elif state == UPDATER_STATE_ERROR: state_str = "ERROR   "
        elif state == UPDATER_STATE_DONE: state_str = "DONE    "
        else: state_str = "UNKNOWN "
        
        sys.stdout.write(f"\r[{state_str}] Progress: {pct:5.1f}% [{current_line}/{total_lines}] | Active: {format_channels(active)} | Errors: {format_channels(err_mask)}")
        sys.stdout.flush()
        
        # State Machine Handling
        if state == UPDATER_STATE_ERROR:
            print(f"\n\n[CRITICAL ERROR] Updater reported an error! Code: {err_code}, Error Channels: {format_channels(err_mask)}")
            print("Sending STOP command...")
            stop_updater(ser)
            break
            
        if state == UPDATER_STATE_DONE:
            print("\n\n[SUCCESS ] Firmware update completed successfully on all active channels!")
            if err_mask != 0:
                print(f"[WARNING ] The following channels failed during the process: {format_channels(err_mask)}")
            break
            
        # Hang Detection
        if current_line == last_line and state != UPDATER_STATE_DELAYING:
            hang_counter += 1
            if hang_counter > 15: # ~15 seconds no progress
                print(f"\n\n[TIMEOUT ] Updater seems hung at line {current_line}. Sending STOP...")
                stop_updater(ser)
                break
        else:
            hang_counter = 0
            
        last_line = current_line
        time.sleep(1.0)

    ser.close()

def main():
    parser = argparse.ArgumentParser(description="Multi-Channel SLFS Updater Monitor")
    parser.add_argument("-port", required=True, help="Serial port to connect (e.g., com7)")
    parser.add_argument("-ch", type=int, nargs='+', required=True, help="List of channels to update (e.g., -ch 1 2 3)")
    
    args = parser.parse_args()
    
    # Validate channels
    valid_channels = []
    for c in args.ch:
        if 1 <= c <= 6:
            valid_channels.append(c)
        else:
            print(f"Warning: Ignoring invalid channel {c}")
            
    if not valid_channels:
        print("Error: No valid channels specified. Must be between 1 and 6.")
        return
        
    run_monitor(args.port, valid_channels)

if __name__ == "__main__":
    main()
