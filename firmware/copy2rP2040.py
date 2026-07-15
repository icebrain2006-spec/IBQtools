import argparse
import shutil
import os

def copy_uf2(drive_letter):
    # Normalize drive letter to Windows format, e.g. "I:\"
    drive = drive_letter.strip().upper()
    if not drive.endswith(":"):
        drive += ":"
    
    # Check if target drive directory exists
    target_dir = drive + "\\"
    if not os.path.exists(target_dir):
        print(f"Error: Target drive '{target_dir}' does not exist or is not mounted.")
        print("Please check if RP2040 is in BOOTSEL mode and mounted under this letter.")
        return False
        
    # Get current script path to locate build/firmware.uf2
    base_dir = os.path.dirname(os.path.abspath(__file__))
    uf2_source = os.path.join(base_dir, "build", "firmware.uf2")
    
    if not os.path.exists(uf2_source):
        print(f"Error: Source file '{uf2_source}' not found. Did you build the project first?")
        return False
        
    uf2_dest = os.path.join(target_dir, "firmware.uf2")
    
    print(f"Copying '{uf2_source}' to '{uf2_dest}'...")
    try:
        shutil.copy(uf2_source, uf2_dest)
        print("Copy successful! RP2040 should reboot automatically now.")
        return True
    except Exception as e:
        print(f"Failed to copy file: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Copy firmware.uf2 to RP2040 BOOTSEL drive")
    parser.add_argument("-drive", required=True, help="Drive letter of RP2040 (e.g. i or I)")
    
    args = parser.parse_args()
    copy_uf2(args.drive)

if __name__ == "__main__":
    main()
