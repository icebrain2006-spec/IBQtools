import sys

file_path = r"d:\WinApp\python\IBQtools\Reference_Data\BQU_BQ_VT0601.slfs"

max_w_len = 0
max_c_len = 0
max_w_line = ""

try:
    with open(file_path, "r") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if line.startswith("W:"):
                parts = line.split()
                # W: <addr> <reg> <data...> (sometimes just W: <addr> <data...>)
                # parts[0] is 'W:'
                payload_len = len(parts) - 1 # excluding 'W:'
                if payload_len > max_w_len:
                    max_w_len = payload_len
                    max_w_line = line
            elif line.startswith("C:"):
                parts = line.split()
                payload_len = len(parts) - 1
                if payload_len > max_c_len:
                    max_c_len = payload_len

    print(f"Max W: payload length: {max_w_len} bytes")
    print(f"Max C: payload length: {max_c_len} bytes")
    print(f"Example Max W: line: {max_w_line[:100]}...")
except Exception as e:
    print("Error:", e)
