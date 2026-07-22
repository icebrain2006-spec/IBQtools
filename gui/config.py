import json
import os
from PySide6.QtCore import QSettings

class AppConfig:
    def __init__(self):
        self.settings = QSettings("IBQtools", "BQ40Z50_Updater")
        
    def get_work_log_path(self):
        return self.settings.value("work_log_path", "work_log.csv", type=str)
        
    def set_work_log_path(self, path):
        self.settings.setValue("work_log_path", path)
        
    def get_error_log_path(self):
        return self.settings.value("error_log_path", "error_log.txt", type=str)
        
    def set_error_log_path(self, path):
        self.settings.setValue("error_log_path", path)
        
config = AppConfig()
