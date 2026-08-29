import os
import re
import sys
import subprocess

def increment_version():
    main_c_path = os.path.join("firmware_rp2040", "src", "main.c")
    if not os.path.exists(main_c_path):
        print(f"[Error] Could not find {main_c_path}")
        return None
        
    with open(main_c_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Find the version string: const char *version = "v1.0.27";
    pattern = r'(const\s+char\s*\*\s*version\s*=\s*"v)(\d+)\.(\d+)\.(\d+)(";\s*)'
    match = re.search(pattern, content)
    if not match:
        print("[Error] Could not extract version from main.c")
        return None
        
    major = int(match.group(2))
    minor = int(match.group(3))
    patch = int(match.group(4))
    
    new_patch = patch + 1
    new_version_str = f"v{major}.{minor}.{new_patch}"
    
    new_content = content[:match.start()] + match.group(1) + f"{major}.{minor}.{new_patch}" + match.group(5) + content[match.end():]
    
    with open(main_c_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print(f"[*] Firmware version incremented to {new_version_str}")
    return new_version_str

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
    
    # 1. Parse & Increment Version
    version = increment_version()
    if not version:
        sys.exit(1)
        
    # 2. Build firmware via make_uf2.py
    print("\n[*] Building firmware via make_uf2.py...")
    firmware_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firmware_rp2040')
    build_res = subprocess.run(["uv", "run", "python", "make_uf2.py"], cwd=firmware_dir, shell=True)
    if build_res.returncode != 0:
        print("[!] Build failed. Aborting Git commit and Release.")
        sys.exit(1)
    
    uf2_path = os.path.join("firmware_rp2040", "build", "firmware.uf2")
    if not os.path.exists(uf2_path):
        print(f"[Error] UF2 file not found at {uf2_path}")
        sys.exit(1)
        
    print(f"[*] Found built firmware file: {uf2_path}")
    
    # 3. Git Commit and Push
    print("\n[*] Committing changes to git...")
    subprocess.run(["git", "add", "firmware_rp2040/"], shell=True)
    subprocess.run(["git", "commit", "-m", f"Auto-build and release firmware {version}"], shell=True)
    
    print("[*] Pushing to remote repository...")
    push_res = subprocess.run(["git", "push", "-u", "origin", "HEAD"], shell=True)
    if push_res.returncode != 0:
        print("[!] Git push failed. You may need to resolve remote issues before GitHub release.")
        # Proceeding anyway as GitHub release might still work if branch exists remotely
    else:
        print("[+] Git push successful.")

    # 4. Check GitHub CLI
    if not check_gh_cli():
        print("\n[Error] GitHub CLI ('gh') is not installed or not in PATH.")
        print("Please download and install it from: https://cli.github.com/")
        print("After installing, run 'gh auth login' in terminal to authenticate.")
        sys.exit(1)
        
    # 5. Upload Release via GitHub CLI
    print(f"\n[*] Creating GitHub Release for {version}...")
    
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
            print(f"\n[SUCCESS] Firmware {version} uploaded to GitHub Releases successfully!")
        else:
            print(f"\n[ERROR] GitHub CLI returned error code {result.returncode}")
            print("Make sure you have run 'gh auth login' if you haven't already.")
    except Exception as e:
        print(f"\n[ERROR] Exception while running GitHub CLI: {e}")

if __name__ == "__main__":
    main()
