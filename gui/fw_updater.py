import urllib.request
import json
import os
import shutil
import tempfile

def get_latest_github_release(repo):
    """
    Fetches the latest release from a GitHub repo (e.g. 'owner/repo').
    Returns a tuple (tag_name, uf2_download_url) or (None, None) if not found/error.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                tag_name = data.get("tag_name", "Unknown")
                assets = data.get("assets", [])
                
                uf2_url = None
                for asset in assets:
                    if asset.get("name", "").endswith(".uf2"):
                        uf2_url = asset.get("browser_download_url")
                        break
                        
                return tag_name, uf2_url
    except Exception as e:
        print(f"Error fetching github release: {e}")
        
    return None, None

def download_file(url, dest_path):
    """
    Downloads a file from url to dest_path. Returns True if successful.
    """
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response, open(dest_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        return True
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False

def find_rp2040_drive():
    """
    Scans Windows drives A-Z for the RP2040 BOOTSEL drive.
    It identifies it by looking for the 'INFO_UF2.TXT' file.
    Returns the drive string (e.g. 'D:\\') or None.
    """
    import string
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        # Skip checking A and B to avoid floppy drive hangs
        if letter in ['A', 'B']:
            continue
            
        if os.path.exists(drive):
            uf2_info = os.path.join(drive, "INFO_UF2.TXT")
            if os.path.exists(uf2_info):
                return drive
    return None
