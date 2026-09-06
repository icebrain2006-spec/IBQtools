import os
import sys
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QSettings

from .calibration_mixins import (
    CustomHeader,
    CalibrationTableMixin,
    CalibrationChannelMixin,
    CalibrationUIMixin,
    CalibrationRunnerMixin,
)

class CalibrationTab(
    QWidget,
    CalibrationUIMixin,
    CalibrationChannelMixin,
    CalibrationTableMixin,
    CalibrationRunnerMixin
):
    """Main Calibration Tab orchestrating UI, channel selection, table rendering, and execution."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("IBQ", "IBQtools")
        self.dynamic_inputs = {}
        self.dynamic_checks = {}
        self.current_channel = 1

        self._init_ui()
        self.refresh_ports()
