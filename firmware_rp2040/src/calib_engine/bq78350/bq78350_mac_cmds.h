/**
 * @file bq78350_mac_cmds.h
 * @brief BQ78350 IC ManufacturerAccess() 16-bit MAC 커맨드 레지스터 정의 및 매크로
 */

#ifndef BQ78350_MAC_CMDS_H
#define BQ78350_MAC_CMDS_H

#include <stdint.h>

/**
 * @brief SMBus Block Write (Command 0x44) 용 2바이트 복합 리터럴 변환 매크로
 */
#define MAC_CMD(cmd) ((const uint8_t[]){ (uint8_t)((cmd) & 0xFF), (uint8_t)(((cmd) >> 8) & 0xFF) })

/* ========================================================================= */
/* BQ78350 ManufacturerAccess() 0x00 / 0x44 Command Address Definitions      */
/* ========================================================================= */
#define BQ78350_MAC_CAL_TOGGLE             0x002D  ///< Calibration Mode Toggle
#define BQ78350_MAC_MANUFACTURING_STATUS   0x0057  ///< Manufacturing Status Read
#define BQ78350_MAC_DASTATUS1              0x0071  ///< DAStatus1 Read
#define BQ78350_MAC_DASTATUS2              0x0072  ///< DAStatus2 Read
#define BQ78350_MAC_RAW_ADC_START          0xF081  ///< Raw ADC Read Start
#define BQ78350_MAC_RAW_ADC_STOP           0xF080  ///< Raw ADC Read Stop
#define BQ78350_MAC_RESET                  0x0041  ///< Device Reset

#endif // BQ78350_MAC_CMDS_H
