/**
 * @file bq40z50_offsets.h
 * @brief BQ40Z50 IC 전용 특수 명령(MAC) 수신 데이터 물리 프레임 오프셋 통합 정의 헤더
 * 
 * =========================================================================================
 * [ BQ40Z50 -> RP2040 SMBus Block Read (0x44) 실제 수신 데이터 물리 프레임 구조 ]
 * (EV2300 트레이스 및 TI BQ40Z50 데이터시트 1:1 대응 오프셋)
 * =========================================================================================
 * 
 * 1) Raw ADC Mode (MAC 0xF081) 수신 프레임 맵 (총 27 바이트 데이터)
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Byte 0  | Byte 1  | Byte 2  | Byte 3  | Byte 4  | Byte 5-6| Byte 7-8|Byte 9-10|Byte 11-12|
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Length  | 0x81    | 0xF0    | Reserved| Reserved| Current | Cell 1  | Cell 2  | Cell 3  |
 * | (0x1A)  | (EchoL) | (EchoH) | (0xBE)  | (0x01)  | (RawADC)| (RawADC)| (RawADC)| (RawADC)|
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * |Byte 13-14|Byte 15-16|Byte 17-18| ...     | Byte 27 |
 * +----------+----------+----------+---------+---------+
 * | Cell 4   | BAT Volt | PACK Volt| Reserved| PEC     |
 * | (RawADC) | (RawADC) | (RawADC) |         | (CRC8)  |
 * +----------+----------+----------+---------+---------+
 * 
 * 2) DAStatus1 (MAC 0x0071) 수신 프레임 맵 (총 35 바이트 데이터)
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Byte 0  | Byte 1  | Byte 2  | Byte 3-4| Byte 5-6| Byte 7-8|Byte 9-10|Byte 11-12|Byte 13-14|
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Length  | 0x71    | 0x00    | Cell 1  | Cell 2  | Cell 3  | Cell 4  | BAT Volt| PACK Volt|
 * | (0x22)  | (EchoL) | (EchoH) | (mV)    | (mV)    | (mV)    | (mV)    | (mV)    | (mV)    |
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * |Byte 15-16|Byte 17-18|Byte 19-20|Byte 21-22|Byte 23-24|Byte 25-26|Byte 27-28|Byte 29-30|Byte 31-32|
 * +----------+----------+----------+----------+----------+----------+----------+----------+----------+
 * | Cell1 Cur| Cell2 Cur| Cell3 Cur| Cell4 Cur| Cell1 Pwr| Cell2 Pwr| Cell3 Pwr| Cell4 Pwr| Total Pwr|
 * | (mA)     | (mA)     | (mA)     | (mA)     | (mW)     | (mW)     | (mW)     | (mW)     | (mW)     |
 * +----------+----------+----------+----------+----------+----------+----------+----------+----------+
 * 
 * 3) DAStatus2 (MAC 0x0072) 수신 프레임 맵 (총 31 바이트 데이터)
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Byte 0  | Byte 1  | Byte 2  | Byte 3-4| Byte 5-6| Byte 7-8|Byte 9-10|Byte 11-12| ...     |
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Length  | 0x72    | 0x00    | Int Temp| TS1 Temp| TS2 Temp| TS3 Temp| TS4 Temp| Res/Pwr |
 * | (0x1E)  | (EchoL) | (EchoH) | (0.1K)  | (0.1K)  | (0.1K)  | (0.1K)  | (0.1K)  |         |
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * |Byte 23-24|Byte 25-26|Byte 27-28|Byte 29-30|
 * +----------+----------+----------+----------+
 * |Cell1 ADC |Cell2 ADC |Cell3 ADC |Cell4 ADC |
 * | (Raw)    | (Raw)    | (Raw)    | (Raw)    |
 * +----------+----------+----------+----------+
 * 
 * 4) Calibration DataFlash Block (Subclass 0x4000 / MAC 0x4000) 프레임 맵 (총 35 바이트)
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Byte 0  | Byte 1  | Byte 2  | Byte 3-4| Byte 5-6| Byte 7-8| Byte 9-12|Byte 13-16| ...    |
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Length  | 0x00    | 0x40    | Cell 1  | BAT Gain| PACK Gain| CC Gain | Capacity| ...     |
 * | (0x22)  | (EchoL) | (EchoH) | Gain    |         |         | (float) | Gain(flt)|        |
 * +---------+---------+---------+---------+---------+---------+---------+---------+---------+
 * | Byte 34 |
 * +---------+
 * | PEC     |
 * | (CRC8)  |
 * +---------+
 * =========================================================================================
 */

#ifndef BQ40Z50_OFFSETS_H
#define BQ40Z50_OFFSETS_H

#include <stdint.h>

/** 
 * @brief SMBus Block Read 프로토콜 사용 시 Length 바이트(Byte 0) 분리로 인한 C 버퍼 페이로드 오프셋 시프트 값
 * @note Physical Wire-Level Offset에서 1을 차감하면 C 배열 rx_buf 페이로드 인덱스가 됩니다.
 */
