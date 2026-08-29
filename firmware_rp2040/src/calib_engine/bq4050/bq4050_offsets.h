/**
 * @file bq4050_offsets.h
 * @brief BQ4050 IC 전용 오프셋 헤더 (공통 시프트 정의 및 버전별 오프셋 포함)
 */

#ifndef BQ4050_OFFSETS_H
#define BQ4050_OFFSETS_H

#include <stdint.h>

#ifndef SMBUS_PAYLOAD_OFFSET_SHIFT
#define SMBUS_PAYLOAD_OFFSET_SHIFT (-1)

static inline uint8_t get_payload_offset(uint8_t wire_offset) {
    return (uint8_t)(wire_offset + SMBUS_PAYLOAD_OFFSET_SHIFT);
}
#endif

#include "bq4050_v0_01_offsets.h"

#endif // BQ4050_OFFSETS_H
