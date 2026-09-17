import time
import os
import sys
from PySide6.QtCore import Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox

from gui.calibrators.calib_multi_runner import MultiCalibrationThread
from gui.models import IC_CONFIGS


class MultiCalibrationRunnerMixin:
    """Mixin for port refresh, 18-ch log console outputs, calibration thread initialization, audio playback, and finish handlers."""

    def log(self, msg):
        msg_lower = msg.lower()
        is_important = (
            "error" in msg_lower or 
            "warning" in msg_lower or 
            "crash" in msg_lower or 
            "---" in msg or 
            "calibration finished" in msg_lower or 
            "calibration failed" in msg_lower or
            "[time]" in msg_lower
        )
        
        if "error" in msg_lower or "crash" in msg_lower:
            from gui.config import log_error
            log_error(f"[Calibration18CH] {msg}")
            
        from gui.config import config
        if config.settings.value("global_debug_log_en", "false") != "true":
            if not is_important:
                return

        timestamp = time.strftime("%H:%M:%S")
        if "error" in msg_lower or "fail" in msg_lower or "crash" in msg_lower:
            self.log_console.append(f'<span style="color: #FF4444;">[{timestamp}] {msg}</span>')
        elif "finished successfully" in msg_lower:
            self.log_console.append(f'<span style="color: #00E676;">[{timestamp}] {msg}</span>')
        else:
            self.log_console.append(f"[{timestamp}] {msg}")

    @Slot(str)
    def on_start_calib(self, mode):
        if hasattr(self, 'cal_thread') and self.cal_thread and self.cal_thread.isRunning():
            self.cal_thread.stop()
            self.cal_thread.wait()

        ports_map = {
            1: self.combo_port_1.currentText(),
            2: self.combo_port_2.currentText(),
            3: self.combo_port_3.currentText()
        }
        
        valid_ports = [p for p in ports_map.values() if p and "Select" not in p and p != "None"]
        if not valid_ports:
            self.log("Error: Please select at least one valid COM port for Board #1, #2, or #3.")
            return

        ic = self.combo_ic.currentText()
        if ic not in IC_CONFIGS:
            self.log("Error: IC configuration not found.")
            return
            
        config = IC_CONFIGS[ic]
        self._save_current_channel_inputs()
        
        all_defaults = {}
        for section in ["voltage", "temperature", "current"]:
            if section in config and config[section]:
                all_defaults.update(config[section])
                
        targets_per_ch = {}
        for ch in range(1, 19):
            ch_targets = {}
            for key, default_data in all_defaults.items():
                global_fallback = self.settings.value(f"calib_{ic}_{key}_val", default_data["val"] if isinstance(default_data, dict) else default_data)
                val = self.settings.value(f"calib_multi_ch{ch}_{ic}_{key}_val", global_fallback)
                val_str = str(val).strip() if val is not None else ""
                if val_str:
                    try:
                        safe_key = "".join(e for e in key if e.isalnum()).lower()
                        parsed_val = float(val_str) if '.' in val_str else int(val_str)
                        ch_targets[safe_key] = parsed_val
                        ch_targets[key] = parsed_val
                    except ValueError:
                        pass
                if isinstance(default_data, dict) and default_data.get("check"):
                    global_chk_fallback = self.settings.value(f"calib_{ic}_{key}_chk", "true")
                    chk_val = self.settings.value(f"calib_multi_ch{ch}_{ic}_{key}_chk", global_chk_fallback)
                    safe_key = "".join(e for e in key if e.isalnum()).lower() + "_en"
                    ch_targets[safe_key] = (str(chk_val).lower() == "true")
            ch_targets["run_mode"] = mode
            targets_per_ch[ch] = ch_targets

        targets = targets_per_ch.get(self.current_channel, {}).copy()
        targets["per_ch"] = targets_per_ch
        targets["run_mode"] = mode
        
        relay_delay_str = str(self.settings.value("calib_relay_delay_ms", "300")).strip()
        try:
            relay_delay_val = float(relay_delay_str)
        except ValueError:
            relay_delay_val = 300.0
        targets["relay_delay_ms"] = relay_delay_val
        for ch in range(1, 19):
            if ch in targets_per_ch:
                targets_per_ch[ch]["relay_delay_ms"] = relay_delay_val
        
        selected_channels = sorted(list(self.selected_channels))
        if not selected_channels:
            QMessageBox.warning(self, "No Channels", "Please select at least one channel to calibrate.")
            return

        self.log_console.clear()
        self.log(f"Starting 18-Channel {ic} calibration ({mode} mode)... Active Channels: {len(selected_channels)}")
        self.table_data.clearContents()
        self.table_data.setRowCount(0)
        
        for c in range(1, 19):
            item = self.table_overall.item(0, c)
            if item:
                item.setText("")
                item.setBackground(QColor("#2b2b2b"))
                
        self.param_statuses = {}
        self.settings.sync()
        
        if "BQ78350" in ic.upper():
            limit_keys = [
                "Cell 1 Offset", "Cell 2 Offset", "Cell 3 Offset", "Cell 4 Offset",
                "Cell 5 Offset", "Cell 6 Offset", "Cell 7 Offset", "Cell 8 Offset",
                "Cell 9 Offset", "Cell 10 Offset", "Cell 11 Offset", "Cell 12 Offset",
                "Cell 13 Offset", "Cell 14 Offset", "Cell 15 Offset",
                "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4", "V_Cell 5", "V_Cell 6",
                "V_Cell 7", "V_Cell 8", "V_Cell 9", "V_Cell 10", "V_Cell 11", "V_Cell 12",
                "V_Cell 13", "V_Cell 14", "V_Cell 15",
                "V_Ext", "V_Aux",
                "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp",
                "CC Offset", "Shunt Resistor"
            ]
        else:
            limit_keys = [
                "Cell 1 Gain", "Bat Gain", "Pack Gain", "CC Gain", "Capacity Gain",
                "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4",
                "V_Bat", "V_Pack", "V_Pack - V_Bat Diff",
                "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp",
                "Shunt Resistor"
            ]
        
        limits_per_ch = {}
        for ch in range(1, 19):
            ch_t = targets_per_ch.get(ch, {})
            ch_limits = {}
            for key in limit_keys:
                default_min = ""
                default_max = ""
                base_target = 0
                is_offset = False
                
                if key in ["Cell 1 Gain", "Bat Gain", "Pack Gain", "CC Gain", "Capacity Gain"]:
                    default_min = "0"
                    default_max = "1000000"
                else:
                    is_offset = True
                    target_key = key.lower().replace(" ", "").replace("_", "")
                    if "diff" in target_key:
                        is_offset = False
                        default_min = "-20"
                        default_max = "20"
                    elif "shunt" in target_key:
                        base_target = float(ch_t.get("shuntresistormohm", 1.0))
                        default_min = "-0.05"
                        default_max = "0.05"
                    elif "vcell" in target_key or "vpack" in target_key or "vbat" in target_key:
                        default_min = "-20"
                        default_max = "20"
                        if "cell" in target_key:
                            base_target = float(ch_t.get("cell1mv", 3200))
                        elif "pack" in target_key:
                            base_target = float(ch_t.get("packmv", 12780))
                        elif "bat" in target_key:
                            base_target = float(ch_t.get("batmv", 12780))
                    elif "temp" in target_key:
                        default_min = "-1.0"
                        default_max = "1.0"
                        if "int" in target_key:
                            base_target = float(ch_t.get("inttempc", 25.0))
                        elif "ts1" in target_key:
                            base_target = float(ch_t.get("ts1tempc", 25.0))
                        elif "ts2" in target_key:
                            base_target = float(ch_t.get("ts2tempc", 25.0))
                        elif "ts3" in target_key:
                            base_target = float(ch_t.get("ts3tempc", 25.0))
                        elif "ts4" in target_key:
                            base_target = float(ch_t.get("ts4tempc", 25.0))

                l_min = self.settings.value(f"limit_{ic}_{key}_min", default_min)
                l_max = self.settings.value(f"limit_{ic}_{key}_max", default_max)
                
                if l_min != "" and l_max != "":
                    try:
                        v_min = float(l_min)
                        v_max = float(l_max)
                        if is_offset:
                            if key == "Shunt Resistor":
                                ch_limits["CC Gain"] = (base_target + v_min, base_target + v_max)
                                ch_limits["Capacity Gain"] = (base_target + v_min, base_target + v_max)
                                ch_limits["Shunt Resistor"] = (base_target + v_min, base_target + v_max)
                            else:
                                ch_limits[key] = (base_target + v_min, base_target + v_max)
                        else:
                            ch_limits[key] = (v_min, v_max)
                    except ValueError:
                        pass
            limits_per_ch[ch] = ch_limits

        limits = limits_per_ch.get(self.current_channel, {})
        
        try:
            self.cal_thread = MultiCalibrationThread(ports_map, selected_channels, targets, ic, limits, limits_per_ch)
        except Exception as e:
            self.log(f"Error initializing MultiCalibrationThread: {e}")
            return
            
        self.cal_thread.log_signal.connect(self.log)
        self.cal_thread.row_signal.connect(self.update_or_add_table_row)
        self.cal_thread.clear_ch_signal.connect(self.clear_table_column)
        self.cal_thread.play_sound_signal.connect(self.play_sound)
        self.cal_thread.finished_signal.connect(self.on_calib_finished)
        self.cal_thread.start()

    @Slot(bool)
    def play_sound(self, success):
        import winsound
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            ref_dir = os.path.join(base_dir, "assets", "wav")
            wav_path = os.path.join(ref_dir, "testComplete.wav" if success else "testFail.wav")
            if os.path.exists(wav_path):
                winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.Beep(880 if success else 350, 150)
        except Exception:
            pass

    @Slot(bool)
    def on_calib_finished(self, success):
        self.btn_cal_v.setEnabled(True)
        self.btn_cal_t.setEnabled(True)
        self.btn_cal_c.setEnabled(True)
        self.btn_cal_all.setEnabled(True)
        if success:
            self.log("18-Channel Calibration Sequence Fully Completed.")
        else:
            self.log("18-Channel Calibration failed or was aborted.")