#define SMBUS_PAYLOAD_OFFSET_SHIFT (-1)

/**
 * @brief Physical Wire-Level Offset을 C 버퍼 페이로드 인덱스로 변환하는 도우미 함수
 * @param wire_offset EV2300 / TI 데이터시트 물리 오프셋 값 (1-indexed)
 * @return C 배열 페이로드 인덱스 (0-indexed)
 */
static inline uint8_t get_payload_offset(uint8_t wire_offset) {
    return (uint8_t)(wire_offset + SMBUS_PAYLOAD_OFFSET_SHIFT);
}

/* ========================================================================= */
/* 1. BQ40Z50 Raw ADC (MAC 0xF081) Output Byte Offset Configuration          */
/* Note: EV2300 Wire-Level Offsets (Includes Byte 0 Length)                  */
/* ========================================================================= */
typedef struct {
    uint8_t min_len;  ///< 최소 수신 요구 바이트 길이
    uint8_t current;  ///< Current raw ADC 오프셋 (bytes 5-6)
    uint8_t cell1;    ///< Cell 1 Voltage raw ADC 오프셋 (bytes 7-8)
    uint8_t cell2;    ///< Cell 2 Voltage raw ADC 오프셋 (bytes 9-10)
    uint8_t cell3;    ///< Cell 3 Voltage raw ADC 오프셋 (bytes 11-12)
    uint8_t cell4;    ///< Cell 4 Voltage raw ADC 오프셋 (bytes 13-14)
    uint8_t bat;      ///< BAT Voltage raw ADC 오프셋 (bytes 15-16)
    uint8_t pack;     ///< PACK Voltage raw ADC 오프셋 (bytes 17-18)
} bq_raw_adc_offsets_t;

static const bq_raw_adc_offsets_t BQ40Z50_ADC_OFFSETS = {
    .min_len = 18,
    .current = 5,
    .cell1   = 7,
    .cell2   = 9,
    .cell3   = 11,
    .cell4   = 13,
    .bat     = 15,
    .pack    = 17
};

/* ========================================================================= */
/* 2. BQ40Z50 DAStatus1 (MAC 0x0071) Output Byte Offset Configuration       */
/* Note: EV2300 Wire-Level Offsets (Includes Byte 0 Length)                  */
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
    .cell1          = 3,
    .cell2          = 5,
    .cell3          = 7,
    .cell4          = 9,
    .bat            = 11,
    .pack           = 13,
    .cell1_current  = 15,
    .cell2_current  = 17,
    .cell3_current  = 19,
    .cell4_current  = 21,
    .cell1_power    = 23,
    .cell2_power    = 25,
    .cell3_power    = 27,
    .cell4_power    = 29,
    .power          = 31
};

/* ========================================================================= */
/* 3. BQ40Z50 DAStatus2 (MAC 0x0072) Output Byte Offset Configuration       */
/* Note: EV2300 Wire-Level Offsets (Includes Byte 0 Length)                  */
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
    .int_temp       = 3,
    .ts1_temp       = 5,
    .ts2_temp       = 7,
    .ts3_temp       = 9,
    .ts4_temp       = 11,
    .cell1_raw_adc  = 23,
    .cell2_raw_adc  = 25,
    .cell3_raw_adc  = 27,
    .cell4_raw_adc  = 29
};

/* ========================================================================= */
/* 4. BQ40Z50 DataFlash 0x4000 Calibration Block Offset Configuration       */
/* Note: EV2300 Wire-Level Offsets (Includes Byte 0 Length 0x22)             */
/* Subclass Address: 0x4000 (CC Gain, Capacity Gain, Voltage Gains)          */
/* ========================================================================= */
typedef struct {
    uint8_t min_len;
    uint8_t cell1_gain;     ///< Cell 1 Gain 오프셋 (uint16_t, bytes 3-4)
    uint8_t bat_gain;       ///< BAT Gain 오프셋 (uint16_t, bytes 5-6)
    uint8_t pack_gain;      ///< PACK Gain 오프셋 (uint16_t, bytes 7-8)
    uint8_t cc_gain;        ///< CC Gain 오프셋 (float32, bytes 9-12)
    uint8_t capacity_gain;  ///< Capacity Gain 오프셋 (float32, bytes 13-16)
} bq_df4000_offsets_t;

static const bq_df4000_offsets_t BQ40Z50_DF4000_OFFSETS = {
    .min_len        = 34,
    .cell1_gain     = 3,
    .bat_gain       = 5,
    .pack_gain      = 7,
    .cc_gain        = 9,
    .capacity_gain  = 13
};

#include "bq40z50_v3_09_offsets.h"
#include "bq40z50_v4_02_offsets.h"
#include "bq40z50_v5_05_offsets.h"

#endif // BQ40Z50_OFFSETS_H
