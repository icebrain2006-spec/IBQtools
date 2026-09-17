import os
import sys
import subprocess
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'gui')))
from version import __version__

def increment_gui_version():
    version_file = os.path.join(os.path.dirname(__file__), 'gui', 'version.py')
    if not os.path.exists(version_file):
        return "1.4.00"
    
    with open(version_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    import re
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        return "1.4.00"
        
    old_ver = match.group(1)
    parts = old_ver.split('.')
    
    if len(parts) == 2:
        major_minor = f"{parts[0]}.{parts[1]}"
        build_num = 1
    elif len(parts) >= 3:
        major_minor = f"{parts[0]}.{parts[1]}"
        try:
            build_num = int(parts[2]) + 1
        except ValueError:
            build_num = 1
    else:
        major_minor = "1.4"
        build_num = 1
        
    new_ver = f"{major_minor}.{build_num:02d}"
    
    new_content = re.sub(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        f'__version__ = "{new_ver}"',
        content
    )
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print(f"[*] GUI Version incremented: {old_ver} -> {new_ver}")
    return new_ver

FAST_BUILD = True  # Set to False (or run with --clean) for full clean release builds

def build_app():
    is_clean = "--clean" in sys.argv or not FAST_BUILD
    current_ver = increment_gui_version()
    
    if is_clean:
        print("Cleaning previous builds (Clean Build Mode)...")
        for dir_name in ['build', 'dist']:
            if os.path.exists(dir_name):
                shutil.rmtree(dir_name)
    else:
        print("[*] Running FAST Incremental Build (reusing PyInstaller cache)...")

    args = [
        'main.py',
        '--name=IBQtools',
        '--windowed',       # Hide console
        '--noconfirm',
        '--icon=gui/app_icon.ico',
        '--paths=.',
        '--paths=gui',
        
        # Windows separator for --add-data is ';'
        '--add-data=gui/app_icon.png;.',
        '--add-data=gui/app_icon.png;gui',
        '--add-data=gui/style.qss;.',
        '--add-data=gui/style.qss;gui',
        '--add-data=gui/BQ_Information.csv;.',
        '--add-data=gui/BQ_Information.csv;gui',
        '--add-data=gui/calibrators/dataflashs/*;calibrators/dataflashs',
        '--add-data=gui/calibrators/dataflashs/*;gui/calibrators/dataflashs',
        '--add-data=gui/models/*;models',
        '--add-data=gui/models/*;gui/models',
        '--add-data=gui/assets/wav/*;assets/wav',
        '--add-data=gui/assets/wav/*;gui/assets/wav',
    ]
    if is_clean:
        args.append('--clean')
    
    print(f"Running PyInstaller...")
    subprocess.run(['uv', 'run', 'pyinstaller'] + args, check=True)
    
    print("Copying assets folder to dist/IBQtools...")
    dist_assets = os.path.join('dist', 'IBQtools', 'assets')
    if os.path.exists(dist_assets):
        shutil.rmtree(dist_assets)
    shutil.copytree(os.path.join('gui', 'assets'), dist_assets)
    
    print("Zipping the distribution folder...")
    zip_name = f'IBQtools_Release_v{current_ver}'
    zip_file = f'{zip_name}.zip'
    if os.path.exists(zip_file):
        os.remove(zip_file)
        
    shutil.make_archive(zip_name, 'zip', root_dir='dist', base_dir='IBQtools')
    print(f"Successfully created {zip_file}!")

    # Network drive Y: auto copy
    y_drive = 'Y:\\'
    if os.path.exists(y_drive):
        try:
            dest_path = os.path.join(y_drive, zip_file)
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            shutil.copy2(zip_file, dest_path)
            print(f"[+] Automatically copied {zip_file} to network drive Y:\\ ({dest_path})")
        except Exception as e:
            print(f"[!] Warning: Failed to copy zip to Y:\\ drive: {e}")
    else:
        print("[!] Note: Network drive Y:\\ was not detected. Skipping Y:\\ auto copy.")

if __name__ == '__main__':
    build_app()
