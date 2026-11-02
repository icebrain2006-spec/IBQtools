import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLineEdit, QPushButton, QFormLayout, QMessageBox,
    QFileDialog, QLabel, QCheckBox
)
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QKeySequenceEdit

from gui.config import config, setup_error_logging
from gui.dialogs.csv_viewer_dialog import CsvViewerDialog
from gui.styles import Colors
from gui.strings import UIStrings
from gui.tabs.options_mixins import OptionsFwUpdateMixin, OptionsGDriveSyncMixin


class OptionsTab(QWidget, OptionsFwUpdateMixin, OptionsGDriveSyncMixin):
    """Options and configuration settings tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_fw_state()
        self._init_ui()
        
    def _init_ui(self):
        layout_options = QVBoxLayout(self)
        
        # --- Data Logging Settings ---
        group_log_settings = QGroupBox(UIStrings.get("GRP_DATA_LOGGING"))
        layout_log = QFormLayout(group_log_settings)
        
        self.input_work_log = QLineEdit()
        self.btn_browse_work = QPushButton(UIStrings.get("BTN_BROWSE"))
        self.btn_view_work = QPushButton(UIStrings.get("BTN_VIEWER"))
        work_layout = QHBoxLayout()
        work_layout.addWidget(self.input_work_log)
        work_layout.addWidget(self.btn_browse_work)
        work_layout.addWidget(self.btn_view_work)
        
        self.input_cal_log = QLineEdit()
        self.btn_browse_cal = QPushButton(UIStrings.get("BTN_BROWSE"))
        self.btn_view_cal = QPushButton(UIStrings.get("BTN_VIEWER"))
        cal_layout = QHBoxLayout()
        cal_layout.addWidget(self.input_cal_log)
        cal_layout.addWidget(self.btn_browse_cal)
        cal_layout.addWidget(self.btn_view_cal)
        
        self.input_error_log = QLineEdit()
        self.btn_browse_error = QPushButton(UIStrings.get("BTN_BROWSE"))
        error_layout = QHBoxLayout()
        error_layout.addWidget(self.input_error_log)
        error_layout.addWidget(self.btn_browse_error)
        
        layout_log.addRow(UIStrings.get("LBL_WORK_LOG"), work_layout)
        layout_log.addRow(UIStrings.get("LBL_CAL_LOG"), cal_layout)

        # Google Drive Integration Controls
        self.lbl_gdrive_path = QLabel()
        self.lbl_gdrive_path.setWordWrap(True)
        self.btn_set_gdrive = QPushButton(UIStrings.get("BTN_SET_GDRIVE"))
        self.btn_migrate_logs = QPushButton(UIStrings.get("BTN_MIGRATE_LOGS"))
        
        gdrive_btn_layout = QHBoxLayout()
        gdrive_btn_layout.addWidget(self.btn_set_gdrive)
        gdrive_btn_layout.addWidget(self.btn_migrate_logs)
        
        layout_log.addRow(UIStrings.get("LBL_GDRIVE_STORAGE"), self.lbl_gdrive_path)
        layout_log.addRow("", gdrive_btn_layout)
        
        # --- Error & Debug Settings ---
        group_error_settings = QGroupBox(UIStrings.get("GRP_ERROR_DEBUG"))
        layout_error = QFormLayout(group_error_settings)
        
        self.cb_save_error_log = QCheckBox(UIStrings.get("CB_SAVE_ERROR_LOG"))
        self.cb_save_error_log.setChecked(config.get_error_log_en())
        self.cb_save_error_log.toggled.connect(self._on_error_log_toggled)
        layout_error.addRow("", self.cb_save_error_log)
        layout_error.addRow(UIStrings.get("LBL_ERROR_LOG"), error_layout)
        
        self.cb_global_debug_log = QCheckBox(UIStrings.get("CB_GLOBAL_DEBUG_LOG"))
        self.cb_global_debug_log.setChecked(config.settings.value("global_debug_log_en", "false") == "true")
        layout_error.addRow(UIStrings.get("LBL_CONSOLE_OUTPUT"), self.cb_global_debug_log)
        
        # --- Production Settings ---
        group_prod_settings = QGroupBox(UIStrings.get("GRP_PRODUCTION"))
        layout_prod = QFormLayout(group_prod_settings)
        
        self.input_hotkey = QKeySequenceEdit()
        self.input_hotkey.setKeySequence(QKeySequence(config.get_start_hotkey()))
        self.input_hotkey.setToolTip(UIStrings.get("TOOLTIP_HOTKEY"))
        layout_prod.addRow(UIStrings.get("LBL_QUICK_START_HOTKEY"), self.input_hotkey)
        
        self.btn_save_options = QPushButton(UIStrings.get("BTN_SAVE_SETTINGS"))
        
        layout_options.addWidget(group_log_settings)
        layout_options.addWidget(group_error_settings)
        layout_options.addWidget(group_prod_settings)
        layout_options.addWidget(self.btn_save_options)
        
        # --- Firmware Auto-Update Settings ---
        group_fw = QGroupBox(UIStrings.get("GRP_FW_UPDATE"))
        layout_fw = QVBoxLayout(group_fw)
        
        form_fw = QFormLayout()
        self.input_github_repo = QLineEdit(config.settings.value("github_repo", "icebrain2006-spec/IBQtools", type=str))
        self.input_github_repo.setPlaceholderText(UIStrings.get("PH_GITHUB_REPO"))
        form_fw.addRow(UIStrings.get("LBL_GITHUB_REPO"), self.input_github_repo)
        
        self.lbl_latest_ver = QLabel("Board: Unknown | Latest: Unknown")
        self.lbl_latest_ver.setStyleSheet(f"color: {Colors.HEX_WARN_CYAN}; font-weight: bold;")
        form_fw.addRow(UIStrings.get("LBL_STATUS"), self.lbl_latest_ver)
        
        layout_fw.addLayout(form_fw)
        
        btn_layout = QHBoxLayout()
        self.btn_check_update = QPushButton(UIStrings.get("BTN_CHECK_UPDATE"))
        self.btn_download_update = QPushButton(UIStrings.get("BTN_DOWNLOAD_FLASH"))
        self.btn_download_update.setEnabled(False)
        self.btn_download_update.setObjectName("startBtn")
        
        self.btn_flash_local = QPushButton(UIStrings.get("BTN_FLASH_LOCAL"))
        self.btn_flash_local.setObjectName("startBtn")
        
        btn_layout.addWidget(self.btn_check_update)
        btn_layout.addWidget(self.btn_download_update)
        btn_layout.addWidget(self.btn_flash_local)
        layout_fw.addLayout(btn_layout)
        
        self.lbl_update_status = QLabel(UIStrings.get("LBL_READY"))
        layout_fw.addWidget(self.lbl_update_status)
        
        layout_options.addWidget(group_fw)
        layout_options.addStretch()
        
        # Initial Values & Labels
        self.input_work_log.setText(config.get_work_log_path())
        self.input_cal_log.setText(config.get_cal_log_path())
        self.input_error_log.setText(config.get_error_log_path())
        self._on_error_log_toggled(self.cb_save_error_log.isChecked())
        self._update_gdrive_status_label()
        
        # Connect signals
        self.btn_browse_work.clicked.connect(self._browse_work_log)
        self.btn_browse_cal.clicked.connect(self._browse_cal_log)
        self.btn_browse_error.clicked.connect(self._browse_error_log)
        
        self.btn_view_work.clicked.connect(self._view_work_log)
        self.btn_view_cal.clicked.connect(self._view_cal_log)
        
        self.btn_set_gdrive.clicked.connect(self._on_set_gdrive_paths)
        self.btn_migrate_logs.clicked.connect(self._on_migrate_local_logs)
        
        self.btn_save_options.clicked.connect(self._save_settings)
        self.btn_check_update.clicked.connect(self._on_check_update)
        self.btn_download_update.clicked.connect(self._on_download_update)
        self.btn_flash_local.clicked.connect(self._on_flash_local)

    def _on_error_log_toggled(self, checked: bool):
        self.input_error_log.setEnabled(checked)
        self.btn_browse_error.setEnabled(checked)

    def _browse_work_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Work Log File", self.input_work_log.text(), "CSV Files (*.csv);;All Files (*)")
        if path:
            self.input_work_log.setText(path)

    def _view_work_log(self):
        path = self.input_work_log.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Not Found", "The specified CSV file does not exist yet.")
            return
        dialog = CsvViewerDialog(path, self)
        dialog.exec()

    def _browse_cal_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Cal Log File", self.input_cal_log.text(), "CSV Files (*.csv);;All Files (*)")
        if path:
            self.input_cal_log.setText(path)

    def _view_cal_log(self):
        path = self.input_cal_log.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Not Found", "The specified CSV file does not exist yet.")
            return
        dialog = CsvViewerDialog(path, self)
        dialog.exec()

    def _browse_error_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Error Log File", self.input_error_log.text(), "Text Files (*.txt *.log);;All Files (*)")
        if path:
            self.input_error_log.setText(path)

    def _save_settings(self):
        config.set_work_log_path(self.input_work_log.text())
        config.set_cal_log_path(self.input_cal_log.text())
        config.set_error_log_path(self.input_error_log.text())
        config.set_error_log_en(self.cb_save_error_log.isChecked())
        config.settings.setValue("github_repo", self.input_github_repo.text().strip())
        config.settings.setValue("global_debug_log_en", "true" if self.cb_global_debug_log.isChecked() else "false")
        
        seq = self.input_hotkey.keySequence().toString()
        if not seq: 
            seq = "Space"
        config.set_start_hotkey(seq)
        config.settings.sync()
        
        main_win = self.window()
        if hasattr(main_win, 'update_start_hotkey'):
            main_win.update_start_hotkey(seq)
            
        setup_error_logging(self.input_error_log.text(), self.cb_save_error_log.isChecked())
        self._update_gdrive_status_label()
        QMessageBox.information(self, "Settings Saved", "Application settings have been saved successfully.")
