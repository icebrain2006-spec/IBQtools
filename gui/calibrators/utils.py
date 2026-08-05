import csv
import glob
import os

def detect_dataflash_offset(ic_name, version_hex, param_name="DA Configuration"):
    """
    Looks up the DataFlash offset from the matching CSV file.
    version_hex: e.g. 0x0402 -> looks for V4_02
    """
    major = version_hex >> 8
    minor = version_hex & 0xFF
    ver_str = f"V{major}_{minor:02d}"
    
    df_dir = os.path.join(os.path.dirname(__file__), "dataflashs")
    
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
        
    df_dir = os.path.join(os.path.dirname(__file__), "dataflashs")
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
