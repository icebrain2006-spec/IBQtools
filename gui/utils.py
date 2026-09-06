import os
import csv
import datetime
import logging
import time
import threading
import winsound
import serial.tools.list_ports

def append_work_log(log_path: str, board_id: int, ch_idx: int, slfs_file: str, wrote_sn: str, date_str: str, sn_str: str, result_str: str) -> None:
    """
    Appends a single verification record to the CSV work log file safely.
    Isolates File I/O operations from UI components as per AGENTS.md standards.
    """
    if not log_path:
        return

    try:
        file_exists = os.path.exists(log_path)
        with open(log_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Board_ID", "Channel", "SLFS_File", "Wrote_SN", "Read_Date", "Read_SN", "Result"])
            
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([ts, board_id, ch_idx, slfs_file, wrote_sn, date_str or "N/A", sn_str, result_str])
    except Exception as e:
        logging.getLogger('IBQtools').error(f"Failed to write work log: {e}")


def play_sound_effect(is_error: bool) -> None:
    """
    Asynchronously plays a completion or failure WAV audio sound effect, with fallback beeps if WAV is unavailable.
    """
    def _play():
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ref_dir = os.path.join(base_dir, "assets", "wav")
            wav_name = "testFail.wav" if is_error else "testComplete.wav"
            wav_path = os.path.join(ref_dir, wav_name)

            if os.path.exists(wav_path):
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            else:
                if is_error:
                    winsound.Beep(350, 80)
                    time.sleep(0.03)
                    winsound.Beep(350, 80)
                else:
                    winsound.Beep(880, 80)
                    winsound.Beep(1046, 80)
                    winsound.Beep(1318, 150)
        except Exception as e:
            logging.getLogger('IBQtools').error(f"Failed to play sound effect: {e}")

    threading.Thread(target=_play, daemon=True).start()


def get_active_usb_ports() -> list[str]:
    """
    Scans available COM serial ports and filters out Bluetooth/virtual ports, returning valid USB device ports.
    """
    ports = ["None"]
    for p in serial.tools.list_ports.comports():
        hwid = str(p.hwid).upper()
        desc = str(p.description).upper()
        if "BTHENUM" in hwid or "BLUETOOTH" in desc or "BTHENUM" in desc:
            continue
        if "USB" not in hwid and "USB" not in desc:
            continue
        ports.append(p.device)
    return ports


def format_sn_value(sn_int: int, fmt: str) -> tuple[int, str]:
    """
    Formats integer SN into DEC/HEX representation with BCD conversion and handles overflow boundaries.
    """
    if sn_int < 0:
        return sn_int, "N/A"

    if fmt == "HEX":
        if sn_int > 65535:
            sn_int = 0
        return sn_int, f"0x{sn_int:04X}"
    else:
        if sn_int > 9999:
            sn_int = 0
        try:
            actual_sn = int(f"{sn_int:X}", 10)
            sn_str = str(actual_sn)
        except ValueError:
            actual_sn = sn_int
            sn_str = f"INVALID_BCD_0x{sn_int:04X}"
        return actual_sn, sn_str


def is_error_status(text: str) -> bool:
    """
    Checks if a given status message or text contains error/failure keywords.
    """
    if not text:
        return False
    lower_text = text.lower()
    return "error" in lower_text or "fail" in lower_text or "오류" in lower_text
