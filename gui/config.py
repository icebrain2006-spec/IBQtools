import json
import os
import logging
from PySide6.QtCore import QSettings

from gui.gdrive_utils import get_default_log_dir


def setup_error_logging(filepath, enabled=True):
    logger = logging.getLogger('IBQtools')
    logger.setLevel(logging.ERROR)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    if not enabled or not filepath:
        return

    try:
        abs_path = os.path.abspath(filepath)
        dir_name = os.path.dirname(abs_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        fh = logging.FileHandler(abs_path, encoding='utf-8')
        fh.setLevel(logging.ERROR)
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Failed to setup error logging: {e}")


def log_error(msg: str):
    """Utility helper to write an error message to IBQtools logger."""
    logging.getLogger('IBQtools').error(msg)


class AppConfig:
    def __init__(self):
        self.settings = QSettings("IBQtools", "BQ40Z50_Updater")
        
    def _resolve_safe_log_path(self, key: str, filename: str) -> str:
        val = self.settings.value(key, "", type=str)
        needs_fallback = False

        if not val or val == filename or not os.path.isabs(val):
            needs_fallback = True
        else:
            drive, _ = os.path.splitdrive(val)
            if drive and not os.path.exists(drive + "\\"):
                needs_fallback = True
            elif not os.path.exists(os.path.dirname(val)):
                try:
                    os.makedirs(os.path.dirname(val), exist_ok=True)
                except Exception:
                    needs_fallback = True

        if needs_fallback:
            safe_dir = get_default_log_dir()
            resolved = os.path.join(safe_dir, filename)
            self.settings.setValue(key, resolved)
            return resolved

        return val

    def get_work_log_path(self):
        return self._resolve_safe_log_path("work_log_path", "work_log.csv")
        
    def set_work_log_path(self, path):
        self.settings.setValue("work_log_path", path)
        
    def get_error_log_path(self):
        return self._resolve_safe_log_path("error_log_path", "error_log.txt")
        
    def set_error_log_path(self, path):
        self.settings.setValue("error_log_path", path)

    def get_error_log_en(self):
        return self.settings.value("error_log_en", "true") == "true"

    def set_error_log_en(self, enabled: bool):
        self.settings.setValue("error_log_en", "true" if enabled else "false")
        
    def get_cal_log_path(self):
        return self._resolve_safe_log_path("cal_log_path", "cal_log.csv")
        
    def set_cal_log_path(self, path):
        self.settings.setValue("cal_log_path", path)

    def get_gsheet_webhook_url(self):
        return self.settings.value("gsheet_webhook_url", "", type=str)

    def set_gsheet_webhook_url(self, url: str):
        self.settings.setValue("gsheet_webhook_url", url)

    def get_gsheet_logging_en(self):
        return self.settings.value("gsheet_logging_en", "true") == "true"

    def set_gsheet_logging_en(self, enabled: bool):
        self.settings.setValue("gsheet_logging_en", "true" if enabled else "false")
        
    def get_start_hotkey(self):
        return self.settings.value("start_hotkey", "Space", type=str)
        
    def set_start_hotkey(self, key):
        self.settings.setValue("start_hotkey", key)


config = AppConfig()
