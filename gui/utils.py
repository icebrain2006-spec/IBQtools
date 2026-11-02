import os
import sys
import csv
import math
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
        dir_name = os.path.dirname(os.path.abspath(log_path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
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
            wav_name = "testFail.wav" if is_error else "testComplete.wav"
            gui_dir = os.path.dirname(os.path.abspath(__file__))
            repo_dir = os.path.dirname(gui_dir)
            exe_dir = os.path.dirname(sys.executable)
            meipass = getattr(sys, '_MEIPASS', '')

            # Search across all potential locations (exe dir, _MEIPASS, repo dir, and gui dir)
            candidate_paths = [
                os.path.join(exe_dir, "assets", "wav", wav_name),
                os.path.join(exe_dir, "_internal", "assets", "wav", wav_name),
                os.path.join(exe_dir, "_internal", "gui", "assets", "wav", wav_name),
                os.path.join(meipass, "assets", "wav", wav_name) if meipass else "",
                os.path.join(meipass, "gui", "assets", "wav", wav_name) if meipass else "",
                os.path.join(gui_dir, "assets", "wav", wav_name),
                os.path.join(repo_dir, "assets", "wav", wav_name),
                os.path.join(repo_dir, "gui", "assets", "wav", wav_name),
            ]

            wav_path = None
            for p in candidate_paths:
                if p and os.path.exists(p):
                    wav_path = p
                    break

            if wav_path:
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


def convert_csv_to_slfs(input_path: str, output_path: str, ic_type: str, version: str, log_callback=None) -> tuple[bool, int, str]:
    """
    Parses I2C CSV transactions from input_path and generates formatted .slfs file at output_path.
    Returns (success: bool, transaction_count: int, message: str).
    """
    if log_callback:
        log_callback(f"[INFO] Starting conversion: {input_path} -> {output_path}")

    try:
        with open(input_path, 'r', encoding='utf-8') as infile, open(output_path, 'w', encoding='utf-8') as outfile:
            reader = csv.DictReader(infile)
            rows = list(reader)
            
            outfile.write("; slfs file generated from i2cdata.csv\n")
            outfile.write(f"; IC Type: {ic_type}\n")
            outfile.write(f"; Version: {version}\n")           
            
            i = 0
            last_time = 0
            transaction_count = 0
            
            while i < len(rows):
                if rows[i].get('type') == 'start':
                    j = i + 1
                    stop_index = -1
                    while j < len(rows):
                        if rows[j].get('type') == 'stop':
                            stop_index = j
                            break
                        j += 1
                    
                    if stop_index == -1:
                        i += 1
                        continue # Incomplete transaction

                    transaction_rows = rows[i:stop_index + 1]
                    
                    # Pattern: Write-then-Read
                    cmd_lines = []
                    if (len(transaction_rows) >= 6 and
                        transaction_rows[1].get('type') == 'address' and transaction_rows[1].get('read') == 'false' and
                        transaction_rows[2].get('type') == 'data' and
                        transaction_rows[3].get('type') == 'start' and
                        transaction_rows[4].get('type') == 'address' and transaction_rows[4].get('read') == 'true' and
                        transaction_rows[1].get('address') == transaction_rows[4].get('address')):
                        
                        address_hex = transaction_rows[1]['address'].replace('0x', '')
                        command_byte = transaction_rows[2]['data'].replace('0x', '')
                        read_bytes = [r['data'].replace('0x', '') for r in transaction_rows[5:] if r.get('type') == 'data']
                        
                        write_address_8bit = f"{(int(address_hex, 16) << 1):02X}"
                        all_bytes = [write_address_8bit, command_byte] + read_bytes
                        cmd_lines.append(f"C: {' '.join(all_bytes)}\n")

                    elif len(transaction_rows) > 1 and transaction_rows[1].get('type') == 'address':
                        address_hex = transaction_rows[1]['address'].replace('0x', '')
                        # Filter out non-target noise addresses
                        if address_hex.upper() not in ('0B', '16'):
                            i = stop_index + 1
                            continue

                        is_read = transaction_rows[1].get('read') == 'true'
                        data_bytes = [r['data'].replace('0x', '') for r in transaction_rows[2:] if r.get('type') == 'data']

                        if not is_read: # Simple Write
                            write_address_8bit = f"{(int(address_hex, 16) << 1):02X}"
                            # If first command is 0x44 without arguments, normalize to full ROM mode entry
                            if transaction_count == 0 and data_bytes == ['44']:
                                all_bytes = [write_address_8bit, '44', '02', '00', '0F', '41']
                            else:
                                all_bytes = [write_address_8bit] + data_bytes
                            cmd_lines.append(f"W: {' '.join(all_bytes)}\n")
                        else: # Simple Read
                            cmd_lines.append(f"C: {address_hex} R\n")
                            if data_bytes:
                                cmd_lines.append(f"W: {' '.join(data_bytes)}\n")

                    if cmd_lines:
                        # Time delay: <= 2ms -> 2ms, > 2ms -> ceil to next multiple of 10ms
                        if last_time != 0:
                            time_diff = (float(transaction_rows[0]['start_time']) - last_time) * 1000
                            if time_diff <= 2:
                                delay_val = 2
                            else:
                                delay_val = int(math.ceil(time_diff / 10.0) * 10)
                            outfile.write(f"X: {delay_val}\n")

                        for cmd in cmd_lines:
                            outfile.write(cmd)
                        transaction_count += 1
                        last_time = float(transaction_rows[-1]['start_time']) + float(transaction_rows[-1]['duration'])

                    i = stop_index + 1
                else:
                    i += 1

        if log_callback:
            log_callback(f"[INFO] Processed {transaction_count} transactions.")

        return True, transaction_count, "File converted successfully!"
    except Exception as e:
        return False, 0, str(e)


def load_bq_ic_info(info_path: str) -> dict[str, set[str]]:
    """
    Reads BQ_Information.csv and returns a dictionary mapping IC names to set of versions.
    """
    ic_dict = {}
    if not os.path.exists(info_path):
        return ic_dict

    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ic = row.get('IC')
                version = row.get('Version')
                if ic and version:
                    if ic not in ic_dict:
                        ic_dict[ic] = set()
                    ic_dict[ic].add(version)
    except Exception as e:
        logging.getLogger('IBQtools').error(f"Could not load BQ_Information.csv: {e}")

    return ic_dict
