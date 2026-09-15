import sys
import os

# Ensure repository root and gui directories are in sys.path when executed directly as a script
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_gui_dir = os.path.dirname(os.path.abspath(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _gui_dir not in sys.path:
    sys.path.insert(0, _gui_dir)

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QHBoxLayout, QPushButton
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from gui.tabs.sn_checker_tab import SNCheckerTab
from gui.tabs.calibration_tab import CalibrationTab
from gui.tabs.calibration_multi_tab import CalibrationMultiTab
from gui.tabs.manual_tab import ManualTab
from gui.tabs.slfs_flasher_tab import SLFSFlasherTab
from gui.tabs.csv_tab import CsvTab
from gui.tabs.options_tab import OptionsTab
from gui.tabs.auto_cycle_tab import AutoCycleTab
from gui.tabs.relay_tab import RelayWindow
from gui.version import __version__
from gui.strings import UIStrings
from gui.styles import Colors


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    import logging
    logger = logging.getLogger('IBQtools')
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception


class BqUpdaterMainWindow(QMainWindow):
    """Main Application Window for IBQtools BQ40Z50 Programmer."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"IBQtools v{__version__}")
        
        # Set app icon
        icon_path = os.path.join(os.path.dirname(__file__), "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(1500, 800)
        
        # Apply QSS
        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        try:
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Failed to load QSS: {e}")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        
        self.tabs = QTabWidget()
        
        self.btn_open_relay = QPushButton(UIStrings.get("BTN_OPEN_RELAY"))
        self.btn_open_relay.setStyleSheet(f"font-weight: bold; background-color: #2E7D32; color: {Colors.HEX_WHITE}; padding: 3px 12px; font-size: 11px; border-radius: 3px;")
        self.btn_open_relay.clicked.connect(self.open_relay_window)
        self.tabs.setCornerWidget(self.btn_open_relay, Qt.TopRightCorner)
        
        self.main_layout.addWidget(self.tabs)
        
        # Instantiate Tabs
        self.sn_checker_tab = SNCheckerTab()
        self.updater_tab = self.sn_checker_tab  # Backwards compatibility alias
        self.calibration_tab = CalibrationTab()
        self.calibration_multi_tab = CalibrationMultiTab()
        self.manual_tab = ManualTab()
        self.slfs_flasher_tab = SLFSFlasherTab()
        self.upload_tab = self.slfs_flasher_tab  # Backwards compatibility alias
        self.csv_tab = CsvTab()
        self.auto_cycle_tab = AutoCycleTab()
        self.options_tab = OptionsTab()
        
        self.tabs.addTab(self.sn_checker_tab, UIStrings.get("TAB_SN_INSPECTION"))
        self.tabs.addTab(self.calibration_tab, UIStrings.get("TAB_CALIBRATION"))
        self.tabs.addTab(self.calibration_multi_tab, "Calibration (18CH)")
        self.tabs.addTab(self.auto_cycle_tab, UIStrings.get("TAB_AUTO_CYCLE"))
        self.tabs.addTab(self.manual_tab, UIStrings.get("TAB_MANUAL_DEBUG"))
        self.tabs.addTab(self.slfs_flasher_tab, UIStrings.get("TAB_SLFS_FLASHER"))
        self.tabs.addTab(self.csv_tab, UIStrings.get("TAB_CSV_VIEWER"))
        self.tabs.addTab(self.options_tab, UIStrings.get("TAB_OPTIONS"))
        
        # Connect safety tab-locking signal during active cycle or logging
        self.auto_cycle_tab.lock_tabs_requested.connect(self.set_tabs_locked)
        
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Setup Global Hotkey for Quick Start
        from PySide6.QtGui import QKeySequence, QShortcut
        from gui.config import config
        self.start_shortcut = QShortcut(QKeySequence(config.get_start_hotkey()), self)
        self.start_shortcut.setContext(Qt.ApplicationShortcut)
        self.start_shortcut.activated.connect(self._on_global_hotkey_pressed)
        
        # Load UI states in the SN checker tab
        self.sn_checker_tab.load_ui_states()

    def set_tabs_locked(self, locked: bool):
        """Disables tab switching and auxiliary windows during active cycle/log test."""
        self.tabs.tabBar().setEnabled(not locked)
        if hasattr(self, 'btn_open_relay'):
            self.btn_open_relay.setEnabled(not locked)

    def open_relay_window(self):
        if not hasattr(self, 'relay_window') or not self.relay_window.isVisible():
            self.relay_window = RelayWindow()
            self.relay_window.show()
        else:
            self.relay_window.activateWindow()

    def update_start_hotkey(self, key_str):
        from PySide6.QtGui import QKeySequence
        self.start_shortcut.setKeySequence(QKeySequence(key_str))
        
    def _on_global_hotkey_pressed(self):
        current_widget = self.tabs.currentWidget()
        if current_widget == self.updater_tab:
            if hasattr(self.updater_tab, 'is_hotkey_ready') and self.updater_tab.is_hotkey_ready():
                if hasattr(self.updater_tab, 'trigger_start_all'):
                    self.updater_tab.trigger_start_all()
        elif current_widget == self.calibration_tab:
            if hasattr(self.calibration_tab, 'is_hotkey_ready') and self.calibration_tab.is_hotkey_ready():
                if hasattr(self.calibration_tab, 'trigger_start_all'):
                    self.calibration_tab.trigger_start_all()

    def on_tab_changed(self, index):
        if hasattr(self.updater_tab, 'btn_quick_start'):
            self.updater_tab.btn_quick_start.setChecked(False)
        if hasattr(self.calibration_tab, 'btn_quick_start'):
            self.calibration_tab.btn_quick_start.setChecked(False)
        if hasattr(self.calibration_multi_tab, 'btn_quick_start'):
            self.calibration_multi_tab.btn_quick_start.setChecked(False)

        current_w = self.tabs.widget(index)

        # Pause BQ FW Programmer disconnection monitors on tab leave to release COM ports, resume on return
        if current_w == self.updater_tab:
            if hasattr(self.updater_tab, 'resume_monitors'):
                self.updater_tab.resume_monitors()
        else:
            if hasattr(self.updater_tab, 'pause_monitors'):
                self.updater_tab.pause_monitors()

        if current_w == self.calibration_tab:
            if hasattr(self.calibration_tab, 'refresh_ports'):
                self.calibration_tab.refresh_ports()
        elif current_w == self.calibration_multi_tab:
            if hasattr(self.calibration_multi_tab, 'refresh_ports'):
                self.calibration_multi_tab.refresh_ports()
        else:
            if hasattr(self.calibration_tab, 'cal_thread') and self.calibration_tab.cal_thread and self.calibration_tab.cal_thread.isRunning():
                self.calibration_tab.cal_thread.stop()
                self.calibration_tab.cal_thread.wait(500)
                self.calibration_tab.log("Calibration stopped (Tab changed).")
                self.calibration_tab.table_data.setRowCount(0)
            if hasattr(self.calibration_multi_tab, 'cal_thread') and self.calibration_multi_tab.cal_thread and self.calibration_multi_tab.cal_thread.isRunning():
                self.calibration_multi_tab.cal_thread.stop()
                self.calibration_multi_tab.cal_thread.wait(500)
                self.calibration_multi_tab.log("Multi-Calibration stopped (Tab changed).")
                self.calibration_multi_tab.table_data.setRowCount(0)

    def closeEvent(self, event):
        self.updater_tab.save_ui_states()
        
        try:
            self.updater_tab._stop_all()
            for board in self.updater_tab.boards:
                if hasattr(board, 'worker') and board.worker and board.worker.isRunning():
                    board.worker.wait(1000)
        except Exception:
            pass

        if hasattr(self.calibration_tab, 'cal_thread') and self.calibration_tab.cal_thread and self.calibration_tab.cal_thread.isRunning():
            self.calibration_tab.cal_thread.stop()
            self.calibration_tab.cal_thread.wait(1000)
        if hasattr(self.calibration_multi_tab, 'cal_thread') and self.calibration_multi_tab.cal_thread and self.calibration_multi_tab.cal_thread.isRunning():
            self.calibration_multi_tab.cal_thread.stop()
            self.calibration_multi_tab.cal_thread.wait(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    app_font = app.font()
    if app_font.pointSize() <= 0:
        app_font.setPointSize(10)
    app.setFont(app_font)

    from gui.config import config, setup_error_logging
    setup_error_logging(config.get_error_log_path(), config.get_error_log_en())
    
    window = BqUpdaterMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
