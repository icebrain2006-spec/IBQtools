from PySide6.QtWidgets import QMessageBox, QFileDialog
from gui.workers.fw_update_worker import CheckUpdateWorker, DownloadUpdateWorker, RebootBootselWorker
from gui.styles import Colors


class OptionsFwUpdateMixin:
    """Mixin handling firmware auto-update and flashing operations for OptionsTab."""

    def _init_fw_state(self):
        self.latest_uf2_url = None
        self.boards_to_update = []
        self.update_queue = []
        self.current_update_port = None
        self.is_local_update = False
        self.local_update_path = None
        self.check_worker = None
        self.reboot_worker = None
        self.dl_worker = None

    def _on_check_update(self):
        repo = self.input_github_repo.text().strip()
        if not repo or '/' not in repo:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid GitHub repository (e.g. username/repo).")
            return
            
        self.btn_check_update.setEnabled(False)
        self.lbl_update_status.setText("Checking for updates...")
        self.btn_download_update.setEnabled(False)
        
        self.check_worker = CheckUpdateWorker(repo)
        self.check_worker.finished.connect(self._on_check_finished)
        self.check_worker.error.connect(self._on_check_error)
        self.check_worker.start()

    def _on_check_finished(self, tag, url, versions, active_ports):
        self.btn_check_update.setEnabled(True)
        
        if not versions:
            self.lbl_latest_ver.setText(f'Board: Unknown | Latest: <span style="color: {Colors.HEX_SUCCESS};">{tag}</span>')
            self.lbl_update_status.setText("No boards found.")
            return
            
        ver_strs = []
        for p, v in zip(active_ports, versions):
            color = Colors.HEX_SUCCESS if v == tag else Colors.HEX_FAIL
            ver_strs.append(f'{p}(<span style="color: {color};">{v}</span>)')
            
        self.lbl_latest_ver.setText(f'Boards: {", ".join(ver_strs)} | Latest: <span style="color: {Colors.HEX_SUCCESS};">{tag}</span>')
        self.lbl_update_status.setText("Update available.")
        self.latest_uf2_url = url
        self.boards_to_update = list(active_ports)
        self.btn_download_update.setEnabled(True)

    def _on_check_error(self, err_msg):
        self.btn_check_update.setEnabled(True)
        self.lbl_update_status.setText(f"Check failed: {err_msg}")
        self.lbl_latest_ver.setText("Board: Unknown | Latest: Error")

    def _on_download_update(self):
        if not self.latest_uf2_url:
            return
        if not self.boards_to_update:
            QMessageBox.information(self, "No boards", "No connected boards to update.")
            return
            
        self.update_queue = list(self.boards_to_update)
        self._process_next_board(is_local=False)

    def _process_next_board(self, is_local=False, local_path=None):
        if not self.update_queue:
            QMessageBox.information(self, "Finished", "All connected boards have been updated successfully.")
            self.btn_download_update.setEnabled(True)
            self.btn_check_update.setEnabled(True)
            self.btn_flash_local.setEnabled(True)
            self.lbl_update_status.setText("Batch update complete.")
            return
            
        port = self.update_queue.pop(0)
        self.current_update_port = port
        self.is_local_update = is_local
        self.local_update_path = local_path
        
        self.lbl_update_status.setText(f"Sending software reset to {port}...")
        
        # Async reboot worker to avoid UI blocking
        self.reboot_worker = RebootBootselWorker(target_port=port)
        self.reboot_worker.progress.connect(self._on_dl_progress)
        self.reboot_worker.finished.connect(
            lambda success, msg: self._on_reboot_finished(success, msg, port, is_local, local_path)
        )
        self.reboot_worker.start()

    def _on_reboot_finished(self, success, msg, port, is_local, local_path):
        upload_reply = QMessageBox.information(
            self,
            f"Ready to Upload - {port}",
            f"Board at {port} has been reset.\n"
            "Please wait for the USB drive (RPI-RP2) to be recognized.\n\n"
            "Click OK when the drive is ready.",
            QMessageBox.Ok | QMessageBox.Cancel
        )
        
        if upload_reply == QMessageBox.Ok:
            self.btn_download_update.setEnabled(False)
            self.btn_check_update.setEnabled(False)
            self.btn_flash_local.setEnabled(False)
            
            if is_local:
                self.dl_worker = DownloadUpdateWorker(local_file=local_path)
            else:
                self.dl_worker = DownloadUpdateWorker(url=self.latest_uf2_url)
                
            self.dl_worker.progress.connect(self._on_dl_progress)
            self.dl_worker.finished.connect(self._on_dl_finished)
            self.dl_worker.start()
        else:
            self.lbl_update_status.setText("Update cancelled.")
            self.btn_download_update.setEnabled(True)
            self.btn_check_update.setEnabled(True)
            self.btn_flash_local.setEnabled(True)

    def _on_flash_local(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Local Firmware", "", "UF2 Files (*.uf2);;All Files (*)")
        if not path:
            return
        if not self.boards_to_update:
            QMessageBox.information(self, "No boards", "Please click 'Check Update' first to scan connected boards.")
            return
            
        self.update_queue = list(self.boards_to_update)
        self._process_next_board(is_local=True, local_path=path)

    def _on_dl_progress(self, msg):
        self.lbl_update_status.setText(msg)

    def _on_dl_finished(self, success, msg):
        if success:
            self.lbl_update_status.setText(f"Done: {msg}")
            if self.update_queue:
                reply = QMessageBox.question(
                    self, 
                    "Next Board", 
                    f"Update for {self.current_update_port} successful!\n\nDo you want to proceed with the next board ({self.update_queue[0]})?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._process_next_board(is_local=self.is_local_update, local_path=self.local_update_path)
                    return
                else:
                    self.update_queue = []
                    self.lbl_update_status.setText("Batch update stopped.")
            else:
                QMessageBox.information(self, "Update Complete", "All selected boards updated successfully.")
        else:
            self.lbl_update_status.setText(f"Error: {msg}")
            QMessageBox.critical(self, "Update Error", msg)
            
        self.btn_check_update.setEnabled(True)
        self.btn_flash_local.setEnabled(True)
        self.btn_download_update.setEnabled(True)
