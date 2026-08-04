import os
import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, 
    QLineEdit, QPushButton, QScrollArea, QWidget, QHBoxLayout
)
from PySide6.QtCore import QSettings, Qt

class LimitsDialog(QDialog):
    def __init__(self, ic_name, default_targets, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle(f"Calibration Limits - {ic_name}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        self.ic_name = ic_name
        self.settings = settings if settings else QSettings("IBQ", "IBQtools")
        self.default_targets = default_targets
        
        if "BQ78350" in self.ic_name.upper():
            self.limit_keys = [
                "Cell 1 Offset", "Cell 2 Offset", "Cell 3 Offset", "Cell 4 Offset",
                "Cell 5 Offset", "Cell 6 Offset", "Cell 7 Offset", "Cell 8 Offset",
                "Cell 9 Offset", "Cell 10 Offset", "Cell 11 Offset", "Cell 12 Offset",
                "Cell 13 Offset", "Cell 14 Offset", "Cell 15 Offset",
                "Ext Cell Divider Gain",
                "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4", "V_Cell 5", "V_Cell 6",
                "V_Cell 7", "V_Cell 8", "V_Cell 9", "V_Cell 10", "V_Cell 11", "V_Cell 12",
                "V_Cell 13", "V_Cell 14", "V_Cell 15",
                "V_Ext", "V_Aux",
                "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp",
                "CC Offset", "Coulomb Counter Offset Samples", "Shunt Resistor"
            ]
        else:
            self.limit_keys = [
                "Cell 1 Gain", "Pack Gain", "Bat Gain",
                "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4",
                "V_Bat", "V_Pack",
                "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp",
                "Shunt Resistor"
            ]
        
        self.inputs = {}
        
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        grid = QGridLayout(content_widget)
        
        # Headers
        grid.addWidget(QLabel("<b>Parameter</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Min (or -Offset)</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Max (or +Offset)</b>"), 0, 2)
        
        for i, key in enumerate(self.limit_keys):
            row = i + 1
            lbl = QLabel(key)
            grid.addWidget(lbl, row, 0)
            
            # Default to the target value if it matches some common naming
            # or default to a wide range for gains
            default_min = ""
            default_max = ""
            
            if "Gain" in key and not "Ext Cell" in key:
                default_min = "0"
                default_max = "65535"
            elif "Gain" in key and "Ext Cell" in key:
                default_min = "0"
                default_max = "65535"
            elif "Offset" in key:
                if "Coulomb" in key:
                    default_min = "-100"
                    default_max = "100"
                else:
                    default_min = "-128"
                    default_max = "127"
            else:
                # Voltage/Temp default limits (from targets)
                target_key = key.lower().replace(" ", "").replace("_", "")
                if "shunt" in target_key:
                    default_min = "-0.05"
                    default_max = "0.05"
                elif "vcell" in target_key or "vpack" in target_key or "vbat" in target_key or "vext" in target_key or "vaux" in target_key:
                    default_min = "-20"
                    default_max = "20"
                elif "temp" in target_key:
                    default_min = "-1.0"
                    default_max = "1.0"
                
            saved_min = self.settings.value(f"limit_{self.ic_name}_{key}_min", default_min)
            saved_max = self.settings.value(f"limit_{self.ic_name}_{key}_max", default_max)
            
            edit_min = QLineEdit(str(saved_min))
            edit_max = QLineEdit(str(saved_max))
            
            self.inputs[key] = (edit_min, edit_max)
            
            # --- LIVE UPDATE INJECTION ---
            def make_live_updater(k, emin, emax):
                pass
            # -----------------------------
            
            grid.addWidget(edit_min, row, 1)
            grid.addWidget(edit_max, row, 2)
            
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save && Close")
        btn_save.clicked.connect(self.save_and_close)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)
        
    def accept(self):
        try:
            # Rebuild limits dict from current thread if it exists
            new_lim = None
            if hasattr(self.parent(), 'cal_thread') and self.parent().cal_thread:
                new_lim = dict(self.parent().cal_thread.limits)
                
            for key, (edit_min, edit_max) in self.inputs.items():
                vmin_txt = edit_min.text().strip()
                vmax_txt = edit_max.text().strip()
                self.settings.setValue(f"limit_{self.ic_name}_{key}_min", vmin_txt)
                self.settings.setValue(f"limit_{self.ic_name}_{key}_max", vmax_txt)
                
                # Update background thread dynamically if running
                if new_lim is not None:
                    try:
                        v_min = float(vmin_txt)
                        v_max = float(vmax_txt)
                        
                        base_target = 0
                        is_offset = False
                        if "Gain" not in key and "Offset" not in key or "CC Offset" in key or "Coulomb" in key:
                            is_offset = True
                            target_key = key.lower().replace(" ", "").replace("_", "")
                            if "shunt" in target_key:
                                base_target = float(self.default_targets.get("shuntresistormohm", 1.0))
                            elif "vcell" in target_key:
                                # extract cell index
                                import re
                                m = re.search(r'vcell(\d+)', target_key)
                                if m:
                                    cell_idx = m.group(1)
                                    base_target = float(self.default_targets.get(f"cell{cell_idx}mv", 3200))
                                else:
                                    base_target = float(self.default_targets.get("cell1mv", 3200))
                            elif "vpack" in target_key:
                                base_target = float(self.default_targets.get("packmv", 12780))
                            elif "vbat" in target_key:
                                base_target = float(self.default_targets.get("batmv", 12780))
                            elif "vext" in target_key:
                                base_target = float(self.default_targets.get("extaveragecellmv", 3200))
                            elif "vaux" in target_key:
                                base_target = float(self.default_targets.get("vauxmv", 3200))
                            elif "temp" in target_key:
                                if "int" in target_key:
                                    base_target = float(self.default_targets.get("inttempc", 25.0))
                                elif "ts1" in target_key:
                                    base_target = float(self.default_targets.get("ts1tempc", 25.0))
                                elif "ts2" in target_key:
                                    base_target = float(self.default_targets.get("ts2tempc", 25.0))
                                elif "ts3" in target_key:
                                    base_target = float(self.default_targets.get("ts3tempc", 25.0))
                                elif "ts4" in target_key:
                                    base_target = float(self.default_targets.get("ts4tempc", 25.0))
                            elif "ccoffset" in target_key or "coulomb" in target_key:
                                is_offset = False # these are pure limits, not offsets from a target in the UI!
                                
                        if "Offset" in key and "Cell" in key:
                            is_offset = False # Offsets calculated in chip are saved as pure values in limits, e.g. -2 to +2

                                    
                        if is_offset:
                            new_lim[key] = (base_target + v_min, base_target + v_max)
                        else:
                            new_lim[key] = (v_min, v_max)
                    except ValueError:
                        pass
                        
            if new_lim is not None:
                self.parent().cal_thread.limits = new_lim
                self.parent().log("DEBUG: Updated limits on Save & Close.")
                
            # Force flush to registry so CalibrationTab can instantly read it
            self.settings.sync()
            self.setResult(1) # Force Accepted
            super().accept()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error in accept", str(e))
        
    def save_and_close(self):
        self.accept()
