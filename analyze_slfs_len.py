import sys

file_path = r"d:\WinApp\python\IBQtools\Reference_Data\BQU_BQ_VT0601.slfs"

max_len = 0
try:
    with open(file_path, "r") as f:
        for idx, line in enumerate(f):
            if len(line) > max_len:
                max_len = len(line)
    print(f"Max line length (including newline): {max_len} bytes")
except Exception as e:
    print("Error:", e)
