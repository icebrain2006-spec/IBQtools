import os
import csv
import datetime
import logging

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
