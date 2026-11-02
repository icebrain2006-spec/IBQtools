import os
import re
import shutil
import winreg
from typing import Optional, List, Dict, Tuple


def detect_google_drive_folder() -> str:
    """
    Detect Google Drive paths on Windows, preferring 'IB_Product_Log/IBQtools'
    or a dedicated Google Drive folder outside the project directory.
    Falls back to user's Documents/IBQtools_Log if Google Drive is not detected.
    """
    candidates: List[str] = []

    # 1. Inspect Google DriveFS registry SyncTargets
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS\Share") as key:
            val, _ = winreg.QueryValueEx(key, "SyncTargets")
            if isinstance(val, bytes):
                text = val.decode("utf-8", errors="ignore")
                matches = re.findall(r'[A-Za-z]:\\[^:\*\?"<>\|\r\n\x00-\x1f]+', text)
                for m in matches:
                    clean = re.split(r'[\x00-\x20]', m.strip())[0]
                    if os.path.isdir(clean):
                        candidates.append(clean)
    except Exception:
        pass

    # 2. Check well-known Google Drive junction points / drive letters
    search_roots = [
        r"D:\icebrain2006",
        r"D:\Supplysn81",
        r"D:\Supplysn8102",
        r"D:\GoogleDrive",
        r"G:\내 드라이브",
        r"G:\My Drive",
        os.path.expanduser(r"~\Google Drive"),
    ]

    for root in search_roots:
        if os.path.isdir(root) and root not in candidates:
            candidates.append(root)

    # 3. Resolve "내 드라이브" or "My Drive" subfolders
    valid_drive_roots: List[str] = []
    for cand in candidates:
        for sub in ["내 드라이브", "My Drive"]:
            p = os.path.join(cand, sub)
            if os.path.isdir(p) and p not in valid_drive_roots:
                valid_drive_roots.append(p)
        if os.path.isdir(cand) and cand not in valid_drive_roots:
            valid_drive_roots.append(cand)

    # 4. Search for IB_Product_Log first (optimal match for company infrastructure)
    for v in valid_drive_roots:
        ib_log_path = os.path.join(v, "IB_Product_Log")
        if os.path.isdir(ib_log_path):
            target = os.path.join(ib_log_path, "IBQtools")
            return target

    # 5. Otherwise, use the first valid drive root with "IBQtools_Log"
    if valid_drive_roots:
        return os.path.join(valid_drive_roots[0], "IBQtools_Log")

    # 6. Fallback outside project workspace (Documents)
    return os.path.join(os.path.expanduser(r"~\Documents"), "IBQtools_Log")


def get_default_log_dir() -> str:
    """Returns the safest default directory for storing logs outside repo."""
    target_dir = detect_google_drive_folder()
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        fallback = os.path.join(os.path.expanduser(r"~\Documents"), "IBQtools_Log")
        os.makedirs(fallback, exist_ok=True)
        return fallback
    return target_dir


def is_project_local_path(path: str) -> bool:
    """Check if the path is relative or points directly inside the project root."""
    if not path:
        return True
    if not os.path.isabs(path):
        return True
    
    current_dir = os.path.abspath(os.getcwd()).lower()
    abs_path = os.path.abspath(path).lower()
    return abs_path.startswith(current_dir)


def migrate_csv_file(src_path: str, dest_path: str) -> Tuple[bool, str]:
    """
    Safely copy or merge a CSV log file from src_path to dest_path.
    If dest_path already exists, skips duplicate header and appends new rows.
    """
    if not os.path.isfile(src_path):
        return False, f"Source file '{src_path}' not found."

    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)

    if not os.path.exists(dest_path):
        shutil.copy2(src_path, dest_path)
        return True, f"Copied to '{dest_path}'."

    # Dest exists: read both and append only new unique data lines
    try:
        with open(src_path, "r", encoding="utf-8", errors="replace") as f_src:
            src_lines = f_src.readlines()
        with open(dest_path, "r", encoding="utf-8", errors="replace") as f_dst:
            dst_lines = set(line.strip() for line in f_dst if line.strip())

        new_lines = []
        for line in src_lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip if exact line is already in destination
            if stripped not in dst_lines:
                new_lines.append(line)

        if new_lines:
            with open(dest_path, "a", encoding="utf-8") as f_dst:
                f_dst.writelines(new_lines)
            return True, f"Merged {len(new_lines)} lines into '{dest_path}'."
        return True, f"Destination '{dest_path}' is already up to date."
    except Exception as e:
        return False, f"Failed to merge: {e}"


def migrate_all_local_logs(dest_dir: str) -> Dict[str, Tuple[bool, str]]:
    """
    Migrates standard local log files (work_log.csv, cal_log.csv)
    to the designated destination directory.
    """
    results = {}
    standard_files = {
        "work_log.csv": os.path.join(dest_dir, "work_log.csv"),
        "cal_log.csv": os.path.join(dest_dir, "cal_log.csv"),
        "error_log.txt": os.path.join(dest_dir, "error_log.txt")
    }

    for fname, target_path in standard_files.items():
        if os.path.exists(fname):
            if fname.endswith(".csv"):
                success, msg = migrate_csv_file(fname, target_path)
            else:
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    if not os.path.exists(target_path):
                        shutil.copy2(fname, target_path)
                        success, msg = True, f"Copied to '{target_path}'."
                    else:
                        success, msg = True, f"File already exists at '{target_path}'."
                except Exception as e:
                    success, msg = False, str(e)
            results[fname] = (success, msg)

    return results
