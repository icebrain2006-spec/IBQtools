import os
import sys
import time
import struct
import zlib
import serial
import serial.tools.list_ports

from gui.protocol import (
    PROTOCOL_STX, PROTOCOL_ETX, RESP_OK,
    CMD_GET_VERSION, CMD_FW_GET_FILE_INFO,
    CMD_FW_UPLOAD_START, CMD_FW_UPLOAD_DATA, CMD_FW_UPLOAD_END,
    CMD_FW_UPDATE_RUN, CMD_FW_UPDATE_STATUS, CMD_FW_UPDATE_STOP,
    CMD_SMBUS_CMD,
    UPDATER_STATE_IDLE, UPDATER_STATE_RUNNING, UPDATER_STATE_DELAYING,
    UPDATER_STATE_ERROR, UPDATER_STATE_DONE,
    make_packet, parse_response
)

def find_rp2040_port():
    for p in serial.tools.list_ports.comports():
        if "2E8A" in str(p.hwid).upper():
            return p.device
    for p in serial.tools.list_ports.comports():
        if "USB" in str(p.description).upper():
            return p.device
    return "COM6"

def send_and_wait(ser, cmd, payload=b"", timeout=1.0):
    pkt = make_packet(cmd, payload)
    ser.reset_input_buffer()
    ser.write(pkt)
    
    start_time = time.time()
    buf = bytearray()
    while time.time() - start_time < timeout:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
            stx_idx = buf.find(PROTOCOL_STX)
            if stx_idx != -1 and len(buf) >= stx_idx + 7:
                length = struct.unpack(">H", buf[stx_idx+1:stx_idx+3])[0]
                expected_total = length + 6
                if len(buf) >= stx_idx + expected_total:
                    resp_cmd, resp_payload = parse_response(buf[stx_idx:stx_idx+expected_total])
                    if resp_cmd == cmd:
                        return resp_payload
        time.sleep(0.01)
    return None

def check_battery(ser, ch):
    # Read 0x1B (Date) and 0x1C (SN)
    payload_date = bytes([ch, 0x0B, 0x1B, 1, 2, 0, 0])
    resp_date = send_and_wait(ser, CMD_SMBUS_CMD, payload_date, timeout=0.3)
    
    payload_sn = bytes([ch, 0x0B, 0x1C, 1, 2, 0, 0])
    resp_sn = send_and_wait(ser, CMD_SMBUS_CMD, payload_sn, timeout=0.3)
    
    if resp_date and resp_date[0] == RESP_OK and resp_sn and resp_sn[0] == RESP_OK:
        date_val = resp_date[1] | (resp_date[2] << 8)
        sn_val = resp_sn[1] | (resp_sn[2] << 8)
        year = (date_val >> 9) + 1980
        month = (date_val >> 5) & 0x0F
        day = date_val & 0x1F
        return f"{year}-{month:02d}-{day:02d}", sn_val
    return None, None

def upload_slfs(ser, file_path):
    with open(file_path, "rb") as f:
        file_data = f.read()
    file_size = len(file_data)
    file_crc = zlib.crc32(file_data) & 0xFFFFFFFF
    filename_str = os.path.basename(file_path)[:63]
    
    print(f"[UPLOAD] Checking existing file on RP2040...")
    resp = send_and_wait(ser, CMD_FW_GET_FILE_INFO, b"", timeout=1.0)
    if resp and resp[0] == RESP_OK and len(resp) >= 81:
        board_magic = struct.unpack(">I", resp[1:5])[0]
        if board_magic == 0x534C4653:
            board_size = struct.unpack(">I", resp[5:9])[0]
            board_crc = struct.unpack(">I", resp[9:13])[0]
            board_fn = resp[17:81].split(b'\x00')[0].decode('utf-8', errors='ignore')
            print(f"   -> Board has: {board_fn} ({board_size} bytes, CRC:0x{board_crc:08X})")
            if board_size == file_size and board_crc == file_crc and board_fn == filename_str:
                print("   [SUCCESS] Identical file already exists on board. Skipping upload!\n")
                return True

    print(f"[UPLOAD] Uploading {filename_str} ({file_size} bytes, CRC:0x{file_crc:08X})...")
    resp = send_and_wait(ser, CMD_FW_UPLOAD_START, struct.pack(">I", file_size), timeout=4.0)
    if not resp or resp[0] != RESP_OK:
        print("[ERROR] Failed to start upload (Flash Erase timeout).")
        return False
        
    chunk_size = 128
    offset = 0
    while offset < file_size:
        chunk = file_data[offset:offset + chunk_size]
        payload = struct.pack(">I", offset) + chunk
        resp = send_and_wait(ser, CMD_FW_UPLOAD_DATA, payload, timeout=1.0)
        if not resp or resp[0] != RESP_OK:
            print(f"[ERROR] Upload data chunk failed at offset {offset}")
            return False
        offset += len(chunk)
        pct = int(offset / file_size * 100)
        print(f"\r[UPLOAD] Progress: {pct}% ({offset}/{file_size} bytes)", end="", flush=True)
    print()
    
    end_payload = struct.pack(">I I 64s", file_crc, int(time.time()), filename_str.encode('utf-8'))
    resp = send_and_wait(ser, CMD_FW_UPLOAD_END, end_payload, timeout=2.0)
    if not resp or resp[0] != RESP_OK:
        print("[ERROR] Final upload verification failed.")
        return False
    print("[SUCCESS] SLFS file successfully uploaded and verified in RP2040 Flash!\n")
    return True

