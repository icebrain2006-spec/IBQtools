import sys
import os
import glob
import csv

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

def load_adc_offset_0xf081(ic_name="BQ40Z50"):
    import json
    df_dir = get_dataflash_dir()
    json_path = os.path.join(df_dir, "adc_offset_0xf081.json")
    if not os.path.exists(json_path):
        json_path = os.path.join(os.path.dirname(__file__), "adc_offset_0xf081.json")
    
    defaults = {"min_len": 16, "current": 2, "cell1": 4, "cell2": 6, "cell3": 8, "cell4": 10, "pack": 12, "bat": 14}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get(ic_name.upper(), defaults)
        except Exception:
            pass
    return defaults

def load_dastatus1_offset_0x0071(ic_name="BQ40Z50"):
    import json
    df_dir = get_dataflash_dir()
    json_path = os.path.join(df_dir, "dastatus1_offset_0x0071.json")
    if not os.path.exists(json_path):
        json_path = os.path.join(os.path.dirname(__file__), "dastatus1_offset_0x0071.json")
    
    defaults = {"min_len": 34, "cell1": 2, "cell2": 4, "cell3": 6, "cell4": 8, "bat": 10, "pack": 12}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get(ic_name.upper(), defaults)
        except Exception:
            pass
    return defaults

def load_dastatus2_offset_0x0072(ic_name="BQ40Z50"):
    import json
    df_dir = get_dataflash_dir()
    json_path = os.path.join(df_dir, "dastatus2_offset_0x0072.json")
    if not os.path.exists(json_path):
        json_path = os.path.join(os.path.dirname(__file__), "dastatus2_offset_0x0072.json")
    
    defaults = {"min_len": 30, "int_temp": 2, "ts1_temp": 4, "ts2_temp": 6, "ts3_temp": 8, "ts4_temp": 10}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get(ic_name.upper(), defaults)
        except Exception:
            pass
    return defaults
