import os
import sys
import json
import glob

def load_ic_configs():
    """Dynamically loads all IC configuration JSON files from the models directory."""
    if getattr(sys, 'frozen', False):
        base_meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        candidates = [
            os.path.join(base_meipass, "gui", "models"),
            os.path.join(base_meipass, "models"),
            os.path.join(os.path.dirname(sys.executable), "gui", "models"),
            os.path.join(os.path.dirname(sys.executable), "models"),
        ]
        models_dir = os.path.dirname(os.path.abspath(__file__))
        for c in candidates:
            if os.path.exists(c):
                models_dir = c
                break
    else:
        models_dir = os.path.dirname(os.path.abspath(__file__))
        
    configs = {}
    json_files = glob.glob(os.path.join(models_dir, "*.json"))
    for json_file in sorted(json_files):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                ic_name = data.get("name")
                if ic_name:
                    configs[ic_name] = data
                else:
                    print(f"[Warning] Missing 'name' field in model JSON: {json_file}")
        except Exception as e:
            print(f"[Warning] Failed to parse model JSON '{json_file}': {e}")
            
    return configs

IC_CONFIGS = load_ic_configs()

def get_ic_config(ic_name):
    """Helper to retrieve a specific IC configuration dict by name."""
    return IC_CONFIGS.get(ic_name)
