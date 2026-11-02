import sys
import os
import glob
import csv
import math
import struct

def format_df4000_breakdown(df_bytes, label="0x4000 DF DUMP"):
    if not df_bytes or len(df_bytes) < 16:
        return f"    [{label}] Invalid/Short block (len={len(df_bytes) if df_bytes else 0})"
    
    # Address header (0x00 0x40) check
    if len(df_bytes) >= 18 and df_bytes[0] == 0x00 and df_bytes[1] == 0x40:
        base = 2
    else:
        base = 0
        
    c1_g = struct.unpack_from('<H', df_bytes, base)[0]
    bat_g = struct.unpack_from('<H', df_bytes, base + 2)[0]
    pack_g = struct.unpack_from('<H', df_bytes, base + 4)[0]
    cc_g = struct.unpack_from('<f', df_bytes, base + 6)[0]
    cap_g = struct.unpack_from('<f', df_bytes, base + 10)[0]
    
    c1_hex = bytes(df_bytes[base:base+2]).hex(' ')
    bat_hex = bytes(df_bytes[base+2:base+4]).hex(' ')
    pack_hex = bytes(df_bytes[base+4:base+6]).hex(' ')
    cc_hex = bytes(df_bytes[base+6:base+10]).hex(' ')
    cap_hex = bytes(df_bytes[base+10:base+14]).hex(' ')
    
    mohm = (3.714528 / cc_g) if cc_g != 0 else 0.0
    
    lines = [
        f"    [{label}]",
        f"    ├── Cell1 Gain : {c1_g:<5d} (0x{c1_g:04X})  [Hex: {c1_hex}]",
        f"    ├── Bat Gain   : {bat_g:<5d} (0x{bat_g:04X})  [Hex: {bat_hex}]",
        f"    ├── Pack Gain  : {pack_g:<5d} (0x{pack_g:04X})  [Hex: {pack_hex}]",
        f"    ├── CC Gain    : {cc_g:.6f} ({mohm:.3f} mOhm) [Hex: {cc_hex}]",
        f"    └── Cap Gain   : {cap_g:.3f}  [Hex: {cap_hex}]"
    ]
    return "\n".join(lines)

def float_to_xemics(v):
    if v == 0.0: return [0, 0, 0, 0]
    exp = int(math.floor(math.log(abs(v), 2))) + 1
    mant = int((abs(v) / (2**exp)) * (2**24))
    exp += 128
    b0 = exp
    b1 = (mant >> 16) & 0x7F
    if v < 0: b1 |= 0x80
    b2 = (mant >> 8) & 0xFF
    b3 = mant & 0xFF
    return [b0, b1, b2, b3]

def xemics_to_float(data):
    if not data or len(data) < 4: return 0.0
    b0, b1, b2, b3 = data[0], data[1], data[2], data[3]
    if b0 == 0 and b1 == 0 and b2 == 0 and b3 == 0: return 0.0
    exp = b0 - 128
    mant = (((b1 & 0x7F) | 0x80) << 16) | (b2 << 8) | b3
    v = (mant / (2**24)) * (2**exp)
    if b1 & 0x80: v = -v
    return v

def crc8_smbus_byte(crc, data):
    crc ^= data
    for _ in range(8):
        if crc & 0x80:
            crc = (crc << 1) ^ 0x07
        else:
            crc = (crc << 1)
        crc &= 0xFF
    return crc

def smbus_pec_calculate(data_bytes):
    crc = 0
    for b in data_bytes:
        crc = crc8_smbus_byte(crc, b)
    return crc

def get_dataflash_dir():
    if getattr(sys, 'frozen', False):
        base_meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        candidates = [
            os.path.join(base_meipass, "gui", "calibrators", "dataflashs"),
            os.path.join(base_meipass, "calibrators", "dataflashs"),
            os.path.join(os.path.dirname(sys.executable), "gui", "calibrators", "dataflashs"),
            os.path.join(os.path.dirname(sys.executable), "calibrators", "dataflashs"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
    return os.path.join(os.path.dirname(__file__), "dataflashs")

def detect_dataflash_offset(ic_name, version_hex, param_name="DA Configuration"):
    """
    Looks up the DataFlash offset from the matching CSV file.
    version_hex: e.g. 0x0402 -> looks for V4_02
    """
    major = version_hex >> 8
    minor = version_hex & 0xFF
    ver_str = f"V{major}_{minor:02d}"
    
    df_dir = get_dataflash_dir()
    
    # Clean IC name (e.g. BQ40Z50 -> bq40z50)
    ic = ic_name.lower()
    
    search_pattern = f"df_{ic}*{ver_str}.csv"
    matches = glob.glob(os.path.join(df_dir, search_pattern))
    
    if not matches:
        # Fallback to the latest/any available version for this IC
        fallback = glob.glob(os.path.join(df_dir, f"df_{ic}*.csv"))
        if fallback:
            matches = [sorted(fallback)[-1]]
            
    if not matches:
        return None, None
        
    csv_file = matches[0]
    
    # Parse CSV for the specific parameter
    with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) > 6:
                if row[2].strip() == param_name:
                    try:
                        offset = int(row[6].strip())
                        return offset, os.path.basename(csv_file)
                    except ValueError:
                        pass
    return None, os.path.basename(csv_file)

def load_calibration_offsets(csv_name):
    """
    Loads all relevant DataFlash offsets from the given CSV file.
    Returns a dictionary mapping parameter names to their offset relative to the block.
    """
    if not csv_name:
        return {}
        
    df_dir = get_dataflash_dir()
    csv_file = os.path.join(df_dir, csv_name)
    
    if not os.path.exists(csv_file):
        return {}
        
    offsets = {}
    with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) > 6:
                param_name = row[2].strip()
                try:
                    offsets[param_name] = int(row[6].strip())
                except ValueError:
                    pass
    return offsets



def write_calibration_log_file(path, ch, serial_num, mfg_date, ch_data, overall_success):
    """Writes calibration log results to CSV file."""
    if not path or not ch_data:
        return
    import csv
    from datetime import datetime

    dir_name = os.path.dirname(os.path.abspath(path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    params = list(ch_data.keys())
    header_row1 = ["Timestamp", "Serial Number", "Manufacture Date"] + params + ["Overall Result"]
    header_row2 = ["", "", ""] + [ch_data[p]['range'] for p in params] + [""]
    data_row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), serial_num, mfg_date] + [ch_data[p]['value'] for p in params] + ["PASS" if overall_success else "FAIL"]
    
    write_header = False
    if not os.path.exists(path):
        write_header = True
    else:
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = list(csv.reader(f))
                last_ranges = None
                for row in reversed(reader):
                    if len(row) > 3 and row[0] == "" and row[1] == "":
                        last_ranges = row
                        break
                if last_ranges != header_row2:
                    write_header = True
        except Exception:
            write_header = True
            
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                writer.writerow([])
            writer.writerow(header_row1)
            writer.writerow(header_row2)
        writer.writerow(data_row)

    # Cloud Google Sheet Sync
    try:
        from gui.config import config
        from gui.gsheet_logger import send_to_google_sheet_async
        if config.get_gsheet_logging_en():
            webhook_url = config.get_gsheet_webhook_url()
            if webhook_url:
                send_to_google_sheet_async(webhook_url, "cal_log", data_row)
    except Exception as e:
        import logging
        logging.getLogger('IBQtools').warning(f"Google Sheet cal hook error: {e}")
