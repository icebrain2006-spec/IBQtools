import os
import sys
import subprocess
import shutil

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
        '--add-data=gui/calibrators/dataflashs/*;calibrators/dataflashs',
    ]
    
    print(f"Running PyInstaller...")
    subprocess.run(['uv', 'run', 'pyinstaller'] + args, check=True)
    
    print("Copying assets folder to dist/IBQtools...")
    dist_assets = os.path.join('dist', 'IBQtools', 'assets')
    if os.path.exists(dist_assets):
        shutil.rmtree(dist_assets)
    shutil.copytree('assets', dist_assets)
    
    print("Zipping the distribution folder...")
    if os.path.exists('IBQtools_Release_v1.0.zip'):
        os.remove('IBQtools_Release_v1.0.zip')
        
    shutil.make_archive('IBQtools_Release_v1.0', 'zip', 'dist/IBQtools')
    print("Successfully created IBQtools_Release_v1.0.zip!")

if __name__ == '__main__':
    build_app()
