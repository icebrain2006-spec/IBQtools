import os
import re
import sys
import subprocess

def find_version():
    main_c_path = os.path.join("firmware", "src", "main.c")
    if not os.path.exists(main_c_path):
        print(f"[Error] Could not find {main_c_path}")
        return None
        
    with open(main_c_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Look for: const char *version = "v1.0.22";
    match = re.search(r'const\s+char\s*\*\s*version\s*=\s*"([^"]+)"', content)
    if match:
        return match.group(1)
        
    print("[Error] Could not extract version from main.c")
    return None

def check_gh_cli():
    try:
        result = subprocess.run(["gh", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    return False

def main():
    print("=== GitHub Release Auto-Deploy Script ===")
    
    # 1. Parse Version
    version = find_version()
    if not version:
        sys.exit(1)
    
    print(f"Detected Firmware Version: {version}")
    
    # 2. Check UF2 file
    uf2_path = os.path.join("firmware", "build", "firmware.uf2")
    if not os.path.exists(uf2_path):
        print(f"[Error] UF2 file not found at {uf2_path}")
        print("Please build the firmware first!")
        sys.exit(1)
        
    print(f"Found firmware file: {uf2_path}")
    
    # 3. Check GitHub CLI
    if not check_gh_cli():
        print("\n[Error] GitHub CLI ('gh') is not installed or not in PATH.")
        print("Please download and install it from: https://cli.github.com/")
        print("After installing, run 'gh auth login' in terminal to authenticate.")
        sys.exit(1)
        
    # 4. Upload Release
    print(f"\nCreating GitHub Release for {version}...")
    
    cmd = [
        "gh", "release", "create", 
        version, 
        uf2_path, 
        "--repo", "icebrain2006-spec/IBQtools",
        "--title", f"Release {version}", 
        "--generate-notes"
    ]
    
    try:
        result = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr, text=True)
        if result.returncode == 0:
            print("\n[SUCCESS] Firmware uploaded to GitHub Releases successfully!")
        else:
            print(f"\n[ERROR] GitHub CLI returned error code {result.returncode}")
            print("Make sure you have run 'gh auth login' if you haven't already.")
    except Exception as e:
        print(f"\n[ERROR] Exception while running GitHub CLI: {e}")

if __name__ == "__main__":
    main()
