"""Auto Cycle & BQ Logger Tab main widget."""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal

from gui.tabs.auto_cycle_mixins import (
    UiMixin, StateMachineMixin, TableMixin,
    CsvLoggerMixin, RunnerMixin
)


class AutoCycleTab(QWidget, UiMixin, StateMachineMixin, TableMixin, CsvLoggerMixin, RunnerMixin):
    """Main tab component for Auto Cycle & BQ Logger."""

    lock_tabs_requested = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def closeEvent(self, event):
        """Clean up background worker when closed."""
        self.stop_process()
        super().closeEvent(event)
