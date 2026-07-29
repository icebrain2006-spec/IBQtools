import sys
import os
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget
from PySide6.QtGui import QIcon

from config import config, setup_error_logging
from tabs.updater_tab import UpdaterTab
from tabs.calibration_tab import CalibrationTab
from tabs.manual_tab import ManualTab
from tabs.upload_tab import UploadTab
from tabs.csv_tab import CsvTab
from tabs.options_tab import OptionsTab

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    import logging
    logger = logging.getLogger('IBQtools')
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

class BqUpdaterMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IBQtools v0.8 (Multi BQ Firmware Programmer)")
        
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
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        # Instantiate Tabs
        self.updater_tab = UpdaterTab()
        self.calibration_tab = CalibrationTab()
        self.manual_tab = ManualTab()
        self.upload_tab = UploadTab()
        self.csv_tab = CsvTab()
        self.options_tab = OptionsTab()
        
        self.tabs.addTab(self.updater_tab, "Firmware Update (Main)")
        self.tabs.addTab(self.calibration_tab, "Calibration")
        self.tabs.addTab(self.manual_tab, "Manual I2C Debug")
        self.tabs.addTab(self.upload_tab, "SLFS Upload")
        self.tabs.addTab(self.csv_tab, "CSV to SLFS")
        self.tabs.addTab(self.options_tab, "Options")
        
        # Load UI states in the updater tab
        self.updater_tab.load_ui_states()

    def closeEvent(self, event):
        self.updater_tab.save_ui_states()
        if hasattr(self.calibration_tab, 'cal_thread') and self.calibration_tab.cal_thread and self.calibration_tab.cal_thread.isRunning():
            self.calibration_tab.cal_thread.stop()
            self.calibration_tab.cal_thread.wait(1000)
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Initialize error logging right at startup
    setup_error_logging(config.get_error_log_path())
    
    window = BqUpdaterMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
