import argparse
import serial
import struct
import time
import sys
import os
import zlib

PROTOCOL_STX = 0x02
PROTOCOL_ETX = 0x03
CMD_FW_UPLOAD_START  = 0x30
CMD_FW_UPLOAD_DATA   = 0x31
CMD_FW_UPLOAD_END    = 0x32
CMD_FW_UPDATE_RUN    = 0x33
CMD_FW_UPDATE_STATUS = 0x34
CMD_FW_GET_FILE_INFO = 0x35
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
    
    crc_calc = crc16_calculate(bytes([cmd]) + payload)
    if crc_calc != crc_rx:
        return None, f"CRC mismatch: rx={crc_rx:#x}, calc={crc_calc:#x}"
        
    return cmd, payload

def send_and_wait(ser, packet, expected_cmd, timeout=2.0):
    ser.reset_input_buffer()
    ser.write(packet)
    
    start_time = time.time()
    rx_buf = bytearray()
    
    while time.time() - start_time < timeout:
        if ser.in_waiting:
            rx_buf.extend(ser.read(ser.in_waiting))
            # Minimal packet is 7 bytes
            if len(rx_buf) >= 7 and rx_buf[0] == PROTOCOL_STX and rx_buf[-1] == PROTOCOL_ETX:
                cmd, payload = parse_response(rx_buf)
                if cmd == expected_cmd:
                    return payload
        time.sleep(0.01)
    
    return None

def upload_slfs(port_name, file_path):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return False
        
    with open(file_path, 'rb') as f:
        file_data = f.read()
        
    file_size = len(file_data)
    file_crc = zlib.crc32(file_data) & 0xFFFFFFFF
    file_timestamp = int(os.path.getmtime(file_path)) & 0xFFFFFFFF
    filename_str = os.path.basename(file_path)[:63]
    
    print(f"Connecting to RP2040 on {port_name}...")
    try:
        ser = serial.Serial(port_name, 115200, timeout=1.0)
    except Exception as e:
        print(f"Error opening serial port: {e}")
        return False
        
    print(f"File Size: {file_size} bytes")
    print(f"File CRC32: {file_crc:#010x}")
    print(f"Timestamp: {file_timestamp}")
    print(f"Filename:  {filename_str}")
    print("-" * 50)
    
    # 0. Check Existing File Info
    print("0. Checking existing file on board...")
    packet = make_packet(CMD_FW_GET_FILE_INFO, b"")
    resp = send_and_wait(ser, packet, CMD_FW_GET_FILE_INFO, timeout=1.0)
    if resp and resp[0] == RESP_OK and len(resp) >= 81:
        board_magic = struct.unpack(">I", resp[1:5])[0]
        if board_magic == 0x534C4653: # "SLFS"
            board_size = struct.unpack(">I", resp[5:9])[0]
            board_crc = struct.unpack(">I", resp[9:13])[0]
            board_ts = struct.unpack(">I", resp[13:17])[0]
            board_fn = resp[17:81].split(b'\x00')[0].decode('utf-8', errors='ignore')
            print(f"   -> Board has: {board_fn} ({board_size} bytes, CRC:{board_crc:#010x}, TS:{board_ts})")
            
            if board_size == file_size and board_crc == file_crc and board_ts == file_timestamp and board_fn == filename_str:
                print("\n   [SUCCESS] Identical file already exists on board. Skipping upload!")
                print("-" * 50)
                ser.close()
                return True
        else:
            print("   -> No valid SLFS file found on board.")
    else:
        print("   -> Failed to query board file info or none exists.")
        
    print("-" * 50)
    # 1. Start Upload
    print("1. Sending FW_UPLOAD_START...")
    payload = struct.pack(">I", file_size)
    packet = make_packet(CMD_FW_UPLOAD_START, payload)
    resp = send_and_wait(ser, packet, CMD_FW_UPLOAD_START, timeout=3.0) # Flash erase might take time
    
    if not resp or resp[0] != RESP_OK:
        print(f"Failed to start upload. Response: {resp}")
        return False
        
    print("   -> Flash Erase and Start OK")
    
    # 2. Upload Data in Chunks
    chunk_size = 256
    offset = 0
    total_chunks = (file_size + chunk_size - 1) // chunk_size
    chunk_idx = 1
    
    print("2. Uploading Data...")
    while offset < file_size:
        remain = file_size - offset
        length = min(chunk_size, remain)
        chunk = file_data[offset:offset+length]
        
        payload = struct.pack(">I H", offset, length) + chunk
        packet = make_packet(CMD_FW_UPLOAD_DATA, payload)
        
        resp = send_and_wait(ser, packet, CMD_FW_UPLOAD_DATA, timeout=1.0)
        if not resp or resp[0] != RESP_OK:
            print(f"\nFailed at chunk {chunk_idx}/{total_chunks} (Offset: {offset}).")
            return False
            
        progress = (offset + length) / file_size * 100
        sys.stdout.write(f"\r   -> Progress: {progress:5.1f}% [{chunk_idx}/{total_chunks}]")
        sys.stdout.flush()
        
        offset += length
        chunk_idx += 1
        
    print("\n   -> Data Upload Complete")
    
    # 3. End Upload & Verify
    print("3. Sending FW_UPLOAD_END (CRC Check)...")
    fn_bytes = filename_str.encode('utf-8')
    payload = struct.pack(">I I", file_crc, file_timestamp) + fn_bytes
    print(f"Debug UPLOAD_END payload: {payload.hex()}")
    packet = make_packet(CMD_FW_UPLOAD_END, payload)
    resp = send_and_wait(ser, packet, CMD_FW_UPLOAD_END, timeout=1.0)
    
    if not resp or resp[0] != RESP_OK:
        print(f"Upload verification failed! CRC mismatch or write error. Resp: {resp}")
        return False
        
    print("   -> Verification OK! SLFS file successfully stored in RP2040 Flash.")
    print("-" * 50)
    ser.close()
    return True

def main():
    parser = argparse.ArgumentParser(description="Upload SLFS firmware script to RP2040 Flash")
    parser.add_argument("-port", required=True, help="Serial port to connect (e.g., com7 or COM7)")
    parser.add_argument("-file", required=True, help="Path to .slfs file")
    
    args = parser.parse_args()
    upload_slfs(args.port, args.file)

if __name__ == "__main__":
    main()
