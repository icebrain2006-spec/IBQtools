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
        
        self.limit_keys = [
            "Cell 1 Gain", "Pack Gain", "Bat Gain",
            "Temp Gain", "Current Gain",
            "V_Cell 1", "V_Cell 2", "V_Cell 3", "V_Cell 4",
            "V_Bat", "V_Pack",
            "Int Temp", "TS1 Temp", "TS2 Temp", "TS3 Temp", "TS4 Temp",
            "CC Current"
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
        grid.addWidget(QLabel("<b>Min Value</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Max Value</b>"), 0, 2)
        
        for i, key in enumerate(self.limit_keys):
            row = i + 1
            lbl = QLabel(key)
            grid.addWidget(lbl, row, 0)
            
            # Default to the target value if it matches some common naming
            # or default to a wide range for gains
            default_min = ""
            default_max = ""
            
            if "Gain" in key:
                default_min = "0"
                default_max = "65535"
            else:
                # Voltage/Temp/Current default limits
                target_key = key.lower().replace(" ", "").replace("_", "")
                if "vcell" in target_key or "vpack" in target_key or "vbat" in target_key:
                    if "cell" in target_key:
                        default_min = str(self.default_targets.get("cell1mv", 3200))
                        default_max = default_min
                    elif "pack" in target_key:
                        default_min = str(self.default_targets.get("packmv", 12780))
                        default_max = default_min
                    elif "bat" in target_key:
                        default_min = str(self.default_targets.get("batmv", 12780))
                        default_max = default_min
                
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
                        new_lim[key] = (float(vmin_txt), float(vmax_txt))
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