def run_flashing(ser, active_channels):
    ch_mask = 0
    for ch in active_channels:
        ch_mask |= (1 << (ch - 1))
        
    print(f"[FLASH] Starting firmware update on channels: {active_channels} (mask=0x{ch_mask:02X})...")
    resp = send_and_wait(ser, CMD_FW_UPDATE_RUN, bytes([ch_mask]), timeout=1.0)
    if not resp or resp[0] != RESP_OK:
        print(f"[ERROR] Failed to trigger update: {resp}")
        return False

    print("[FLASH] Updater is running on RP2040 Core 1. Monitoring progress...")
    last_print_line = -1
    start_time = time.time()
    
    while True:
        resp = send_and_wait(ser, CMD_FW_UPDATE_STATUS, b"", timeout=0.5)
        if not resp or len(resp) < 13:
            time.sleep(0.1)
            continue
            
        state = resp[1]
        current_line = struct.unpack(">I", resp[2:6])[0]
        total_lines = struct.unpack(">I", resp[6:10])[0]
        active = resp[10]
        err_mask = resp[11]
        err_code = struct.unpack(">i", resp[12:16])[0] if len(resp) >= 16 else struct.unpack(">b", bytes([resp[12]]))[0]
        
        pct = (current_line / total_lines * 100) if total_lines > 0 else 0
        state_str = {0: "IDLE", 1: "RUNNING", 2: "DELAY", 3: "ERROR", 4: "DONE"}.get(state, f"STATE_{state}")
        
        if current_line != last_print_line or state in (UPDATER_STATE_ERROR, UPDATER_STATE_DONE):
            last_print_line = current_line
            elapsed = time.time() - start_time
            print(f"[{elapsed:5.1f}s] Line {current_line:4d}/{total_lines:4d} ({pct:5.1f}%) | {state_str} | err_mask=0x{err_mask:02X} err_code={err_code}")
            
        if state == UPDATER_STATE_ERROR:
            print(f"\n[CRITICAL] Flashing aborted with Error Code {err_code} at line {current_line}!")
            send_and_wait(ser, CMD_FW_UPDATE_STOP, b"", timeout=0.5)
            return False
            
        if state == UPDATER_STATE_DONE:
            print(f"\n[SUCCESS] All {total_lines} lines executed successfully in {time.time()-start_time:.1f}s!")
            send_and_wait(ser, CMD_FW_UPDATE_STOP, b"", timeout=0.5)
            return True
            
        time.sleep(0.08)

def main():
    port = find_rp2040_port()
    print(f"==================================================")
    print(f"  IBQtools RP2040 Firmware Flasher CLI")
    print(f"  Target Port: {port}")
    print(f"==================================================")
    
    try:
        ser = serial.Serial(port, 115200, timeout=0.5)
    except Exception as e:
        print(f"[ERROR] Cannot open {port}: {e}")
        print("\n[안내] RP2040 USB 케이블을 한 번 뽑았다가 다시 꽂아주세요 (USB 리셋).")
        return

    # Check Version
    resp = send_and_wait(ser, CMD_GET_VERSION, b"", timeout=1.0)
    if resp and resp[0] == RESP_OK:
        ver = resp[1:].split(b'\x00')[0].decode('utf-8', errors='ignore')
        print(f"[OK] Connected to RP2040 (Firmware {ver})")
    else:
        print("[WARN] No version response from RP2040, but port opened.")

    # Check all channels for battery
    print("\n[SCAN] Checking connected battery channels (1~6)...")
    detected_channels = []
    for ch in range(1, 7):
        date_str, sn_val = check_battery(ser, ch)
        if date_str:
            print(f"  -> Channel {ch}: DETECTED! [M: {date_str}, SN: {sn_val} (0x{sn_val:04X})]")
            detected_channels.append(ch)
        else:
            print(f"  -> Channel {ch}: No Battery")

    if not detected_channels:
        print("\n[WARN] No batteries detected via standard SMBus! Defaulting to Channel 2...")
        detected_channels = [2]
        
    # Select SLFS file
    slfs_file = r"d:\WinApp\python\IBQtools\reference\TEMPP\BQU_LI18S01_261015_09_unseal.slfs"
    if not os.path.exists(slfs_file):
        slfs_file = r"d:\WinApp\python\IBQtools\reference\TEMPP\BQU_LI18S01_261015_09.slfs"
        
    print(f"\n[FILE] Selected SLFS: {slfs_file}")
    if not upload_slfs(ser, slfs_file):
        ser.close()
        return

    # Run flashing
    success = run_flashing(ser, detected_channels)
    
    # Post-check
    print("\n[VERIFY] Waiting 2 seconds for BQ chip reboot...")
    time.sleep(2.0)
    for ch in detected_channels:
        date_str, sn_val = check_battery(ser, ch)
        if date_str:
            print(f"  -> Channel {ch} Post-Check: OK! [M: {date_str}, SN: {sn_val}]")
        else:
            print(f"  -> Channel {ch} Post-Check: Failed to read (chip may still be rebooting or in ROM mode)")

    ser.close()
    print("\n[FINISH] Flashing execution finished.")

if __name__ == '__main__':
    main()
