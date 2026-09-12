"""CSV logging mixin for Auto Cycle & BQ Logger."""

import os
import csv
import time
from gui.tabs.auto_cycle_mixins.constants import SBS_COMMANDS, STATUS_REGISTERS


class CsvLoggerMixin:
    """Manages Raw and Summary CSV file output."""

    def init_csv_logging(self, file_path: str):
        """Prepares CSV files and writes headers if new."""
        self.csv_file_path = file_path
        if not file_path:
            return

        base, ext = os.path.splitext(file_path)
        self.summary_file_path = f"{base}_summary{ext or '.csv'}"
        
        # Write Raw CSV Header
        if not os.path.exists(self.csv_file_path) or os.path.getsize(self.csv_file_path) == 0:
            raw_headers = ["Time_ms", "Timestamp"] + list(SBS_COMMANDS.keys()) + ["Cell1", "Cell2", "Cell3", "Cell4"] + STATUS_REGISTERS
            try:
                with open(self.csv_file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(raw_headers)
            except Exception as e:
                if hasattr(self, 'append_log'):
                    self.append_log(f"Error initializing Raw CSV: {e}")

        # Write Summary CSV Header
        if not os.path.exists(self.summary_file_path) or os.path.getsize(self.summary_file_path) == 0:
            summary_headers = [
                "Time_ms", "Timestamp", "Voltage", "Current", "AverageCurrent",
                "Temperature", "RSOC", "RemainingCapacity", "FullChargeCapacity",
                "CycleCount", "Cell1", "Cell2", "Cell3", "Cell4",
                "VCT", "REST", "FD", "FC", "CUV", "Lstatus", "Step"
            ]
            try:
                with open(self.summary_file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(summary_headers)
            except Exception as e:
                if hasattr(self, 'append_log'):
                    self.append_log(f"Error initializing Summary CSV: {e}")

    def log_telemetry_to_csv(self, telemetry: dict, current_step: str = ""):
        """Appends one line of telemetry to both Raw and Summary CSVs."""
        if not hasattr(self, 'csv_file_path') or not self.csv_file_path:
            return

        t_now = telemetry.get("timestamp", time.time())
        t_ms = int(t_now * 1000)
        t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t_now))

        # 1. Append to Raw CSV
        raw_row = [t_ms, t_str]
        for key in SBS_COMMANDS.keys():
            raw_row.append(telemetry.get(key, ""))
        for cell_k in ["Cell1", "Cell2", "Cell3", "Cell4"]:
            raw_row.append(telemetry.get(cell_k, ""))
        for reg_k in STATUS_REGISTERS:
            val = telemetry.get(reg_k, "")
            raw_row.append(f"0x{val:02X}" if isinstance(val, int) else val)

        try:
            with open(self.csv_file_path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(raw_row)
        except Exception:
            pass

        # 2. Append to Summary CSV
        summary_row = [
            t_ms, t_str,
            telemetry.get("Voltage", ""),
            telemetry.get("Current", ""),
            telemetry.get("AverageCurrent", ""),
            telemetry.get("Temperature", ""),
            telemetry.get("RSOC", ""),
            telemetry.get("RemainingCapacity", ""),
            telemetry.get("FullChargeCapacity", ""),
            telemetry.get("CycleCount", ""),
            telemetry.get("Cell1", ""),
            telemetry.get("Cell2", ""),
            telemetry.get("Cell3", ""),
            telemetry.get("Cell4", ""),
            1 if telemetry.get("VCT") else 0,
            1 if telemetry.get("REST") else 0,
            1 if telemetry.get("FD") else 0,
            1 if telemetry.get("FC") else 0,
            1 if telemetry.get("CUV") else 0,
            telemetry.get("Lstatus", ""),
            current_step
        ]
        try:
            with open(self.summary_file_path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(summary_row)
        except Exception:
            pass
