/**
 * @file bq40z50_offsets.h
 * @brief BQ40Z50 IC 전용 특수 명령(MAC) 수신 데이터 오프셋 통합 정의 헤더
 */

#ifndef BQ40Z50_OFFSETS_H
#define BQ40Z50_OFFSETS_H

#include <stdint.h>

/* ========================================================================= */
/* 1. BQ40Z50 Raw ADC (MAC 0xF081) Output Byte Offset Configuration          */
/* Note: SMBus Block Read (0x44) prepends a 2-byte MAC Echo (0x81 0xF0)      */
/* ========================================================================= */
typedef struct {
    uint8_t min_len;  ///< 최소 수신 요구 바이트 길이
    uint8_t current;  ///< Current raw ADC 오프셋 (bytes 4-5)
    uint8_t cell1;    ///< Cell 1 Voltage raw ADC 오프셋 (bytes 6-7)
    uint8_t cell2;    ///< Cell 2 Voltage raw ADC 오프셋 (bytes 8-9)
    uint8_t cell3;    ///< Cell 3 Voltage raw ADC 오프셋 (bytes 10-11)
    uint8_t cell4;    ///< Cell 4 Voltage raw ADC 오프셋 (bytes 12-13)
    uint8_t pack;     ///< PACK Voltage raw ADC 오프셋 (bytes 16-17)
    uint8_t bat;      ///< BAT Voltage raw ADC 오프셋 (bytes 14-15)
} bq_raw_adc_offsets_t;

static const bq_raw_adc_offsets_t BQ40Z50_ADC_OFFSETS = {
    .min_len = 18,
    .current = 4,
    .cell1   = 6,
    .cell2   = 8,
    .cell3   = 10,
    .cell4   = 12,
    .pack    = 16,
    .bat     = 14
};

/* ========================================================================= */
/* 2. BQ40Z50 DAStatus1 (MAC 0x0071) Output Byte Offset Configuration       */
/* Note: SMBus Block Read (0x44) prepends a 2-byte MAC Echo (0x71 0x00)      */
/* ========================================================================= */
typedef struct {
    uint8_t min_len;
    uint8_t cell1;
    uint8_t cell2;
    uint8_t cell3;
    uint8_t cell4;
    uint8_t bat;
    uint8_t pack;
    uint8_t cell1_current;
    uint8_t cell2_current;
    uint8_t cell3_current;
    uint8_t cell4_current;
    uint8_t cell1_power;
    uint8_t cell2_power;
    uint8_t cell3_power;
    uint8_t cell4_power;
    uint8_t power;
} bq_dastatus1_offsets_t;

static const bq_dastatus1_offsets_t BQ40Z50_DASTATUS1_OFFSETS = {
    .min_len        = 34,
    .cell1          = 2,
    .cell2          = 4,
    .cell3          = 6,
    .cell4          = 8,
    .bat            = 10,
    .pack           = 12,
    .cell1_current  = 14,
    .cell2_current  = 16,
    .cell3_current  = 18,
    .cell4_current  = 20,
    .cell1_power    = 22,
    .cell2_power    = 24,
    .cell3_power    = 26,
    .cell4_power    = 28,
    .power          = 30
};

/* ========================================================================= */
/* 3. BQ40Z50 DAStatus2 (MAC 0x0072) Output Byte Offset Configuration       */
/* Note: SMBus Block Read (0x44) prepends a 2-byte MAC Echo (0x72 0x00)      */
/* ========================================================================= */
typedef struct {
    uint8_t min_len;
    uint8_t int_temp;
    uint8_t ts1_temp;
    uint8_t ts2_temp;
    uint8_t ts3_temp;
    uint8_t ts4_temp;
    uint8_t cell1_raw_adc;
    uint8_t cell2_raw_adc;
    uint8_t cell3_raw_adc;
    uint8_t cell4_raw_adc;
} bq_dastatus2_offsets_t;

static const bq_dastatus2_offsets_t BQ40Z50_DASTATUS2_OFFSETS = {
    .min_len        = 30,
    .int_temp       = 2,
    .ts1_temp       = 4,
    .ts2_temp       = 6,
    .ts3_temp       = 8,
    .ts4_temp       = 10,
    .cell1_raw_adc  = 22,
    .cell2_raw_adc  = 24,
    .cell3_raw_adc  = 26,
    .cell4_raw_adc  = 28
};

#endif // BQ40Z50_OFFSETS_H
