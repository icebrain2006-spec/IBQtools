import threading
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal

from tabs.sn_checker_mixins import MasterPanelMixin, WorkerRunnerMixin, StateCacheMixin

class SNCheckerTab(MasterPanelMixin, WorkerRunnerMixin, StateCacheMixin, QWidget):
    """
    Multi-Board BQ40Z50 Serial Number & Date Checker/Updater Main Tab.
    Modularized using Mixin architecture for AGENTS.md 300-Line Limit compliance.
    """
    update_sn_ui_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.boards = []
        self.active_workers = 0
        self.sn_lock = threading.Lock()
        
        self.cached_exp_date = ""
        self.cached_fmt = "DEC"
        self.cached_should_write = False
        self.cached_should_inc = False
        self.cached_sn_int = 0
        
        self.update_sn_ui_signal.connect(self._safe_update_sn_ui)
        self._init_ui()

# Backwards compatibility alias
UpdaterTab = SNCheckerTab
