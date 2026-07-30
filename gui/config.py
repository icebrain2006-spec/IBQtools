import json
import os
import logging
from PySide6.QtCore import QSettings

def setup_error_logging(filepath):
    logger = logging.getLogger('IBQtools')
    logger.setLevel(logging.ERROR)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    try:
        fh = logging.FileHandler(filepath, encoding='utf-8')
        fh.setLevel(logging.ERROR)
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Failed to setup error logging: {e}")

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
        
    def get_cal_log_path(self):
        return self.settings.value("cal_log_path", "cal_log.csv", type=str)
        
    def set_cal_log_path(self, path):
        self.settings.setValue("cal_log_path", path)
        
config = AppConfig()
