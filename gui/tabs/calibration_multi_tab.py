import os
import sys
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QSettings

from .calibration_multi_mixins import (
    CustomHeader,
    MultiCalibrationTableMixin,
    MultiCalibrationChannelMixin,
    MultiCalibrationUIMixin,
    MultiCalibrationRunnerMixin,
)

class CalibrationMultiTab(
    QWidget,
    MultiCalibrationUIMixin,
    MultiCalibrationChannelMixin,
    MultiCalibrationTableMixin,
    MultiCalibrationRunnerMixin
):
    """18-Channel Multi-RP2040 Calibration Tab orchestrating UI, 3 COM ports, 18-ch table rendering, and execution."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("IBQ", "IBQtools")
        self.dynamic_inputs = {1: {}, 2: {}, 3: {}}
        self.dynamic_checks = {1: {}, 2: {}, 3: {}}
        self.board_current_ch = {1: 1, 2: 7, 3: 13}

        self._init_ui()
        self.refresh_ports()
