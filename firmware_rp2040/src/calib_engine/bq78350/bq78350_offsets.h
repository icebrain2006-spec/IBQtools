/**
 * @file bq78350_offsets.h
 * @brief BQ78350 IC 전용 오프셋 헤더 (공통 시프트 정의 및 버전별 오프셋 포함)
 */

#ifndef BQ78350_OFFSETS_H
#define BQ78350_OFFSETS_H

#include <stdint.h>

#ifndef SMBUS_PAYLOAD_OFFSET_SHIFT
#define SMBUS_PAYLOAD_OFFSET_SHIFT (-1)

static inline uint8_t get_payload_offset(uint8_t wire_offset) {
    return (uint8_t)(wire_offset + SMBUS_PAYLOAD_OFFSET_SHIFT);
}
#endif

typedef struct {
    uint8_t min_len;
    uint8_t current;
    uint8_t cell1;
    uint8_t cell2;
    uint8_t cell3;
    uint8_t cell4;
    uint8_t bat;
    uint8_t pack;
} bq78350_adc_offsets_t;

static const bq78350_adc_offsets_t BQ78350_ADC_OFFSETS = {
    .min_len = 18,
    .current = 5,
    .cell1   = 7,
    .cell2   = 9,
    .cell3   = 11,
    .cell4   = 13,
    .bat     = 15,
    .pack    = 17
};

typedef struct {
    uint8_t min_len;
    uint8_t int_temp;
    uint8_t ts1_temp;
    uint8_t ts2_temp;
    uint8_t ts3_temp;
    uint8_t ts4_temp;
} bq78350_dastatus2_offsets_t;

static const bq78350_dastatus2_offsets_t BQ78350_DASTATUS2_OFFSETS = {
    .min_len        = 30,
    .int_temp       = 3,
    .ts1_temp       = 5,
    .ts2_temp       = 7,
    .ts3_temp       = 9,
    .ts4_temp       = 11
};

#include "bq78350_v1_03_offsets.h"
#include "bq78350_v3_00_offsets.h"

#endif // BQ78350_OFFSETS_H
