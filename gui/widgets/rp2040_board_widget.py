from PySide6.QtWidgets import QGroupBox
from PySide6.QtCore import Signal

from gui.widgets.board_mixins.board_ui_mixin import BoardUiMixin
from gui.widgets.board_mixins.board_worker_mixin import BoardWorkerMixin


class RP2040BoardWidget(QGroupBox, BoardUiMixin, BoardWorkerMixin):
    """Refactored Multi-Board RP2040 Widget decomposed into UI & Worker Mixins."""
    
    board_finished = Signal()
    request_start = Signal(object)  # Emits self instance when clicked

    def __init__(self, board_id: int, log_callback, get_expected_cb, cache_values_cb, parent=None):
        super().__init__("", parent)
        self.board_id = board_id
        self.log_callback = log_callback
        self.get_expected_cb = get_expected_cb
        self.cache_values_cb = cache_values_cb
        
        self.worker = None
        self.disconnect_monitor = None
        self.passed_channels = set()
        self.expected_sn_map = {}
        self.expected_date_map = {}
        self.expected_fmt = "DEC"
        
        self._init_ui()
