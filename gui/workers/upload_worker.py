import os
import time
import struct
import zlib
import serial
from PySide6.QtCore import QThread, Signal

from gui.protocol import (
    PROTOCOL_STX, PROTOCOL_ETX, RESP_OK,
    CMD_FW_GET_FILE_INFO, CMD_FW_UPLOAD_START, CMD_FW_UPLOAD_DATA, CMD_FW_UPLOAD_END,
    make_packet, parse_response
)


class UploadWorker(QThread):
    """Worker thread for uploading SLFS flash images to RP2040."""
    finished = Signal(bool)
    progress_updated = Signal(int)
    log_msg = Signal(str)

    def __init__(self, port: str, file_path: str, parent=None):
        super().__init__(parent)
        self.port = port
        self.file_path = file_path
        self.is_running = True

    def send_and_wait(self, ser, packet, expected_cmd, timeout=2.0):
        ser.reset_input_buffer()
        ser.write(packet)
        
        start_time = time.time()
        rx_buf = bytearray()
        
        while time.time() - start_time < timeout:
            if not self.is_running:
                return None
            if ser.in_waiting:
                rx_buf.extend(ser.read(ser.in_waiting))
                if len(rx_buf) >= 7 and rx_buf[0] == PROTOCOL_STX and rx_buf[-1] == PROTOCOL_ETX:
                    cmd, payload = parse_response(rx_buf)
                    if cmd == expected_cmd:
                        return payload
            time.sleep(0.01)
        return None

    def run(self):
        self.log_msg.emit(f"[INFO] Connecting to {self.port} for SLFS Upload...")
        
        if not os.path.exists(self.file_path):
            self.log_msg.emit(f"[ERROR] File '{self.file_path}' not found.")
            self.finished.emit(False)
            return
            
        try:
            with open(self.file_path, 'rb') as f:
                file_data = f.read()
        except Exception as e:
            self.log_msg.emit(f"[ERROR] Failed to read file: {e}")
            self.finished.emit(False)
            return
            
        file_size = len(file_data)
        file_crc = zlib.crc32(file_data) & 0xFFFFFFFF
        file_timestamp = int(os.path.getmtime(self.file_path)) & 0xFFFFFFFF
        filename_str = os.path.basename(self.file_path)[:63]
        
        ic_type_str = "Unknown"
        version_str = "Unknown"
        
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in range(10):
                    line = f.readline().strip()
                    if line.startswith("; IC Type:"):
                        ic_type_str = line.split(":", 1)[1].strip()[:31]
                    elif line.startswith("; Version:"):
                        version_str = line.split(":", 1)[1].strip()[:31]
        except Exception as e:
            self.log_msg.emit(f"[WARN] Could not parse SLFS header - {e}")
        
        try:
            ser = serial.Serial(self.port, 115200, timeout=1.0)
        except Exception as e:
            self.log_msg.emit(f"[ERROR] Failed to open {self.port}: {e}")
            self.finished.emit(False)
            return

        self.log_msg.emit(f"[INFO] File Size: {file_size} bytes, CRC32: 0x{file_crc:08X}")
        
        # 0. Check Existing
        self.log_msg.emit("0. Checking existing file on board...")
        packet = make_packet(CMD_FW_GET_FILE_INFO, b"")
        resp = self.send_and_wait(ser, packet, CMD_FW_GET_FILE_INFO, timeout=1.0)
        
        if resp and resp[0] == RESP_OK and len(resp) >= 81:
            board_magic = struct.unpack(">I", resp[1:5])[0]
            if board_magic == 0x534C4653:
                board_size = struct.unpack(">I", resp[5:9])[0]
                board_crc = struct.unpack(">I", resp[9:13])[0]
                board_ts = struct.unpack(">I", resp[13:17])[0]
                board_fn = resp[17:81].split(b'\x00')[0].decode('utf-8', errors='ignore')
                
                board_ic_type = "Unknown"
                board_version = "Unknown"
                if len(resp) >= 81 + 32 + 32:
                    board_ic_type = resp[81:113].split(b'\x00')[0].decode('utf-8', errors='ignore')
                    board_version = resp[113:145].split(b'\x00')[0].decode('utf-8', errors='ignore')
                
                self.log_msg.emit(f"   -> Board has: {board_fn} ({board_size} bytes, CRC:0x{board_crc:08X})")
                self.log_msg.emit(f"      [IC: {board_ic_type} | Ver: {board_version}]")
                if board_size == file_size and board_crc == file_crc and board_ts == file_timestamp and board_fn == filename_str:
                    if board_ic_type == ic_type_str and board_version == version_str:
                        self.log_msg.emit("   [SUCCESS] Identical file already exists on board. Skipping upload!")
                        ser.close()
                        self.progress_updated.emit(100)
                        self.finished.emit(True)
                        return
                    else:
                        self.log_msg.emit("   [INFO] Metadata differs. Forcing re-upload...")
            else:
                self.log_msg.emit("   -> No valid SLFS file found on board.")
        else:
            self.log_msg.emit("   -> Failed to query board file info or none exists.")

        if not self.is_running:
            ser.close()
            self.finished.emit(False)
            return

        # 1. Start Upload
        self.log_msg.emit("1. Sending FW_UPLOAD_START...")
        payload = struct.pack(">I", file_size)
        packet = make_packet(CMD_FW_UPLOAD_START, payload)
        resp = self.send_and_wait(ser, packet, CMD_FW_UPLOAD_START, timeout=4.0)
        
        if not resp or resp[0] != RESP_OK:
            self.log_msg.emit("[ERROR] Failed to start upload (Flash Erase timeout/error).")
            ser.close()
            self.finished.emit(False)
            return
            
        self.log_msg.emit("   -> Flash Erase and Start OK")
        
        # 2. Upload Data in Chunks
        chunk_size = 256
        offset = 0
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        chunk_idx = 1
        
        self.log_msg.emit("2. Uploading Data...")
        while offset < file_size:
            if not self.is_running:
                break
                
            remain = file_size - offset
            length = min(chunk_size, remain)
            chunk = file_data[offset:offset+length]
            
            payload = struct.pack(">I H", offset, length) + chunk
            packet = make_packet(CMD_FW_UPLOAD_DATA, payload)
            
            resp = self.send_and_wait(ser, packet, CMD_FW_UPLOAD_DATA, timeout=1.0)
            if not resp or resp[0] != RESP_OK:
                self.log_msg.emit(f"[ERROR] Failed at chunk {chunk_idx}/{total_chunks} (Offset: {offset}).")
                ser.close()
                self.finished.emit(False)
                return
                
            progress = int((offset + length) / file_size * 100)
            self.progress_updated.emit(progress)
            
            offset += length
            chunk_idx += 1

        if not self.is_running:
            ser.close()
            self.finished.emit(False)
            return
            
        self.log_msg.emit("   -> Data Upload Complete")
        
        # 3. End Upload & Verify
        self.log_msg.emit("3. Sending FW_UPLOAD_END (CRC Check)...")
        fn_bytes = filename_str.encode('utf-8').ljust(64, b'\x00')
        ic_bytes = ic_type_str.encode('utf-8').ljust(32, b'\x00')
        ver_bytes = version_str.encode('utf-8').ljust(32, b'\x00')
        
        payload = struct.pack(">I I", file_crc, file_timestamp) + fn_bytes + ic_bytes + ver_bytes
        packet = make_packet(CMD_FW_UPLOAD_END, payload)
        resp = self.send_and_wait(ser, packet, CMD_FW_UPLOAD_END, timeout=2.0)
        
        if not resp or resp[0] != RESP_OK:
            self.log_msg.emit("[ERROR] Upload verification failed! CRC mismatch or write error.")
            ser.close()
            self.finished.emit(False)
            return
            
        self.log_msg.emit("[SUCCESS] Verification OK! SLFS file successfully stored in RP2040 Flash.")
        ser.close()
        self.finished.emit(True)

    def stop(self):
        self.is_running = False
        self.log_msg.emit("[INFO] Stop requested...")
