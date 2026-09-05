/**
 * @file bq40z50_mac_cmds.h
 * @brief BQ40Z50 ManufacturerAccess() (MAC 0x00 / 0x44) Command List (Table 15-1)
 */

#ifndef BQ40Z50_MAC_CMDS_H
#define BQ40Z50_MAC_CMDS_H

#include <stdint.h>

// MAC Command Macro (SMBus 인자로 2바이트 배열 포인터 즉시 전달)
#define MAC_CMD(cmd) ((const uint8_t[]){ (uint8_t)((cmd) & 0xFF), (uint8_t)(((cmd) >> 8) & 0xFF) })

// System Status & Information Commands
#define BQ40Z50_MAC_DEVICE_TYPE         0x0001
#define BQ40Z50_MAC_FIRMWARE_VERSION    0x0002
#define BQ40Z50_MAC_HARDWARE_VERSION    0x0003
#define BQ40Z50_MAC_IF_CHECKSUM         0x0004
#define BQ40Z50_MAC_STATIC_DF_SIGNATURE 0x0005
#define BQ40Z50_MAC_CHEM_ID             0x0006
#define BQ40Z50_MAC_STATIC_CHEM_CHKSUM  0x0008
#define BQ40Z50_MAC_ALL_DF_SIGNATURE    0x0009
#define BQ40Z50_MAC_SHUTDOWN            0x0010
#define BQ40Z50_MAC_SLEEP               0x0011
#define BQ40Z50_MAC_RESET               0x0012

// Control & Toggle Commands
#define BQ40Z50_MAC_GAUGE_EN            0x0020
#define BQ40Z50_MAC_FET_CONTROL         0x0022
#define BQ40Z50_MAC_LIFETIME_EN         0x0023
#define BQ40Z50_MAC_PERM_FAIL_EN        0x0024
#define BQ40Z50_MAC_BLACKBOX_EN         0x0025
#define BQ40Z50_MAC_FUSE_TOGGLE         0x0026
#define BQ40Z50_MAC_LED_TOGGLE          0x0027
#define BQ40Z50_MAC_CAL_TOGGLE          0x002D  // CAL_EN Toggle
#define BQ40Z50_MAC_SEAL                0x0030

// Status & Telemetry Read Commands
#define BQ40Z50_MAC_SECURITY_KEYS       0x0035
#define BQ40Z50_MAC_AUTHENTICATION_KEY  0x0037
#define BQ40Z50_MAC_DEVICE_RESET        0x0041
#define BQ40Z50_MAC_SAFETY_ALERT        0x0050
#define BQ40Z50_MAC_SAFETY_STATUS       0x0051
#define BQ40Z50_MAC_PF_ALERT            0x0052
#define BQ40Z50_MAC_PF_STATUS           0x0053
#define BQ40Z50_MAC_OPERATION_STATUS    0x0054
#define BQ40Z50_MAC_CHARGING_STATUS     0x0055
#define BQ40Z50_MAC_GAUGING_STATUS      0x0056
#define BQ40Z50_MAC_MANUFACTURING_STATUS 0x0057  // ManufacturingStatus (CAL_EN at bit 7)
#define BQ40Z50_MAC_AFE_REGISTER        0x0058

// Calibration & RAW ADC Commands
#define BQ40Z50_MAC_DASTATUS1           0x0071  // DAStatus1 (Cell Voltages, Currents, Powers)
#define BQ40Z50_MAC_DASTATUS2           0x0072  // DAStatus2 (Temperatures, Raw ADCs)
#define BQ40Z50_MAC_RAW_ADC_STOP        0xF080  // Disable RAW ADC Mode
#define BQ40Z50_MAC_RAW_ADC_START       0xF081  // Enable RAW ADC Mode

#endif // BQ40Z50_MAC_CMDS_H
