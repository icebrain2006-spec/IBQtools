import threading
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal

from gui.tabs.sn_checker_mixins import MasterPanelMixin, WorkerRunnerMixin, StateCacheMixin


class SNCheckerTab(MasterPanelMixin, WorkerRunnerMixin, StateCacheMixin, QWidget):
    """
    Multi-Board BQ40Z50 Serial Number & Date Checker/Updater Main Tab.
    Modularized using Mixin architecture for AGENTS.md 300-Line Limit compliance.
    """
    update_sn_ui_signal = Signal(str)
    update_mfg_sn_ui_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.boards = []
        self.active_workers = 0
        self.sn_lock = threading.Lock()
        
        # SBS Cached States
        self.cached_exp_date = ""
        self.cached_fmt = "DEC"
        self.cached_should_write = False
        self.cached_should_inc = False
        self.cached_sn_int = 0

        # Manufacturer Data Cached States
        self.cached_should_write_mfg = False
        self.cached_mfg_start_block = "A02"
        self.cached_mfg_auto_inc = False
        self.cached_mfg_fmt = "DEC"
        self.cached_mfg_sn_int = 1
        
        self.update_sn_ui_signal.connect(self._safe_update_sn_ui)
        self.update_mfg_sn_ui_signal.connect(self._safe_update_mfg_sn_ui)
        self._init_ui()

    def pause_monitors(self):
        """Stops all active disconnection monitors to release COM ports when switching tabs."""
        for board in self.boards:
            if hasattr(board, '_stop_disconnection_monitor'):
                board._stop_disconnection_monitor()

    def resume_monitors(self):
        """Resumes disconnection monitors for passed channels when returning to tab."""
        for board in self.boards:
            if hasattr(board, '_start_disconnection_monitor_if_needed'):
                board._start_disconnection_monitor_if_needed()


# Backwards compatibility alias
UpdaterTab = SNCheckerTab
