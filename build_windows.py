import os
import sys
import subprocess
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'gui')))
from version import __version__

def build_app():
    print("Cleaning previous builds...")
    for dir_name in ['build', 'dist']:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)

    args = [
        'gui/main.py',
        '--name=IBQtools',
        '--windowed',       # Hide console
        '--noconfirm',
        '--icon=gui/app_icon.ico',
        '--clean',
        
        # Windows separator for --add-data is ';'
        '--add-data=gui/app_icon.png;.',
        '--add-data=gui/style.qss;.',
        '--add-data=gui/BQ_Information.csv;.',
        '--add-data=gui/calibrators/scripts/*;calibrators/scripts',
        '--add-data=gui/calibrators/scripts/*;gui/calibrators/scripts',
        '--add-data=gui/calibrators/dataflashs/*;calibrators/dataflashs',
        '--add-data=gui/calibrators/dataflashs/*;gui/calibrators/dataflashs',
    ]
    
    print(f"Running PyInstaller...")
    subprocess.run(['uv', 'run', 'pyinstaller'] + args, check=True)
    
    print("Copying assets folder to dist/IBQtools...")
    dist_assets = os.path.join('dist', 'IBQtools', 'assets')
    if os.path.exists(dist_assets):
        shutil.rmtree(dist_assets)
    shutil.copytree('assets', dist_assets)
    
    print("Zipping the distribution folder...")
    zip_name = f'IBQtools_Release_v{__version__}'
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
