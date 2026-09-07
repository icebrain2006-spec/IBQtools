"""Backward compatibility re-export module for protocols and workers."""

from gui.protocol import (
    PROTOCOL_STX, PROTOCOL_ETX, CMD_FW_UPLOAD_START, CMD_FW_UPLOAD_DATA, 
    CMD_FW_UPLOAD_END, CMD_FW_UPDATE_RUN, CMD_FW_UPDATE_STATUS, CMD_FW_UPDATE_STOP, 
    CMD_I2C_RAW, CMD_FW_GET_FILE_INFO, CMD_SMBUS_CMD, CMD_SMBUS_POLL_BLOCK, 
    CMD_GET_VERSION, CMD_RELAY_SET, CMD_SET_LED_STATE, RESP_OK,
    UPDATER_STATE_IDLE, UPDATER_STATE_RUNNING, UPDATER_STATE_DELAYING, 
    UPDATER_STATE_ERROR, UPDATER_STATE_DONE,
    crc16_calculate, make_packet, parse_response, get_file_info, get_fw_version
)

from gui.workers import (
    set_led_state, DisconnectionMonitor, 
    ScanWorker, GlobalPreflightWorker, 
    UpdaterWorker, SerialCheckWorker, UploadWorker
)
