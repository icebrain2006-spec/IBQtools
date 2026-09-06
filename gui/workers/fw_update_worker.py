import os
import shutil
import tempfile
import time
import struct
import serial.tools.list_ports
from PySide6.QtCore import QThread, Signal

from gui.widgets import get_available_ports
from gui.fw_updater import get_latest_github_release, download_file, find_rp2040_drive
from gui.updater_thread import get_fw_version


def crc16_calculate(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def send_software_bootsel_reboot(target_port=None, progress_signal=None) -> bool:
    """Send software reset command to RP2040 board over Serial."""
    found = False
    for p in serial.tools.list_ports.comports():
        if target_port and p.device != target_port:
            continue
        if "USB" in str(p.hwid).upper() or "USB" in str(p.description).upper():
            try:
                ser = serial.Serial(p.device, 115200, timeout=1.0)
                cmd = 0x02  # CMD_REBOOT_BOOTSEL
                payload = b""
                total_len = 1 + len(payload)
                header = struct.pack(">B H B", 0x02, total_len, cmd)
                crc_data = bytes([cmd]) + payload
                crc = crc16_calculate(crc_data)
                footer = struct.pack(">H B", crc, 0x03)
                packet = header + payload + footer
                ser.write(packet)
                ser.close()
                if progress_signal:
                    progress_signal.emit(f"Sent BOOTSEL reset to {p.device}")
                found = True
            except Exception as e:
                if progress_signal:
                    progress_signal.emit(f"Failed to reset {p.device}: {e}")
    if found:
        time.sleep(2.0)  # Wait for board to remount as USB drive
    return found


class RebootBootselWorker(QThread):
    """Background worker for sending software BOOTSEL reboot without blocking UI thread."""
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, target_port=None):
        super().__init__()
        self.target_port = target_port

    def run(self):
        try:
            self.progress.emit(f"Sending BOOTSEL reset to {self.target_port}...")
            success = send_software_bootsel_reboot(self.target_port, progress_signal=self.progress)
            if success:
                self.finished.emit(True, f"Reboot command sent to {self.target_port}.")
            else:
                self.finished.emit(False, f"Failed to send reset command to {self.target_port}.")
        except Exception as e:
            self.finished.emit(False, str(e))


class CheckUpdateWorker(QThread):
    """Worker to check GitHub latest release and connected board versions."""
    finished = Signal(str, str, list, list)  # tag_name, url, versions, active_ports
    error = Signal(str)

    def __init__(self, repo):
        super().__init__()
        self.repo = repo

    def run(self):
        try:
            # 1. Fetch latest github release
            tag, url = get_latest_github_release(self.repo)

            # 2. Get current board version by scanning active COM ports
            active_ports, _ = get_available_ports(include_none=False)
            active_ports = [p for p in active_ports if p != "Select COM"]

            versions = []
            valid_ports = []
            for port in active_ports:
                ver = get_fw_version(port)
                if ver:
                    versions.append(ver)
                    valid_ports.append(port)

            if tag and url:
                self.finished.emit(tag, url, versions, valid_ports)
            else:
                self.error.emit("Could not find a valid .uf2 release.")
        except Exception as e:
            self.error.emit(str(e))


class DownloadUpdateWorker(QThread):
    """Worker to download and copy firmware .uf2 file to RP2040 BOOTSEL drive."""
    progress = Signal(str)
    finished = Signal(bool, str)  # success, message

    def __init__(self, url=None, local_file=None):
        super().__init__()
        self.url = url
        self.local_file = local_file

    def run(self):
        if self.local_file:
            self.progress.emit("Using local .uf2 file...")
            dest_path = self.local_file
        else:
            self.progress.emit("Downloading .uf2 file...")
            temp_dir = tempfile.gettempdir()
            dest_path = os.path.join(temp_dir, "rp2040_update.uf2")

            success = download_file(self.url, dest_path)
            if not success:
                self.finished.emit(False, "Failed to download the file.")
                return

        self.progress.emit("Waiting for RP2040 BOOTSEL Drive...")
        drive = None
        # Poll for up to 30 seconds
        for _ in range(60):
            drive = find_rp2040_drive()
            if drive:
                break
            time.sleep(0.5)

        if not drive:
            self.finished.emit(False, "Timeout: RP2040 BOOTSEL drive not found.")
            return

        self.progress.emit(f"RP2040 found at {drive}. Copying firmware...")
        try:
            shutil.copy2(dest_path, os.path.join(drive, "rp2040_update.uf2"))
            self.progress.emit("Update complete! Device will reboot automatically.")
            self.finished.emit(True, "Update successfully flashed to RP2040.")
        except Exception as e:
            self.finished.emit(False, f"Error copying file: {e}")
